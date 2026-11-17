"""首次注册绑定、管理员推广统计与历史来源补录。"""

import csv
import io
import json
import secrets
import time

import httpx

from app.db import db
from app.services import catalog_scope, wechat_notices
from app.services.mini_errors import fail
from app.services.referral_metrics import STAGES, progress_join
from app.sql_utils import escape_like

SOURCE_LABELS = {'legacy': '历史来源未知', 'natural': '自然注册', 'admin': '管理员推广', 'user': '用户邀请', 'manual': '人工补录'}


def code(kind='u'):
    return kind + '_' + secrets.token_hex(10)


def attribution(conn, referral_code=''):
    result = {'source': 'natural', 'bound_at': int(time.time())}
    if not referral_code:
        return result
    if referral_code.startswith('a_'):
        campaign = conn.execute("SELECT c.*,u.username FROM referral_campaigns c JOIN users u ON u.id=c.admin_id WHERE c.code=? AND c.active AND u.is_active=1 AND u.role='admin'", (referral_code,)).fetchone()
        if campaign:
            return {**result, 'source': 'admin', 'code': referral_code, 'admin_id': campaign['admin_id'], 'admin_name': campaign['username'],
                    'inviter_type': 'admin', 'inviter_id': str(campaign['admin_id']), 'inviter_name': campaign['username'],
                    'campaign_id': campaign['id'], 'campaign_name': campaign['name'], 'campaign_source': campaign['source']}
        row = conn.execute("SELECT id,username FROM users WHERE referral_code=? AND role='admin' AND is_active=1", (referral_code,)).fetchone()
        if row:
            return {**result, 'source': 'admin', 'code': referral_code, 'admin_id': row['id'], 'admin_name': row['username'],
                    'inviter_type': 'admin', 'inviter_id': str(row['id']), 'inviter_name': row['username']}
    elif referral_code.startswith('u_'):
        row = conn.execute('SELECT id,username,referral FROM mini_users WHERE referral_code=? AND is_active=1', (referral_code,)).fetchone()
        if row:
            return {**result, **{key: row['referral'][key] for key in ('campaign_id', 'campaign_name', 'campaign_source') if key in row['referral']}, 'source': 'user', 'code': referral_code, 'admin_id': row['referral'].get('admin_id'),
                    'admin_name': row['referral'].get('admin_name', ''), 'inviter_type': 'user',
                    'inviter_id': row['id'], 'inviter_name': row['username']}
    # 无效、已删除或停用的推广人不能阻断正常注册，也不能伪造归属。
    return result


def initialize_user(conn, user_id, referral_code=''):
    conn.execute('UPDATE mini_users SET referral_code=?,referral=?::jsonb WHERE id=?',
                 (code(), json.dumps(attribution(conn, referral_code)), user_id))


def admin_code(actor_id, target_id=None):
    with db(serialized='accounts') as conn:
        owner = catalog_scope.owner_id(conn, actor_id)
        target_id = target_id or actor_id
        if owner is not None and target_id != owner:
            fail('不能获取其他管理员的推广码', 403)
        row = conn.execute("SELECT id,username,referral_code FROM users WHERE id=? AND role='admin' AND is_active=1 FOR UPDATE", (target_id,)).fetchone()
        if not row:
            fail('管理员不存在或已停用', 404)
        value = row['referral_code'] or code('a')
        if not row['referral_code']:
            conn.execute('UPDATE users SET referral_code=? WHERE id=?', (value, target_id))
    return {'code': value, 'admin_id': target_id, 'admin_name': row['username'], 'path': 'pages/home/index?ref=' + value}


def admins(actor_id):
    with db() as conn:
        owner = catalog_scope.owner_id(conn, actor_id)
        rows = conn.execute("SELECT id,username,is_active FROM users WHERE role='admin'" + (' AND id=?' if owner is not None else '') + ' ORDER BY id',
                            (owner,) if owner is not None else ()).fetchall()
    return {'items': [dict(row) for row in rows]}


def scope(conn, actor_id, admin_id=None, alias='u'):
    owner = catalog_scope.owner_id(conn, actor_id)
    if owner is not None:
        if admin_id is not None and admin_id != owner:
            fail('不能查看其他管理员的推广数据', 403)
        admin_id = owner
    if admin_id == 0:
        return f"{alias}.referral->>'admin_id' IS NULL", []
    return (f"{alias}.referral->>'admin_id'=?", [str(admin_id)]) if admin_id is not None else ('1=1', [])


