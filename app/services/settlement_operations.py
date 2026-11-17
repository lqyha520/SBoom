"""结算留档、异常恢复、差异说明及站内消息。"""

import hashlib
import io
import json
import time
import uuid
from typing import Any

from fastapi import HTTPException
from PIL import Image

from app.db import db
from app.security import decrypt_secret, encrypt_secret
from app.services import catalog_scope, settlement_access, settlements
from app.services.mini_errors import fail


def owned_statement(conn, actor, identifier):
    row = settlements.statement_row(conn, identifier)
    owner = settlement_access.owner_id(conn, actor)
    if owner is not None and row['beneficiary'] != 'admin:' + str(owner):
        fail('结算单不存在', 404)
    return row


def payee(actor):
    with db() as conn:
        catalog_scope.owner_id(conn, actor)
        row = conn.execute('SELECT summary,revision FROM referral_payees WHERE beneficiary=?', ('admin:' + str(actor),)).fetchone()
        return {**row['summary'], 'revision': row['revision']} if row else None


def save_payee(actor, body):
    with db(serialized='accounts') as conn:
        catalog_scope.owner_id(conn, actor)
        target = 'admin:' + str(actor)
        previous = conn.execute('SELECT revision FROM referral_payees WHERE beneficiary=?', (target,)).fetchone()
        if (previous['revision'] if previous else 0) != body.revision:
            fail('收款资料已变化，请刷新', 409)
        if body.method == 'bank' and not body.bank:
            fail('银行收款请填写开户行', 422)
        if any(ord(c) < 32 for c in body.account + body.name + body.bank):
            fail('收款资料包含无效字符', 422)
        value = body.model_dump(exclude={'revision'})
        summary = {**value, 'account': '****' + body.account[-4:]}
        conn.execute('INSERT INTO referral_payees(beneficiary,value_enc,summary,updated_at) VALUES(?,?,?::jsonb,?) '
                     'ON CONFLICT(beneficiary) DO UPDATE SET value_enc=excluded.value_enc,summary=excluded.summary,revision=referral_payees.revision+1,updated_at=excluded.updated_at',
                     (target, encrypt_secret(json.dumps(value)), json.dumps(summary), int(time.time())))
        settlements.audit(conn, actor, 'payee_updated', target, {'beneficiary': target, 'summary': summary})
        return {**summary, 'revision': body.revision + 1}


def capture_payee(conn, identifier, beneficiary):
    row = conn.execute('SELECT * FROM referral_payees WHERE beneficiary=?', (beneficiary,)).fetchone()
    if not row:
        return None
    conn.execute('INSERT INTO referral_payout_accounts(statement_id,value_enc) VALUES(?,?) ON CONFLICT DO NOTHING', (identifier, row['value_enc']))
    return {**row['summary'], 'revision': row['revision']}


def reveal_payee(actor, identifier):
    with db(serialized='accounts') as conn:
        settlement_access.authorize(conn, actor, 'Payout')
        row = owned_statement(conn, actor, identifier)
        value = conn.execute('SELECT value_enc FROM referral_payout_accounts WHERE statement_id=?', (identifier,)).fetchone()
        if not value:
            fail('本结算单尚未留存收款资料', 404)
        settlements.audit(conn, actor, 'payee_revealed', identifier, {'beneficiary': row['beneficiary']})
        return json.loads(decrypt_secret(value['value_enc']))


def attach_payee(actor, identifier, revision):
    with db(serialized='accounts') as conn:
        settlement_access.authorize(conn, actor, 'Payout')
        row = settlements.statement_row(conn, identifier)
        if row['revision'] != revision or row['status'] not in ('draft', 'approved') or row['snapshot'].get('payee'):
            fail('结算单已变化或已有收款快照', 409)
        value = capture_payee(conn, identifier, row['beneficiary'])
        if not value:
            fail('请管理员先保存本人的收款资料', 422)
        snapshot = {**row['snapshot'], 'payee': value}
        conn.execute('UPDATE referral_statements SET snapshot=?::jsonb,revision=revision+1 WHERE id=?', (json.dumps(snapshot), identifier))
        settlements.audit(conn, actor, 'payee_attached', identifier, {'summary': value})
        return dict(settlements.statement_row(conn, identifier))


