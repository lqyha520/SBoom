"""访问追踪、阶段名单与投放回报使用一次性库验证。"""

import csv
import io
import time

import test_backend_growth as growth
import test_backend_referral_conversion as conversion_tests
from fastapi import HTTPException

from app.db import db
from app.models.referral_operations import CampaignInput, CampaignUpdate
from app.routers import referrals as referral_routes
from app.services import (
    admin_access,
    mini_auth,
    referral_conversion,
    referral_growth,
    referral_operations,
    referrals,
    user_store,
)


class ReferralGrowthContracts(growth.GrowthBase):
    configure = growth.CommerceContracts.configure
    order = conversion_tests.ReferralConversionContracts.order
    reader = conversion_tests.ReferralConversionContracts.reader

    def setUp(self):
        super().setUp()
        self.configure()
        self.client.app.include_router(referral_routes.router)
        self.promoter = user_store.create_user('growth-owner', 'test-password', role='admin')
        admin_access.save_permissions(self.admin.id, self.promoter.id, 1, {'referrals': ['view', 'export']})
        self.campaign = referral_operations.save_campaign(self.admin.id, CampaignInput(
            admin_id=self.promoter.id, name='资料活动', source='家长群', spend_fen=1000))

    def test_entry_is_idempotent_register_is_once_and_existing_login_is_not_registration(self):
        endpoint = '/api/v1/mini/referral-entry'
        body = {'code': self.campaign['code'], 'entry_key': 'first-device-entry-key'}
        response = self.client.post(endpoint, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        visit = response.json()['visit_id']
        self.assertEqual(self.client.post(endpoint, json=body).json()['visit_id'], visit)
        self.assertEqual(self.client.post('/api/v1/mini/referral-start', json={'visit_id': visit}).status_code, 200)
        user = mini_auth.login_public_identity('tracked-new-user', referral_code=body['code'], referral_visit_id=visit)['user']
        another = referral_growth.enter(body['code'], 'another-device-entry-key')['visit_id']
        mini_auth.login_public_identity('tracked-new-user', referral_code=body['code'], referral_visit_id=another)
        with db() as conn:
            conn.execute('UPDATE mini_users SET created_at=? WHERE id=?', (conversion_tests.stamp('2026-11-02T00:00:00'), user['id']))
        self.order(user, 'real-payment', paid=True)
        self.order(user, 'repeat-payment', paid=True)
        stats = referral_growth.acquisition(self.promoter.id)
        self.assertEqual([stats[k] for k in ('visits', 'started', 'registered', 'paid')], [2, 1, 1, 1])
        self.assertLessEqual(stats['tracking_since'], stats['as_of'])

    def test_invalid_expired_and_mismatched_visits_do_not_create_false_conversions(self):
        code = self.campaign['code']
        visit = referral_growth.enter(code, 'expired-device-entry-key')['visit_id']
        with db() as conn:
            conn.execute('UPDATE referral_visits SET created_at=? WHERE id=?', (int(time.time()) - 8 * 86400, visit))
        mini_auth.login_public_identity('expired-reader', referral_code=code, referral_visit_id=visit)
        fresh = referral_growth.enter(code, 'fresh-device-entry-key')['visit_id']
        mini_auth.login_public_identity('natural-reader', referral_visit_id=fresh)
        stats = referral_growth.acquisition(self.promoter.id)
        self.assertEqual(stats['registered'], 0)
        self.assertFalse(referral_growth.enter('a_' + '0' * 20, 'invalid-device-entry')['tracked'])
        self.assertEqual(self.client.post('/api/v1/mini/referral-entry', json={'code': code, 'entry_key': '../bad'}).status_code, 422)

    def test_landing_validation_and_hidden_content_fall_back_to_home(self):
        with self.assertRaises(HTTPException):
            referral_operations.save_campaign(self.admin.id, CampaignInput(admin_id=self.promoter.id,
                name='无效资料', source='家长群', landing_kind='paper', landing_id='missing'))
        paper = self.publish()
        current = referral_operations.save_campaign(self.admin.id, CampaignUpdate(admin_id=self.promoter.id,
            revision=1, name='资料活动', source='家长群', active=True, landing_kind='paper', landing_id=paper['id']), self.campaign['id'])
        self.assertEqual(current['spend_fen'], 1000)
        self.assertEqual(referral_growth.enter(current['code'], 'public-paper-entry')['destination'], '/pages/paper/index?id=' + paper['id'])
        with db() as conn:
            conn.execute("UPDATE catalog_papers SET status='draft' WHERE id=?", (paper['id'],))
        self.assertEqual(referral_growth.enter(current['code'], 'hidden-paper-entry')['destination'], '/pages/home/index')
        with db() as conn:
            conn.execute("UPDATE catalog_papers SET status='published' WHERE id=?", (paper['id'],))
        referral_operations.save_campaign(self.admin.id, CampaignUpdate(admin_id=self.promoter.id,
            revision=2, name='资料活动', source='家长群', active=False), self.campaign['id'])
        self.assertFalse(referral_growth.enter(current['code'], 'disabled-entry-key')['tracked'])

    def test_stage_counts_export_and_snapshot_match_the_conversion_funnel(self):
        self.reader('no-order', self.campaign)
        ordered = self.reader('unpaid', self.campaign)
        paid = self.reader('paid', self.campaign)
        sandbox = self.reader('sandbox', self.campaign)
        self.order(ordered, 'unpaid-order')
        self.order(paid, 'paid-order', paid=True)
        self.order(sandbox, 'sandbox-order', paid=True, sandbox=True)
        result = referral_conversion.conversion(self.promoter.id)
        for stage, count in [('all', 4), ('not_ordered', 2), ('unpaid', 1), ('paid', 1), ('ordered', 2)]:
            filters = {'stage': stage, 'as_of': result['as_of']}
            listing = referrals.users(self.promoter.id, **filters)
            exported = list(csv.reader(io.StringIO(referrals.export_users(self.promoter.id, **filters).lstrip('\ufeff'))))
            self.assertEqual(listing['total'], count)
            self.assertEqual(len(exported) - 1, count)
            self.assertIn('来源渠道', exported[0])
        with db() as conn:
            conn.execute('UPDATE mini_orders SET paid_at=? WHERE id=?', (result['as_of'] + 10, 'unpaid-order'))
        self.assertEqual(referrals.users(self.promoter.id, stage='unpaid', as_of=result['as_of'])['total'], 1)
        self.sign_in(self.promoter)
        response = self.client.get('/api/v1/admin/referrals/export/orders')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('sandbox-order', response.text)
        self.assertIn('paid-order', response.text)

    def test_real_payments_costs_filters_pagination_and_permissions(self):
        real = self.reader('real', self.campaign)
        sandbox = self.reader('test', self.campaign)
        self.order(real, 'real-order', paid=True)
        self.order(sandbox, 'sandbox-order', paid=True, sandbox=True)
        result = referral_operations.performance(self.promoter.id, self.campaign['id'])
        self.assertEqual(result['income']['paid_fen'], 1990)
        self.assertEqual(result['remainder_fen'], 990)
        self.assertEqual(result['return_bps'], 9900)
        other = user_store.create_user('other-growth-owner', 'test-password', role='admin')
        with self.assertRaises(HTTPException):
            referral_operations.performance(other.id, self.campaign['id'])
        self.sign_in(self.promoter)
        self.assertEqual(self.client.get('/api/v1/admin/referrals/acquisition', params={'admin_id': self.admin.id}).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/admin/referrals/campaigns', params={'page': 0}).status_code, 422)
        for index in range(21):
            referral_operations.save_campaign(self.admin.id, CampaignInput(admin_id=self.promoter.id,
                name='搜索活动' + str(index), source='渠道%'))
        first = referral_operations.campaigns(self.promoter.id, q='搜索', source='%', state='active')
        second = referral_operations.campaigns(self.promoter.id, q='搜索', source='%', state='active', page=2)
        self.assertEqual((first['total'], len(first['items']), len(second['items'])), (21, 20, 1))
        self.assertTrue(set(row['id'] for row in first['items']).isdisjoint(row['id'] for row in second['items']))
        with db() as conn:
            conn.execute('UPDATE referral_campaigns SET spend_fen=NULL WHERE id=?', (self.campaign['id'],))
        self.assertIsNone(referral_operations.performance(self.promoter.id, self.campaign['id'])['remainder_fen'])
