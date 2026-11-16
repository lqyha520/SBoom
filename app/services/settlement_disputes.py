"""按推广人隔离的异议线程；处理意见不直接改动历史金额。"""

import hashlib
import time
import uuid

from app.db import db
from app.services import settlement_access, settlements
from app.services.mini_errors import fail


def owned(conn, actor, identifier, personal=False):
    row = conn.execute('SELECT * FROM referral_disputes WHERE id=?', (identifier,)).fetchone()
    owner = settlement_access.owner_id(conn, actor)
    if personal:
        owner = actor
    if not row or owner is not None and row['beneficiary'] != 'admin:' + str(owner):
        fail('异议不存在', 404)
    return row


def detail(conn, actor, identifier, personal=False):
    row = owned(conn, actor, identifier, personal)
    return {**dict(row), 'messages': [dict(r) for r in conn.execute('SELECT m.id,m.actor_id,u.username AS actor_name,m.content,m.evidence,m.created_at FROM referral_dispute_messages m LEFT JOIN users u ON u.id=m.actor_id WHERE dispute_id=? ORDER BY m.id', (identifier,))],
            'files': [dict(r) for r in conn.execute('SELECT id,name,media_type,created_at FROM referral_dispute_files WHERE dispute_id=? ORDER BY created_at,id', (identifier,))]}


def listing(actor, status='', page=1, personal=False):
    with db(read_only_snapshot=True) as conn:
        where, args = settlements.scope(conn, actor)
        if personal:
            where += ' AND beneficiary=?'
            args.append('admin:' + str(actor))
        if status:
            where += ' AND status=?'
            args.append(status)
        total = conn.execute(f'SELECT COUNT(*) FROM referral_disputes WHERE {where}', args).fetchone()[0]
        rows = conn.execute(f'SELECT id FROM referral_disputes WHERE {where} ORDER BY updated_at DESC,id LIMIT 20 OFFSET ?', [*args, (page - 1) * 20]).fetchall()
        return {'items': [detail(conn, actor, row[0]) for row in rows], 'total': total}


def create(actor, body):
    with db(serialized='accounts') as conn:
        settlement_access.identity(conn, actor)
        table, field = ('referral_rewards', 'order_id') if body.target_kind == 'reward' else ('referral_statements', 'id')
        target = conn.execute(f'SELECT beneficiary FROM {table} WHERE {field}=?', (body.target_id,)).fetchone()
        # 只有收益所属人发起；财务通过回复处理。
        if not target or target[0] != 'admin:' + str(actor):
            fail('只能对本人的奖励或结算单发起异议', 404)
        prior = conn.execute('SELECT * FROM referral_disputes WHERE beneficiary=? AND request_key=?', (target[0], body.request_key)).fetchone()
        if prior:
            first = conn.execute('SELECT content,evidence FROM referral_dispute_messages WHERE dispute_id=? ORDER BY id LIMIT 1', (prior['id'],)).fetchone()
            if (prior['target_kind'], prior['target_id'], prior['title'], first['content'], first['evidence']) != (body.target_kind, body.target_id, body.title, body.content, body.evidence):
                fail('请求编号已用于其他异议', 409)
            return detail(conn, actor, prior['id'])
        if conn.execute("SELECT 1 FROM referral_disputes WHERE beneficiary=? AND target_kind=? AND target_id=? AND status IN ('open','processing')", (target[0], body.target_kind, body.target_id)).fetchone():
            fail('此记录已有未处理异议，请在原异议补充说明', 409)
        key, now = uuid.uuid4().hex, int(time.time())
        conn.execute('INSERT INTO referral_disputes(id,beneficiary,target_kind,target_id,title,request_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)', (key, target[0], body.target_kind, body.target_id, body.title, body.request_key, now, now))
        conn.execute('INSERT INTO referral_dispute_messages(dispute_id,actor_id,content,evidence,created_at) VALUES(?,?,?,?,?)', (key, actor, body.content, body.evidence, now))
        settlements.audit(conn, actor, 'dispute_created', key, {'beneficiary': target[0], 'target': body.target_id})
        return detail(conn, actor, key)


def reply(actor, identifier, body):
    with db(serialized='accounts') as conn:
        row = owned(conn, actor, identifier)
        if row['revision'] != body.revision or row['status'] in ('resolved', 'rejected'):
            fail('异议已变化或已结束，请刷新；新问题可重新发起', 409)
        finance = settlement_access.identity(conn, actor)
        from app.admin_permissions import allowed
        reviewer = allowed(finance, 'settlementReview', 'run')
        if not reviewer and (row['beneficiary'] != 'admin:' + str(actor) or body.status != row['status']):
            fail('只有审核人员可以处理或结束异议', 403)
        if reviewer and body.status == 'open' and row['status'] == 'processing':
            fail('处理中的异议不能退回未处理状态', 409)
        now = int(time.time())
        conn.execute('INSERT INTO referral_dispute_messages(dispute_id,actor_id,content,evidence,created_at) VALUES(?,?,?,?,?)', (identifier, actor, body.content, body.evidence, now))
        conn.execute('UPDATE referral_disputes SET status=?,revision=revision+1,updated_at=? WHERE id=?', (body.status, now, identifier))
        settlements.audit(conn, actor, 'dispute_replied', identifier, {'beneficiary': row['beneficiary'], 'status': body.status})
        return detail(conn, actor, identifier)


def blockers(conn, row):
    ids = [item['order_id'] for item in row['snapshot']['items']]
    return [dict(r) for r in conn.execute("SELECT id,title,target_id FROM referral_disputes WHERE status IN ('open','processing') AND ((target_kind='statement' AND target_id=?) OR (target_kind='reward' AND target_id=ANY(?)))", (row['id'], ids))]


def upload(actor, identifier, name, content):
    from app.services.settlement_operations import validate_attachment
    name, media = validate_attachment(name, content)
    digest = hashlib.sha256(content).hexdigest()
    with db(serialized='accounts') as conn:
        row = owned(conn, actor, identifier)
        if row['beneficiary'] != 'admin:' + str(actor):
            settlement_access.authorize(conn, actor, 'Review')
        if row['status'] in ('resolved', 'rejected'):
            fail('已结束的异议不能添加凭据', 409)
        prior = conn.execute('SELECT id FROM referral_dispute_files WHERE dispute_id=? AND digest=?', (identifier, digest)).fetchone()
        if prior:
            return {'id': prior[0]}
        if conn.execute('SELECT COUNT(*) FROM referral_dispute_files WHERE dispute_id=?', (identifier,)).fetchone()[0] >= 5:
            fail('每个异议最多 5 个附件', 422)
        key, now = uuid.uuid4().hex, int(time.time())
        conn.execute('INSERT INTO referral_dispute_files(id,dispute_id,name,media_type,digest,content,created_at) VALUES(?,?,?,?,?,?,?)', (key, identifier, name, media, digest, content, now))
        conn.execute('UPDATE referral_disputes SET revision=revision+1,updated_at=? WHERE id=?', (now, identifier))
        settlements.audit(conn, actor, 'dispute_attachment', identifier, {'beneficiary': row['beneficiary'], 'name': name})
        return {'id': key}


def file(actor, identifier):
    with db() as conn:
        row = conn.execute('SELECT * FROM referral_dispute_files WHERE id=?', (identifier,)).fetchone()
        if not row:
            fail('附件不存在', 404)
        owned(conn, actor, row['dispute_id'])
        return dict(row)