def attachment_access(actor, identifier, write=False):
    with db() as conn:
        row = owned_statement(conn, actor, identifier)
        if write:
            require_evidence_writer(conn, actor)
            if row['status'] == 'void':
                fail('已作废结算单不能添加付款凭证', 409)


def validate_attachment(name, content):
    if not content or len(content) > 2 * 1024 * 1024:
        fail('凭证限 2MB', 413)
    if content.startswith(b'%PDF-') and b'%%EOF' in content[-1024:]:
        media = 'application/pdf'
    else:
        try:
            with Image.open(io.BytesIO(content)) as img:
                if img.format not in ('PNG', 'JPEG') or img.width * img.height > 16000000:
                    raise ValueError
                media = 'image/png' if img.format == 'PNG' else 'image/jpeg'
                img.verify()
        except (OSError, ValueError, Image.DecompressionBombError):
            fail('仅支持有效的 PNG、JPEG 或 PDF 凭证', 422)
    name = name.replace('\\', '/').split('/')[-1][:120]
    if not name or any(ord(c) < 32 for c in name):
        fail('文件名无效', 422)
    return name, media


def require_evidence_writer(conn, actor):
    from app.admin_permissions import allowed
    user = settlement_access.identity(conn, actor)
    if not any(allowed(user, menu, 'run') for menu in settlement_access.MENUS):
        fail('需要结算财务操作权限', 403)


def upload_attachment(actor, identifier, name, content):
    name, media = validate_attachment(name, content)
    digest = hashlib.sha256(content).hexdigest()
    with db(serialized='accounts') as conn:
        require_evidence_writer(conn, actor)
        row = owned_statement(conn, actor, identifier)
        if row['status'] == 'void':
            fail('已作废结算单不能添加付款凭证', 409)
        previous = conn.execute('SELECT id FROM referral_attachments WHERE statement_id=? AND digest=?', (identifier, digest)).fetchone()
        if previous:
            return {'id': previous['id']}
        if conn.execute('SELECT COUNT(*) FROM referral_attachments WHERE statement_id=?', (identifier,)).fetchone()[0] >= 5:
            fail('每张结算单最多保留 5 个凭证', 422)
        key = uuid.uuid4().hex
        conn.execute('INSERT INTO referral_attachments(id,statement_id,actor_id,name,media_type,digest,content,created_at) VALUES(?,?,?,?,?,?,?,?)',
                     (key, identifier, actor, name, media, digest, content, int(time.time())))
        settlements.audit(conn, actor, 'attachment_added', identifier, {'name': name, 'digest': digest})
        return {'id': key}


def attachment(actor, identifier):
    with db() as conn:
        row = conn.execute('SELECT * FROM referral_attachments WHERE id=?', (identifier,)).fetchone()
        if not row:
            fail('凭证不存在', 404)
        owned_statement(conn, actor, row['statement_id'])
        return dict(row)


def attachments(conn, identifier):
    return [dict(row) for row in conn.execute('SELECT id,name,media_type,created_at FROM referral_attachments WHERE statement_id=? ORDER BY created_at,id', (identifier,))]


def difference(request, statement, rewards):
    original = {item['order_id']: item for item in request['snapshot']['items']}
    actual = {item['order_id']: item for item in statement['snapshot']['items']} if statement else {item['order_id']: item for item in rewards}
    rows = []
    for key, before in original.items():
        after = actual.get(key)
        costs = after.get('costs') if after else None
        old_fees = {fee['name']: fee.get('amount_fen') for fee in before['reference_fees']}
        new_fees = {fee['name']: fee['amount_fen'] for fee in costs['shared_fees']} if costs else {}
        rows.append({'order_id': key, 'before_fen': before['reference_commission_fen'],
                     'after_fen': after.get('commission_fen') if after and costs else None,
                     'channel_before_fen': before['reference_channel_fen'], 'channel_after_fen': costs['channel_fee_fen'] if costs else None,
                     'fees': [{'name': name, 'before_fen': old_fees.get(name, 0), 'after_fen': new_fees.get(name, 0) if costs else None} for name in sorted(old_fees.keys() | new_fees.keys())]})
    return {'items': rows, 'reference_gross_fen': request['snapshot']['reference_gross_fen'],
            'actual_gross_fen': statement['gross_fen'] if statement else None,
            'adjustment_before_fen': request['snapshot']['adjustment_fen'], 'adjustment_after_fen': statement['adjustment_fen'] if statement else None,
            'reason': statement['review'].get('difference_reason', '') if statement and statement['review'] else ''}


