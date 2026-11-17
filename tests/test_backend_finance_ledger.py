"""账本金额、幂等性、并发修改、权限与 CSV 公式防护。"""
import unittest

from app.db import db
from app.routers.finance_ledger import router
from app.services import admin_access, user_store
from tests import test_backend_catalog as fixtures


class FinanceLedgerTests(unittest.TestCase):
    def setUp(self):
        fixtures.PublicCatalogContracts.setUp(self)
        self.client.app.include_router(router)
        self.body = {'identifier': 'expense-one', 'entry_date': '2026-11-14', 'direction': 'expense', 'category': '服务费',
                     'amount_fen': 3_000_000_000, 'tax_fen': 100, 'counterparty': '=SUM(A1)', 'reference': '发票一'}

    sign_in = fixtures.PublicCatalogContracts.sign_in

    def create(self):
        response = self.client.post('/api/v1/admin/finance-ledger', json=self.body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_idempotence_revision_void_summary_and_audit(self):
        first = self.create()
        self.assertEqual(self.create()['id'], first['id'])
        changed = self.client.post('/api/v1/admin/finance-ledger', json={**self.body, 'amount_fen': 200})
        self.assertEqual(changed.status_code, 409)
        listing = self.client.get('/api/v1/admin/finance-ledger').json()
        self.assertEqual(listing['total'], 1)
        self.assertEqual(listing['summary']['net_fen'], -3_000_000_000)
        path = '/api/v1/admin/finance-ledger/expense-one'
        body = {**self.body, 'revision': 1, 'amount_fen': 500}
        self.assertEqual(self.client.put(path, json=body).status_code, 200)
        self.assertEqual(self.client.put(path, json=body).status_code, 409)
        self.assertEqual(self.client.post(path + '/void?revision=2').status_code, 200)
        self.assertEqual(self.client.put(path, json={**body, 'revision': 3}).status_code, 409)
        self.assertEqual(self.client.get('/api/v1/admin/finance-ledger?status=').json()['summary']['net_fen'], 0)
        with db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM finance_ledger_audit').fetchone()[0], 3)

    def test_invalid_data_csv_and_view_only_permissions(self):
        for changes in ({'entry_date': '2026-02-30'}, {'category': '  '}, {'amount_fen': 1.5}, {'tax_fen': 4_000_000_000}):
            self.assertEqual(self.client.post('/api/v1/admin/finance-ledger', json={**self.body, **changes}).status_code, 422)
        self.create()
        response = self.client.get('/api/v1/admin/finance-ledger/export.csv')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("'=SUM(A1)", response.text)
        self.assertEqual(self.client.get('/api/v1/admin/finance-ledger?start_date=2026-99-99').status_code, 422)
        self.assertEqual(self.client.get('/api/v1/admin/finance-ledger?start_date=2026-11-15&end_date=2026-11-14').status_code, 422)
        user = user_store.create_user('ledger-reader', 'test-password', role='admin')
        admin_access.save_permissions(self.admin.id, user.id, 1, {'financeLedger': ['view']})
        self.sign_in(user)
        self.assertEqual(self.client.get('/api/v1/admin/finance-ledger').status_code, 200)
        self.assertEqual(self.client.post('/api/v1/admin/finance-ledger', json=self.body).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/admin/finance-ledger/export.csv').status_code, 403)
