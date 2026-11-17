"""原始凭据的两种分摊口径分别封顶；复用现有费用事实，不重记资金账。"""

import hashlib
import time
import uuid

from app.admin_permissions import allowed
from app.db import db
from app.services import settlement_access, settlements
from app.services.mini_errors import fail
from app.sql_utils import escape_like


def access(conn, actor, owner, write=False):
    user = settlement_access.identity(conn, actor)
    financial = allowed(user, 'settlementCosts', 'run' if write else 'view')
    if not write:
        financial = financial or any(allowed(user, menu) for menu in ('settlementReview', 'settlementPayout'))
    if not financial and (owner != actor or not allowed(user, 'referrals', 'create' if write else 'view')):
        fail('未获授权查看或维护此凭据', 403)


def root_ref(value):
    return settlements.cost_reference(value).split('/', 1)[0]


USAGES = """
    SELECT 'expense' AS kind,e.id,e.amount_fen,c.admin_id,e.source_ref
    FROM referral_campaign_expenses e JOIN referral_campaigns c ON c.id=e.campaign_id
    WHERE e.active AND split_part(e.source_ref,'/',1)=?
    UNION ALL
    SELECT 'shared',r.order_id,(f->>'amount_fen')::bigint,split_part(r.beneficiary,':',2)::integer,f->>'source_ref'
    FROM referral_rewards r CROSS JOIN LATERAL jsonb_array_elements(COALESCE(r.costs->'shared_fees','[]'::jsonb)) f
    WHERE split_part(f->>'source_ref','/',1)=? AND (r.status<>'void' OR EXISTS(
        SELECT 1 FROM referral_statements s WHERE s.id=r.statement_id AND s.status='paid'))
    UNION ALL
    SELECT 'personal',s.id,(f->>'amount_fen')::bigint,split_part(s.beneficiary,':',2)::integer,f->>'source_ref'
    FROM referral_statements s CROSS JOIN LATERAL jsonb_array_elements(COALESCE(s.review->'personal_fees','[]'::jsonb)) f
    WHERE s.status IN ('approved','paid') AND split_part(f->>'source_ref','/',1)=?
"""


def usage(conn, row):
    args = [row['reference']] * 3
    result = conn.execute(f"""SELECT COUNT(*) AS count,
        COALESCE(SUM(amount_fen) FILTER(WHERE kind='expense'),0) AS expense_fen,
        COALESCE(SUM(amount_fen) FILTER(WHERE kind<>'expense'),0) AS deduction_fen,
        COUNT(*) FILTER(WHERE admin_id<>?) AS foreign_count FROM ({USAGES}) entries""", [row['admin_id'], *args]).fetchone()
    return {key: int(value) for key, value in result.items()}


def validate_references(conn, references):
    roots = sorted({root_ref(ref) for ref in references if ref})
    if not roots:
        return
    for row in conn.execute('SELECT * FROM referral_cost_vouchers WHERE reference=ANY(?)', (roots,)):
        used = usage(conn, row)
        if used['foreign_count']:
            fail('凭据归属与费用所属管理员不一致，请核对凭据号', 422)
        if max(used['expense_fen'], used['deduction_fen']) > row['total_fen']:
            fail('凭据 ' + row['reference'] + ' 的成本归集或奖励扣费分摊已超过原始总额', 422)


def owned(conn, actor, identifier, write=False):
    row = conn.execute('SELECT * FROM referral_cost_vouchers WHERE id=?', (identifier,)).fetchone()
    if not row:
        fail('凭据不存在', 404)
    access(conn, actor, row['admin_id'], write)
    return row


def detail(conn, actor, identifier):
    row = owned(conn, actor, identifier)
    used = usage(conn, row)
    files = [dict(item) for item in conn.execute('SELECT id,name,media_type,created_at FROM referral_cost_voucher_files WHERE voucher_id=? ORDER BY created_at,id', (identifier,))]
    entries = [dict(item) for item in conn.execute(f'SELECT * FROM ({USAGES}) entries ORDER BY kind,id,source_ref LIMIT 100', [row['reference']] * 3)]
    return {**dict(row), **used, 'expense_remaining_fen': row['total_fen'] - used['expense_fen'],
            'deduction_remaining_fen': row['total_fen'] - used['deduction_fen'], 'entries': entries, 'files': files}