def recovery_preview(actor, identifier):
    with db(read_only_snapshot=True) as conn:
        row = settlements.request_row(conn, identifier, actor)
        return recovery_candidates(conn, row)


def recovery_candidates(conn, row):
    if row['status'] not in ('invalidated', 'rejected', 'cancelled'):
        fail('只有失效、退回或撤回的申请可以重新核算', 409)
    kept, excluded = [], []
    rewards = {reward['order_id']: reward for reward in settlements.reward_orders(conn, order_ids=[item['order_id'] for item in row['snapshot']['items']])}
    now = time.time()
    for item in row['snapshot']['items']:
        reward = rewards.get(item['order_id'])
        if reward is None:
            fail('奖励不存在', 404)
        try:
            if reward['request_id'] or reward['statement_id']:
                fail('已进入其他申请或结算单', 409)
            settlements.require_available(reward, now)
        except HTTPException as error:
            if error.status_code != 409:
                raise
            excluded.append({'order_id': item['order_id'], 'reason': error.detail['error'] if isinstance(error.detail, dict) else str(error.detail)})
        else:
            kept.append(item['order_id'])
    return {'order_ids': kept, 'excluded': excluded, 'revision': row['revision']}


def recover(actor, identifier, body):
    with db(serialized='accounts') as conn:
        row = settlements.request_row(conn, identifier, actor)
        if row['revision'] != body.revision:
            fail('原申请已变化，请刷新后重新核算', 409)
        result = recovery_candidates(conn, row)
        if not result['order_ids']:
            fail('没有可以重新申请的订单', 422)
        owner = int(row['beneficiary'].split(':')[1])
        quote = settlements._request_quote(conn, owner, result['order_ids'])
        key, now = uuid.uuid4().hex, int(time.time())
        snapshot = {**quote['snapshot'], 'source_request_id': identifier, 'recovery_excluded': result['excluded']}
        conn.execute('INSERT INTO referral_settlement_requests(id,beneficiary,beneficiary_name,request_key,quote_digest,snapshot,note,created_at,updated_at) VALUES(?,?,?,?,?,?::jsonb,?,?,?)',
                     (key, row['beneficiary'], row['beneficiary_name'], 'recover-' + key, quote['quote_digest'], json.dumps(snapshot), body.reason, now, now))
        for order_id in result['order_ids']:
            conn.execute('UPDATE referral_rewards SET request_id=?,revision=revision+1 WHERE order_id=?', (key, order_id))
        conn.execute('UPDATE referral_settlement_requests SET revision=revision+1 WHERE id=?', (identifier,))
        settlements.audit(conn, actor, 'request_recovered', key, {'source_request_id': identifier, 'reason': body.reason, **result})
        settlements.audit(conn, actor, 'recovery_created', identifier, {'new_request_id': key, 'reason': body.reason})
        return dict(settlements.request_row(conn, key, actor))


def timeline(conn, targets):
    return [dict(row) for row in conn.execute('SELECT a.id,a.kind,a.target,a.value,a.created_at,u.username AS actor_name '
        'FROM referral_settlement_audit a LEFT JOIN users u ON u.id=a.actor_id WHERE a.target=ANY(?) ORDER BY a.id DESC LIMIT 200', (targets,))]


