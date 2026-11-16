"""推广注册批次转化与只读规则；所有数据写入隔离测试库。"""

import json
from datetime import UTC, datetime

import test_backend_growth as growth

from app.db import db
from app.models.referral_operations import CampaignInput, CampaignUpdate
from app.routers import referrals as referral_routes
from app.routers import settlements as settlement_routes
from app.services import admin_access, mini_auth, referral_conversion, referral_operations, user_store


def stamp(day):
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


class ReferralConversionContracts(growth.GrowthBase):
    configure = growth.CommerceContracts.configure

    def setUp(self):
        super().setUp()
        self.configure()
        self.client.app.include_router(referral_routes.router)
        self.client.app.include_router(settlement_routes.router)
        self.promoter = user_store.create_user('conversion-owner', 'test-password', role='admin')
        self.other_promoter = user_store.create_user('conversion-other', 'test-password', role='admin')
        self.a = self.campaign('家长群一期')
        self.b = self.campaign('线下活动')

    def campaign(self, name):
        return referral_operations.save_campaign(self.admin.id, CampaignInput(admin_id=self.promoter.id, name=name, source='家长群'))

    def reader(self, name, campaign, created='2026-11-02T00:00:00'):
        user = mini_auth.login_public_identity('conversion-' + name, referral_code=campaign['code'])['user']
        with db() as conn:
            conn.execute('UPDATE mini_users SET created_at=? WHERE id=?', (stamp(created), user['id']))
        return user

    def order(self, user, identifier, *, paid=False, sandbox=False, refunded=False):
        created = stamp('2026-11-05T00:00:00')
        with db() as conn:
            relation = conn.execute('SELECT referral FROM mini_users WHERE id=?', (user['id'],)).fetchone()[0]
            conn.execute("""INSERT INTO mini_orders(id,user_id,request_key,plan_id,plan_name,plan_days,amount_fen,
                status,appid,mchid,payment_channel,device_platform,virtual_env,created_at,expires_at,paid_at,updated_at,referral)
                VALUES(?,?,?,?,?,30,1990,?,'isolated-app','isolated-mch',?,'android',?,?,?,?,?,?::jsonb)""",
                (identifier, user['id'], identifier, self.plan['id'], '转化测试', 'refunded' if refunded else 'paid' if paid else 'created',
                 'virtual' if sandbox else 'wechat', 1 if sandbox else 0, created, created + 900,
                 created + 30 if paid else None, created, json.dumps(relation)))

    def test_one_registration_cohort_deduplicates_orders_excludes_sandbox_and_old_registrations(self):
        self.reader('no-order', self.a)
        ordered = self.reader('ordered', self.a)
        paid = self.reader('paid', self.a)
        sandbox = self.reader('sandbox', self.b)
        old = self.reader('old-registration', self.a, '2026-10-01T00:00:00')
        self.order(ordered, 'cohort-unpaid')
        self.order(paid, 'cohort-paid', paid=True)
        self.order(paid, 'cohort-repeat', paid=True, refunded=True)
        self.order(sandbox, 'cohort-sandbox', paid=True, sandbox=True)
        self.order(old, 'cohort-old-user-paid', paid=True)
        filters = {'admin_id': self.promoter.id, 'start_date': '2026-11-01', 'end_date': '2026-11-10'}
        result = referral_conversion.conversion(self.admin.id, **filters)
        self.assertEqual(result['summary'], {'registrations': 4, 'ordered_users': 2, 'paying_users': 1,
                         'not_ordered_users': 2, 'unpaid_users': 1, 'order_rate_bps': 5000,
                         'pay_rate_bps': 2500, 'order_pay_rate_bps': 5000})
        self.assertEqual((result['items'][0]['campaign_id'], result['items'][0]['pay_rate_bps']), (self.a['id'], 3333))
        narrowed = referral_conversion.conversion(self.admin.id, **filters, campaign_id=self.b['id'])
        self.assertEqual(narrowed['summary']['registrations'], 1)
        self.assertIsNone(narrowed['summary']['order_pay_rate_bps'])
        self.assertEqual(narrowed['summary']['pay_rate_bps'], 0)
        self.sign_in(self.admin)
        response = self.client.get('/api/v1/admin/referrals/conversion', params=filters)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['summary'], result['summary'])

    def test_permissions_empty_cohort_date_boundaries_and_changed_attribution(self):
        boundary = self.reader('boundary', self.a, '2026-10-31T16:00:00')
        self.reader('before-boundary', self.a, '2026-10-31T15:59:59')
        self.order(boundary, 'before-reattribution', paid=True)
        with db() as conn:
            conn.execute("UPDATE mini_orders SET referral=jsonb_set(referral,'{admin_id}',?::jsonb) WHERE id=?",
                         (json.dumps(self.other_promoter.id), 'before-reattribution'))
        admin_access.save_permissions(self.admin.id, self.promoter.id, 1, {'referrals': ['view']})
        self.sign_in(self.promoter)
        base = '/api/v1/admin/referrals/conversion'
        response = self.client.get(base, params={'start_date': '2026-11-01', 'end_date': '2026-11-01'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['summary']['registrations'], 1)
        self.assertEqual(response.json()['summary']['paying_users'], 0)
        self.assertEqual(self.client.get(base, params={'admin_id': self.other_promoter.id}).status_code, 403)
        self.assertEqual(self.client.get(base, params={'start_date': 'bad'}).status_code, 422)
        self.assertEqual(self.client.get(base, params={'start_date': '2026-11-10', 'end_date': '2026-11-01'}).status_code, 422)
        self.assertEqual(self.client.get(base, params={'page': 0}).status_code, 422)
        empty = self.client.get(base, params={'campaign_id': 'no-such-campaign'}).json()
        self.assertEqual(empty['summary']['registrations'], 0)
        self.assertIsNone(empty['summary']['pay_rate_bps'])
        self.assertEqual(empty['items'], [])
        self.assertEqual(self.client.get('/api/v1/admin/referrals/rules').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/admin/settlements/policy').status_code, 403)
        self.assertEqual(self.client.get('/api/v1/admin/settlements/rules').status_code, 403)
        admin_access.save_permissions(self.admin.id, self.promoter.id, 2, {'settlements': ['view']})
        self.assertEqual(self.client.get(base).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/admin/settlements/rules').status_code, 200)

    def test_group_pagination_keeps_full_cohort_denominator_and_current_campaign_names(self):
        for index in range(21):
            self.reader('page-' + str(index), self.campaign('分页活动' + str(index)))
        self.reader('renamed', self.a)
        referral_operations.save_campaign(self.admin.id, CampaignUpdate(admin_id=self.promoter.id, revision=1,
                    name='家长群新名称', source='家长群', active=False), self.a['id'])
        first = referral_conversion.conversion(self.promoter.id)
        second = referral_conversion.conversion(self.promoter.id, page=2)
        self.assertEqual(first['summary'], second['summary'])
        self.assertEqual((first['total'], len(first['items']), len(second['items'])), (22, 20, 2))
        items = first['items'] + second['items']
        self.assertEqual(len({item['key'] for item in items}), 22)
        self.assertEqual(next(item['name'] for item in items if item['campaign_id'] == self.a['id']), '家长群新名称')