def listing(actor, admin_id=None, q='', page=1):
    with db(read_only_snapshot=True) as conn:
        user = settlement_access.identity(conn, actor)
        financial = any(allowed(user, menu) for menu in settlement_access.MENUS)
        owner = admin_id if financial else actor
        access(conn, actor, owner or actor)
        where, args = 'TRUE', []
        if owner:
            where += ' AND admin_id=?'
            args.append(owner)
        if q.strip():
            where += " AND (name ILIKE ? ESCAPE '\\' OR reference ILIKE ? ESCAPE '\\')"
            args.extend(['%' + escape_like(q.strip()) + '%'] * 2)
        count = conn.execute(f'SELECT COUNT(*) FROM referral_cost_vouchers WHERE {where}', args).fetchone()[0]
        page = min(page, max(1, (count + 19) // 20))
        rows = conn.execute(f'SELECT id FROM referral_cost_vouchers WHERE {where} ORDER BY created_at DESC,id LIMIT 20 OFFSET ?', [*args, (page - 1) * 20])
        return {'items': [detail(conn, actor, item['id']) for item in rows], 'total': count, 'page': page}


def save(actor, body, identifier=None):
    reference = settlements.cost_reference(body.reference)
    if '/' in reference or len(reference) < 2:
        fail('原始凭据号至少两位且不能包含斜杠；费用项在分摊时填写', 422)
    with db(serialized='accounts') as conn:
        access(conn, actor, body.admin_id, True)
        if not conn.execute("SELECT 1 FROM users WHERE id=? AND role='admin'", (body.admin_id,)).fetchone():
            fail('凭据所属管理员不存在', 422)
        if identifier:
            row = owned(conn, actor, identifier, True)
            if row['revision'] != body.revision:
                fail('凭据已更新，请刷新后核对再保存', 409)
            if row['reference'] != reference or row['admin_id'] != body.admin_id:
                fail('已登记凭据的编号和归属不可更改', 422)
            conn.execute('UPDATE referral_cost_vouchers SET name=?,total_fen=?,evidence=?,revision=revision+1 WHERE id=?', (body.name, body.total_fen, body.evidence, identifier))
        else:
            prior = conn.execute('SELECT * FROM referral_cost_vouchers WHERE reference=?', (reference,)).fetchone()
            if prior:
                if (prior['admin_id'], prior['name'], prior['total_fen'], prior['evidence']) != (body.admin_id, body.name, body.total_fen, body.evidence):
                    fail('凭据号已登记，请核对或修改原凭据', 409)
                return detail(conn, actor, prior['id'])
            identifier = uuid.uuid4().hex
            conn.execute('INSERT INTO referral_cost_vouchers(id,admin_id,reference,name,total_fen,evidence,created_at) VALUES(?,?,?,?,?,?,?)',
                         (identifier, body.admin_id, reference, body.name, body.total_fen, body.evidence, int(time.time())))
        validate_references(conn, [reference])
        settlements.audit(conn, actor, 'cost_voucher_saved', identifier, body.model_dump())
        return detail(conn, actor, identifier)


def upload(actor, identifier, name, content):
    from app.services.settlement_operations import validate_attachment
    name, media = validate_attachment(name, content)
    digest = hashlib.sha256(content).hexdigest()
    with db(serialized='accounts') as conn:
        owned(conn, actor, identifier, True)
        prior = conn.execute('SELECT id FROM referral_cost_voucher_files WHERE voucher_id=? AND digest=?', (identifier, digest)).fetchone()
        if prior:
            return {'id': prior['id']}
        if conn.execute('SELECT COUNT(*) FROM referral_cost_voucher_files WHERE voucher_id=?', (identifier,)).fetchone()[0] >= 5:
            fail('每份原始凭据最多 5 个附件', 422)
        key = uuid.uuid4().hex
        conn.execute('INSERT INTO referral_cost_voucher_files(id,voucher_id,name,media_type,digest,content,created_at) VALUES(?,?,?,?,?,?,?)',
                     (key, identifier, name, media, digest, content, int(time.time())))
        settlements.audit(conn, actor, 'cost_voucher_file', identifier, {'name': name, 'digest': digest})
        return {'id': key}


def file(actor, identifier):
    with db() as conn:
        row = conn.execute('SELECT * FROM referral_cost_voucher_files WHERE id=?', (identifier,)).fetchone()
        if not row:
            fail('附件不存在', 404)
        owned(conn, actor, row['voucher_id'])
        return dict(row)