def date_filter(clauses, args, alias, start_date, end_date):
    from datetime import date, datetime, timedelta, timezone
    try:
        zone = timezone(timedelta(hours=8))
        if start_date and end_date and date.fromisoformat(start_date) > date.fromisoformat(end_date):
            raise ValueError
        for value, operator, delta in ((start_date, '>=', 0), (end_date, '<', 1)):
            if value:
                stamp = datetime.combine(date.fromisoformat(value) + timedelta(days=delta), datetime.min.time(), zone)
                clauses.append(f'{alias}.created_at {operator} ?')
                args.append(int(stamp.timestamp()))
    except (ValueError, OverflowError):
        fail('日期范围无效', 422)


def users(actor_id, admin_id=None, q='', start_date='', end_date='', limit=20, offset=0, campaign_id='', date_basis='created', stage='all', as_of=None):
    with db() as conn:
        where, args = scope(conn, actor_id, admin_id)
        observed = min(as_of or int(time.time()), int(time.time()))
        clauses = [where, 'u.created_at<=t.at', STAGES[stage]]
        date_filter(clauses, args, 'u', start_date, end_date)
        if campaign_id:
            clauses.append("u.referral->>'campaign_id'=?")
            args.append(campaign_id)
        if q:
            clauses.append("(LOWER(u.username) LIKE ? ESCAPE '\\' OR LOWER(u.nickname) LIKE ? ESCAPE '\\')")
            args.extend(['%' + escape_like(q.lower()) + '%'] * 2)
        where = ' AND '.join(clauses)
        source = f'FROM mini_users u CROSS JOIN (SELECT ?::bigint AS at) t {progress_join()} WHERE {where}'
        total = conn.execute(f'SELECT COUNT(*) {source}', [observed, *args]).fetchone()[0]
        rows = conn.execute(f'''SELECT u.id,u.username,u.nickname,u.created_at,u.referral,
            CASE WHEN progress.paid THEN 'paid' WHEN progress.ordered THEN 'unpaid' ELSE 'not_ordered' END AS stage,
            progress.last_order_at,progress.last_paid_at {source}
            ORDER BY u.created_at DESC,u.id DESC LIMIT ? OFFSET ?''', [observed, *args, limit, offset]).fetchall()
    return {'items': [dict(row) for row in rows], 'total': total, 'has_more': offset + len(rows) < total}


def orders(actor_id, admin_id=None, **filters):
    from app.services.mini_orders import listing
    return listing(admin_actor_id=actor_id, referral_admin_id=admin_id, real_only=True, **filters)


def require_order(actor_id, identifier, *, refund=False):
    with db() as conn:
        where, args = scope(conn, actor_id, alias='o')
        target = 'o.id=(SELECT order_id FROM mini_refunds WHERE id=?)' if refund else 'o.id=?'
        if not conn.execute(f'SELECT 1 FROM mini_orders o WHERE {target} AND ({where})', [identifier, *args]).fetchone():
            fail('订单不存在或不在当前账号的管理范围内', 404)


def summary(actor_id, admin_id=None, start_date='', end_date=''):
    with db() as conn:
        where, args = scope(conn, actor_id, admin_id)
        clauses = [where]
        date_filter(clauses, args, 'u', start_date, end_date)
        registrations = conn.execute('SELECT COUNT(*) FROM mini_users u WHERE ' + ' AND '.join(clauses), args).fetchone()[0]
        where, args = scope(conn, actor_id, admin_id, 'o')
        clauses = [where]
        date_filter(clauses, args, 'o', start_date, end_date)
        value = dict(conn.execute("SELECT COUNT(*) AS orders, COUNT(DISTINCT CASE WHEN o.paid_at IS NOT NULL THEN COALESCE(o.referral->>'buyer_id', o.user_id) END) AS paying_users, "
                                 "COALESCE(SUM(CASE WHEN o.paid_at IS NOT NULL THEN o.amount_fen ELSE 0 END),0) AS paid_fen, "
                                 "COALESCE(SUM(CASE WHEN o.status='refunded' THEN o.amount_fen ELSE 0 END),0) AS refunded_fen "
                                 'FROM mini_orders o WHERE ' + ' AND '.join(clauses), args).fetchone())
    return {**value, 'registrations': registrations, 'net_fen': value['paid_fen'] - value['refunded_fen']}