def statement_detail(actor, identifier):
    with db() as conn:
        row = owned_statement(conn, actor, identifier)
        from app.services.settlement_bills import statement_differences
        from app.services.settlement_disputes import blockers
        issues = [{'order_id': item['target_id'], 'reasons': ['未处理结算异议：' + item['title']]} for item in blockers(conn, row)]
        batch = conn.execute("SELECT batch_id FROM referral_payout_batch_items WHERE statement_id=? AND status IN ('pending','failed')", (identifier,)).fetchone()
        if batch:
            issues.append({'order_id': row['id'], 'purpose': 'payment', 'reasons': ['此结算单已进入付款批次，请在原批次登记回单或取消剩余批次']})
        if settlement_access.owner_id(conn, actor) is None:
            for check, purpose in ((settlement_access.check_review, '审核'), (settlement_access.check_payment, '付款')):
                try:
                    check(conn, actor, row)
                except HTTPException as e:
                    reason = e.detail.get('error', str(e.detail)) if isinstance(e.detail, dict) else str(e.detail)
                    issues.append({'order_id': row['id'], 'purpose': 'review' if purpose == '审核' else 'payment', 'reasons': [purpose + '：' + reason]})
        return {'statement': dict(row), 'attachments': attachments(conn, identifier), 'timeline': timeline(conn, [identifier]),
                'payout_batch_id': batch['batch_id'] if batch else None,
                'operation_issues': issues,
                'bill_differences': statement_differences(conn, row) if settlement_access.owner_id(conn, actor) is None else []}


def notices(actor, personal=False):
    with db() as conn:
        owner = settlement_access.owner_id(conn, actor)
        if personal:
            owner = actor
        args: list[Any]
        visible, args = ('TRUE', []) if owner is None else ("""(EXISTS(SELECT 1 FROM referral_settlement_requests r WHERE r.id=a.target AND r.beneficiary=?)
            OR EXISTS(SELECT 1 FROM referral_statements s WHERE s.id=a.target AND s.beneficiary=?)
            OR a.value->>'beneficiary'=?)""", ['admin:' + str(owner)] * 3)
        kinds = ['apply_settlement', 'settlement_request_rejected', 'settlement_request_invalidated', 'approve', 'record_payout', 'request_recovered', 'dispute_created', 'dispute_replied']
        clause = f'({visible}) AND a.kind=ANY(?)'
        args.append(kinds)
        cursor = 'COALESCE(personal_last_id,last_id)' if personal else 'last_id'
        last = conn.execute(f'SELECT {cursor} AS last_id FROM referral_notice_reads WHERE actor_id=?', (actor,)).fetchone()
        last_id = last['last_id'] if last else 0
        count = conn.execute(f'SELECT COUNT(*) FROM referral_settlement_audit a WHERE {clause} AND a.id>?', [*args, last_id]).fetchone()[0]
        items = [dict(row) for row in conn.execute(f'SELECT a.id,a.kind,a.target,a.created_at FROM referral_settlement_audit a WHERE {clause} ORDER BY a.id DESC LIMIT 30', args)]
        return {'unread': count, 'last_id': last_id, 'items': items}


def read_notices(actor, through, personal=False):
    visible = notices(actor, personal)
    maximum = max([item['id'] for item in visible['items']] + [visible['last_id']])
    if through > maximum:
        fail('消息已变化，请刷新', 409)
    with db(serialized='accounts') as conn:
        if personal:
            conn.execute('INSERT INTO referral_notice_reads(actor_id,last_id,personal_last_id) VALUES(?,0,?) ON CONFLICT(actor_id) DO UPDATE SET personal_last_id=GREATEST(COALESCE(referral_notice_reads.personal_last_id,referral_notice_reads.last_id),excluded.personal_last_id)', (actor, through))
        else:
            conn.execute('INSERT INTO referral_notice_reads(actor_id,last_id,personal_last_id) VALUES(?,?,0) ON CONFLICT(actor_id) DO UPDATE SET personal_last_id=COALESCE(referral_notice_reads.personal_last_id,referral_notice_reads.last_id),last_id=GREATEST(referral_notice_reads.last_id,excluded.last_id)', (actor, through))
    return {'ok': True}
