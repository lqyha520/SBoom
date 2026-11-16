"""财务授权只扩大结算范围，不扩大会员、推广或内容管理范围。"""

from app.admin_permissions import allowed, require
from app.services import user_store
from app.services.catalog_scope import owner_id as admin_owner
from app.services.mini_errors import fail

MENUS = ('settlementCosts', 'settlementReview', 'settlementPayout')


def identity(conn, actor):
    admin_owner(conn, actor)
    return user_store.from_row(conn.execute('SELECT * FROM users WHERE id=?', (actor,)).fetchone())


def owner_id(conn, actor):
    user = identity(conn, actor)
    return None if any(allowed(user, menu) for menu in MENUS) else actor


def authorize(conn, actor, stage, action='run'):
    require(identity(conn, actor), 'settlement' + stage, action)


def controls(conn):
    return dict(conn.execute('SELECT revision,separate_review,separate_payment FROM referral_finance_controls WHERE id=1').fetchone())


def check_review(conn, actor, row):
    if controls(conn)['separate_review']:
        preparers = {item['costs'].get('confirmed_by') for item in row['snapshot']['items']}
        preparers.update(r[0] for r in conn.execute("SELECT actor_id FROM referral_settlement_audit WHERE target=? AND kind='create_statement'", (row['id'],)))
        if actor in preparers:
            fail('已启用独立复核，费用核对人和制单人不能审核此单', 409)


def check_payment(conn, actor, row):
    if controls(conn)['separate_payment'] and (row['review'] or {}).get('confirmed_by') == actor:
        fail('已启用独立付款，审核人不能登记此单付款', 409)
