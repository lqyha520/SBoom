"""海报复用真实图片管线，验证范围、计量和恢复；上游网络使用模拟响应。"""

import json
import unittest
from unittest.mock import AsyncMock, patch

import test_backend_image_generation as fixtures

from app.db import db
from app.models.referral_operations import CampaignInput
from app.routers import referrals
from app.services import admin_access, referral_operations, user_store
from app.services import image_generation as image_service


class ReferralPosterContracts(unittest.TestCase):
    setUpImages = fixtures.ImageGenerationContracts.setUp
    login = fixtures.ImageGenerationContracts.login

    def setUp(self):
        self.setUpImages()
        self.client.app.include_router(referrals.router)
        self.promoter = user_store.create_user('poster-promoter', 'test-password', role='admin')
        admin_access.save_permissions(self.admin.id, self.promoter.id, 1, {'referrals': ['view', 'export']})
        self.campaign = referral_operations.save_campaign(self.admin.id, CampaignInput(admin_id=self.promoter.id, name='阅读的春天', source='家长群'))
        self.login(self.promoter)
        self.body = {'campaign_id': self.campaign['id'], 'title': '阅读的春天', 'style': 'editorial', 'direction': '打开的书本变成森林'}

    def send(self, request_id='poster-one', **changes):
        return self.client.post('/api/v1/admin/referrals/poster', json={**self.body, **changes}, headers={'X-Request-ID': request_id})

    def test_uses_configured_provider_and_private_asset_replays_once_without_worksheet_review(self):
        with patch('app.services.image_review.review_image', new_callable=AsyncMock) as review:
            result = self.send()
        self.assertEqual(result.status_code, 200, result.text)
        review.assert_not_called()
        self.assertEqual(len(self.calls), 1)
        payload = json.loads(self.calls[0].content)
        self.assertEqual(payload['model'], self.config['model'])
        self.assertIn('打开的书本变成森林', payload['prompt'])
        self.assertIn('不要绘制任何文字', payload['prompt'])
        self.assertNotIn(self.campaign['code'], payload['prompt'])
        self.assertNotIn(self.campaign['source'], payload['prompt'])
        self.assertNotIn('secret-image-test', result.text)
        self.assertNotIn('b64_json', result.json())
        self.assertEqual(self.send().json()['asset_id'], result.json()['asset_id'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.send(title='另一个主题').status_code, 409)
        status = self.client.get('/api/v1/me/generations/poster-one').json()
        self.assertEqual(status['result']['asset_id'], result.json()['asset_id'])
        self.assertEqual(self.client.get(result.json()['url']).content, fixtures.png())
        self.login(self.admin)
        self.assertEqual(self.client.get(result.json()['url']).status_code, 404)

    def test_denied_or_disabled_campaign_is_checked_before_metering_and_cached_replay(self):
        self.assertEqual(self.send().status_code, 200)
        with db() as conn:
            conn.execute('UPDATE referral_campaigns SET active=FALSE WHERE id=?', (self.campaign['id'],))
        self.assertEqual(self.send().status_code, 404)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.send('poster-disabled').status_code, 404)
        other = referral_operations.save_campaign(self.admin.id, CampaignInput(name='别人的活动', source='家长群'))
        self.assertEqual(self.send('poster-other', campaign_id=other['id']).status_code, 403)
        with db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM generation_requests').fetchone()[0], 1)

    def test_export_permission_required_and_unknown_style_rejected_without_provider_calls(self):
        self.assertEqual(self.send(style='unknown').status_code, 422)
        self.assertEqual(self.send(direction='x' * 501).status_code, 422)
        self.assertEqual(self.send(title='  ').status_code, 422)
        admin_access.save_permissions(self.admin.id, self.promoter.id, 2, {'referrals': ['view']})
        self.assertEqual(self.send().status_code, 403)
        self.assertFalse(self.calls)

    def test_provider_uncertainty_does_not_resubmit_when_request_is_repeated(self):
        with patch.object(image_service, '_provider_json', side_effect=TimeoutError):
            first = self.send()
        self.assertGreaterEqual(first.status_code, 500)
        with patch('app.services.referral_poster.generate_image', new_callable=AsyncMock) as generate:
            self.assertGreaterEqual(self.send().status_code, 400)
            generate.assert_not_called()
