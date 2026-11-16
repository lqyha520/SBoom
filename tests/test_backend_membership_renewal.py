"""续费边界与到期提醒使用一致的七天窗口，长期会员不重复购买。"""
import unittest

from app.db import db
from app.models.commerce import PlanInput
from app.services import mini_messages, mini_orders
from app.services.membership_renewal import renewal_state
from tests import test_backend_catalog as fixtures


def test_renewal_state_boundaries():
    assert renewal_state('vip', None, 1000)['status'] == 'lifetime'
    assert renewal_state('vip', 999, 1000)['status'] == 'expired'
    assert renewal_state('vip', 1000, 1000)['starts_at'] == 1000
    assert renewal_state('vip', 1000 + 7 * 86400, 1000)['status'] == 'expiring'
    assert renewal_state('vip', 1001 + 7 * 86400, 1000)['status'] == 'active'
    assert not renewal_state('regular', None, 1000)['automatic_renewal']


class RenewalTests(unittest.TestCase):
    setUp = fixtures.PublicCatalogContracts.setUp
    sign_in = fixtures.PublicCatalogContracts.sign_in

    def test_expired_plan_quote_and_inbox_are_consistent_and_deduplicated(self):
        mini_orders.save_plan(PlanInput(name='月度会员', days=30, price_fen=100, is_active=True))
        with db() as conn:
            conn.execute("UPDATE mini_users SET membership='vip',vip_expires_at=1000 WHERE id=?", (self.viewer.id,))
            mini_messages.expiry_notice(conn, self.viewer.id)
            mini_messages.expiry_notice(conn, self.viewer.id)
        value = mini_orders.plans(user_id=self.viewer.id)
        self.assertEqual(value['renewal']['status'], 'expired')
        self.assertEqual(value['items'][0]['projected_expires_at'], value['renewal']['starts_at'] + 30 * 86400)
        self.assertIn('已到期', value['items'][0]['renewal_label'])
        inbox = mini_messages.inbox(self.viewer.id)
        self.assertEqual(inbox['total'], 1)
        self.assertEqual(inbox['items'][0]['target_type'], 'membership')
