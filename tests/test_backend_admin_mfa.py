"""管理员两步登录、设备归属、凭证更换和验证码重放的回归。"""
import time
import unittest
from unittest.mock import patch

from app.config import get_settings
from app.db import db
from app.security import decrypt_secret
from app.services import admin_mfa, user_store
from scripts.rotate_encryption import rotate
from tests import test_backend_catalog as fixtures


class AdminMfaTests(unittest.TestCase):
    setUp = fixtures.PublicCatalogContracts.setUp
    sign_in = fixtures.PublicCatalogContracts.sign_in

    def enroll(self):
        self.client.cookies.clear()
        response = self.client.post('/api/v1/auth/login', json={'username': self.admin.username, 'password': 'test-password'})
        self.assertEqual(response.status_code, 200, response.text)
        secret = self.client.post('/api/v1/auth/mfa/setup').json()['secret']
        # 用上一个窗口完成设置，当前窗口可用于登录。
        code = admin_mfa._code(secret, int(time.time() // 30) - 1)
        response = self.client.post('/api/v1/auth/mfa/confirm', json={'code': code})
        self.assertEqual(response.status_code, 200, response.text)
        return secret

    def challenge(self):
        self.client.cookies.clear()
        response = self.client.post('/api/v1/auth/login', json={'username': self.admin.username, 'password': 'test-password'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('set-cookie', response.headers)
        return response.json()['challenge']

    def test_login_requires_second_factor_and_prevents_replay(self):
        secret = self.enroll()
        self.assertEqual(self.client.post('/api/v1/auth/mfa/setup').status_code, 409)
        challenge = self.challenge()
        self.assertEqual(self.client.get('/api/v1/auth/me').status_code, 401)
        body = {'challenge': challenge, 'code': admin_mfa._code(secret, int(time.time() // 30))}
        self.assertEqual(self.client.post('/api/v1/auth/mfa/verify', json=body).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/auth/me').status_code, 200)
        self.assertEqual(self.client.post('/api/v1/auth/mfa/verify', json=body).status_code, 401)

    def test_attempt_budget_commits_and_password_change_invalidates_challenge(self):
        secret = self.enroll()
        challenge = self.challenge()
        with patch.object(admin_mfa, 'verify_code', return_value=None):
            for _ in range(5):
                self.assertEqual(self.client.post('/api/v1/auth/mfa/verify', json={'challenge': challenge, 'code': '000000'}).status_code, 401)
        body = {'challenge': challenge, 'code': admin_mfa._code(secret, int(time.time() // 30))}
        self.assertEqual(self.client.post('/api/v1/auth/mfa/verify', json=body).json()['detail']['code'], 'mfa_challenge_expired')
        body['challenge'] = self.challenge()
        with db() as conn:
            conn.execute('UPDATE users SET token_valid_after=token_valid_after+1 WHERE id=?', (self.admin.id,))
        self.assertEqual(self.client.post('/api/v1/auth/mfa/verify', json=body).status_code, 401)

    def test_own_sessions_available_without_account_management_permission(self):
        user = user_store.create_user('limited-mfa-admin', 'test-password', role='admin')
        self.client.cookies.clear()
        self.client.post('/api/v1/auth/login', json={'username': user.username, 'password': 'test-password'})
        response = self.client.get('/api/v1/admin/sessions')
        self.assertEqual(response.status_code, 200, response.text)
        session = response.json()['sessions'][0]
        self.assertTrue(session['current'])
        self.assertIn('testclient', session['user_agent'])
        self.assertEqual(self.client.get('/api/v1/auth/mfa/status').status_code, 200)
        self.assertEqual(self.client.delete('/api/v1/admin/sessions/' + session['id']).status_code, 204)
        self.assertEqual(self.client.get('/api/v1/auth/me').status_code, 401)
        self.sign_in(self.admin)
        self.assertEqual(self.client.delete('/api/v1/admin/sessions/' + session['id']).status_code, 404)

    def test_totp_known_vector_and_missing_secret(self):
        self.assertEqual(admin_mfa._code('GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ', 1), '287082')
        self.assertEqual(admin_mfa.verify_code('GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ', '287082', 59), 1)
        self.assertIsNone(admin_mfa.verify_code('', '123456'))

    def test_key_rotation_preserves_enrolled_totp_secret(self):
        secret = self.enroll()
        settings = get_settings()
        with patch.object(settings, 'encryption_active_key', 'v2'), patch.object(settings, 'encryption_keys', {'v2': 'new-test-encryption-secret-32-bytes-long'}):
            rotate(apply=True)
            with db() as conn:
                value = conn.execute('SELECT secret_enc FROM admin_mfa WHERE user_id=?', (self.admin.id,)).fetchone()[0]
            self.assertTrue(value.startswith('enc2:v2:'))
            self.assertEqual(decrypt_secret(value), secret)
            self.assertTrue(admin_mfa.enabled(self.admin.id))