def supplement(actor_id, user_id, admin_id, reason):
    with db(serialized='accounts') as conn:
        if catalog_scope.owner_id(conn, actor_id) is not None:
            fail('仅超级管理员可以补录来源', 403)
        row = conn.execute('SELECT referral FROM mini_users WHERE id=? FOR UPDATE', (user_id,)).fetchone()
        if not row:
            fail('用户不存在', 404)
        if row['referral'].get('source') != 'legacy':
            fail('仅可补录历史来源未知的用户，已绑定的来源不能覆盖', 409)
        admin = conn.execute("SELECT id,username FROM users WHERE id=? AND role='admin' AND is_active=1", (admin_id,)).fetchone()
        if not admin:
            fail('归属管理员不存在或已停用', 422)
        after = {'source': 'manual', 'admin_id': admin_id, 'admin_name': admin['username'], 'bound_at': int(time.time())}
        conn.execute('UPDATE mini_users SET referral=?::jsonb WHERE id=?', (json.dumps(after), user_id))
        conn.execute('INSERT INTO mini_referral_audit(actor_id,user_id,before_json,after_json,reason,created_at) VALUES (?,?,?::jsonb,?::jsonb,?,?)',
                     (actor_id, user_id, json.dumps(row['referral']), json.dumps(after), reason, after['bound_at']))
    return after


def audit(actor_id, user_id):
    with db() as conn:
        if catalog_scope.owner_id(conn, actor_id) is not None:
            fail('仅超级管理员可以查看补录记录', 403)
        return {'items': [dict(row) for row in conn.execute('SELECT a.*,u.username AS actor_name FROM mini_referral_audit a LEFT JOIN users u ON u.id=a.actor_id WHERE a.user_id=? ORDER BY a.id DESC', (user_id,))]}


def export_users(actor_id, **filters):
    page = users(actor_id, limit=5000, **filters)
    if page['total'] > 5000:
        fail('结果超过 5000 条，请缩小筛选范围', 422)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['账号', '昵称', '来源', '直接邀请人', '归属管理员', '活动名称', '来源渠道', '转化状态', '注册时间戳', '最近下单时间戳', '最近付费时间戳'])
    for item in page['items']:
        value = item['referral']
        writer.writerow([csv_safe(v) for v in [item['username'], item['nickname'], SOURCE_LABELS.get(value['source'], ''),
                                              value.get('inviter_name', ''), value.get('admin_name', ''), value.get('campaign_name', ''), value.get('campaign_source', ''),
                                              {'paid': '已付费', 'unpaid': '下单未付', 'not_ordered': '尚未下单'}[item['stage']],
                                              item['created_at'], item['last_order_at'], item['last_paid_at']]])
    return '\ufeff' + output.getvalue()


def csv_safe(value):
    value = str(value or '')
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')) else value


def qrcode(actor_id, target_id=None, env_version='release', campaign_id=''):
    from app.config import get_settings
    if not get_settings().wechat_app_id or not get_settings().wechat_app_secret:
        fail('尚未配置微信小程序 AppID 和密钥，无法生成小程序码', 503)
    if campaign_id:
        from app.services.referral_operations import campaign_code
        value = campaign_code(actor_id, campaign_id)
    else:
        value = admin_code(actor_id, target_id)
    try:
        response = wechat_notices._http_client().post('https://api.weixin.qq.com/wxa/getwxacodeunlimit',
            params={'access_token': wechat_notices.access_token()},
            json={'scene': value['code'], 'page': 'pages/home/index', 'check_path': True, 'env_version': env_version, 'width': 430}, timeout=15)
        response.raise_for_status()
        if response.content.startswith(b'\x89PNG\r\n\x1a\n'):
            return response.content, 'image/png'
        if response.content.startswith(b'\xff\xd8\xff'):
            return response.content, 'image/jpeg'
    except (httpx.HTTPError, ValueError, KeyError):
        pass
    fail('微信小程序码生成失败，请核对小程序配置、服务器 IP 白名单及所选版本是否已上传', 502)
