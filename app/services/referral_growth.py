"""活动落地入口、匿名访问批次及真实注册转化。"""

import time
import uuid

from app.db import db
from app.services import referrals
from app.services.mini_errors import fail
from app.services.referral_metrics import cohort_orders


def destination(row):
    kind, identifier = row['landing_kind'], row['landing_id']
    return '/pages/home/index' if kind == 'home' else f'/pages/{kind}/index?id={identifier}'


def validate_destination(conn, kind, identifier):
    if kind == 'home':
        if identifier:
            fail('首页无需填写内容编号', 422)
        return
    if not identifier:
        fail('请填写落地内容编号', 422)
    if kind == 'paper':
        from app.services.public_catalog import JOIN, VISIBLE
        exists = conn.execute(f'SELECT 1 FROM {JOIN} WHERE c.id=? AND {VISIBLE}', (identifier,)).fetchone()
    else:
        exists = conn.execute('SELECT 1 FROM site_topics WHERE id=? AND is_visible=1', (identifier,)).fetchone()
    if not exists:
        fail('落地内容不存在或尚未公开', 422)


def enter(code, entry_key):
    now = int(time.time())
    with db() as conn:
        relation = referrals.attribution(conn, code)
        if not relation.get('admin_id'):
            return {'visit_id': '', 'destination': '/pages/home/index', 'tracked': False}
        campaign = conn.execute('SELECT * FROM referral_campaigns WHERE id=?', (relation.get('campaign_id'),)).fetchone()
        target = '/pages/home/index'
        if campaign:
            try:
                validate_destination(conn, campaign['landing_kind'], campaign['landing_id'])
                target = destination(campaign)
            except Exception as error:
                from fastapi import HTTPException
                if not isinstance(error, HTTPException):
                    raise
                # 内容下架后仍允许正常进入首页，不阻断注册。
        row = conn.execute('INSERT INTO referral_visits(id,code,entry_key,admin_id,campaign_id,created_at) VALUES(?,?,?,?,?,?) '
                           'ON CONFLICT(code,entry_key) DO UPDATE SET entry_key=excluded.entry_key RETURNING id,created_at',
                           (uuid.uuid4().hex, code, entry_key, relation['admin_id'], relation.get('campaign_id'), now)).fetchone()
    return {'visit_id': row['id'], 'destination': target, 'tracked': True}


def start(visit_id):
    now = int(time.time())
    with db() as conn:
        conn.execute('UPDATE referral_visits SET started_at=COALESCE(started_at,?) WHERE id=? AND created_at>=?',
                     (now, visit_id, now - 7 * 86400))
    return {'ok': True}


def registered(conn, user_id, code, visit_id):
    if not code or not visit_id:
        return
    now = int(time.time())
    conn.execute("""UPDATE referral_visits v SET user_id=?,registered_at=?,started_at=COALESCE(v.started_at,?)
        FROM mini_users u WHERE u.id=? AND v.id=? AND v.code=? AND v.user_id IS NULL AND v.created_at>=?
        AND u.referral->>'admin_id'=v.admin_id::text
        AND u.referral->>'campaign_id' IS NOT DISTINCT FROM v.campaign_id""",
        (user_id, now, now, user_id, visit_id, code, now - 7 * 86400))


def acquisition(actor, admin_id=None, campaign_id='', start_date='', end_date=''):
    from app.services.referral_operations import campaign_scope
    with db() as conn:
        target = campaign_scope(conn, actor, admin_id)
        clauses, args = ['TRUE'], []
        if target is not None:
            clauses.append('v.admin_id=?')
            args.append(target)
        if campaign_id:
            clauses.append('v.campaign_id=?')
            args.append(campaign_id)
        referrals.date_filter(clauses, args, 'v', start_date, end_date)
        now = int(time.time())
        row = conn.execute(f"""SELECT COUNT(*) AS visits,COUNT(v.started_at) AS started,
            COUNT(v.registered_at) AS registered,
            COUNT(*) FILTER(WHERE EXISTS(SELECT 1 FROM mini_orders o WHERE {cohort_orders(str(now))}
                AND o.amount_fen>0 AND o.paid_at>=u.created_at AND o.paid_at<={now})) AS paid
            FROM referral_visits v LEFT JOIN mini_users u ON u.id=v.user_id WHERE {' AND '.join(clauses)}""", args).fetchone()
        since = conn.execute('SELECT started_at FROM referral_tracking_config WHERE id=1').fetchone()[0]
    return {**dict(row), 'tracking_since': since, 'as_of': now}
