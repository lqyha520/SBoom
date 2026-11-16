"""推广六项优化：金额、分摊、付款预检与月末清单使用隔离 PostgreSQL。"""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import test_backend_growth as growth
import test_backend_settlements as original
from fastapi import HTTPException

from app.db import db
from app.models.promotion_finance import CampaignExpense, CampaignExpenseUpdate, CostVoucherInput, PayoutBatchInput
from app.models.referral_operations import CampaignInput, CampaignUpdate
from app.models.settlements import CostsInput, PayeeInput, ReviewInput, StatementInput, VoidInput
from app.routers import referrals as referral_routes
from app.routers import settlements as routes
from app.services import (
    admin_access,
    cost_vouchers,
    finance_close,
    referral_comparison,
    referral_expenses,
    referral_operations,
    referrals,
    settlement_batches,
    settlement_operations,
    settlements,
    user_store,
)
from app.services.settlement_queries import ZONE


class PromotionSixContracts(growth.GrowthBase):
    configure = original.SettlementContracts.configure
    create_order = original.SettlementContracts.create_order
    paid_value = original.SettlementContracts.paid_value
    rules = original.SettlementContracts.rules
    reward = original.SettlementContracts.reward
    costs = original.SettlementContracts.costs
    paid = original.SettlementContracts.paid
    another = original.SettlementContracts.another
    draft = original.SettlementContracts.draft
    approve = original.SettlementContracts.approve
    payout = original.SettlementContracts.payout
    refund = original.SettlementContracts.refund

    def setUp(self):
        super().setUp()
        self.client.app.include_router(routes.router)
        self.client.app.include_router(referral_routes.router)
        self.configure()
        self.promoter = user_store.create_user('six-owner', 'test-password', role='admin')
        admin_access.save_permissions(self.admin.id, self.promoter.id, 1, {'referrals': ['view', 'create', 'export'], 'settlements': ['view', 'create', 'export']})
        self.code = referrals.admin_code(self.admin.id, self.promoter.id)['code']
        with db() as conn:
            referrals.initialize_user(conn, self.viewer.id, self.code)
        self.rules()
        settlement_operations.save_payee(self.promoter.id, PayeeInput(name='测试收款人', method='bank', account='6222000012345678', bank='测试银行'))

    def campaign(self, name='测试活动', baseline=0):
        return referral_operations.save_campaign(self.promoter.id, CampaignInput(name=name, source='微信群', spend_fen=baseline))

    def expense(self, campaign, amount=700, ref='FP-SIX/广告', key='six-expense-0001'):
        return referral_expenses.save(self.promoter.id, campaign['id'], CampaignExpense(expense_date='2026-10-15', category='广告', amount_fen=amount, evidence='原始发票依据', source_ref=ref, request_key=key))

    def voucher(self, amount=1000):
        return cost_vouchers.save(self.promoter.id, CostVoucherInput(admin_id=self.promoter.id, reference='FP-SIX', name='十月推广发票', total_fen=amount, evidence='原始发票总额'))

    def test_unknown_baseline_keeps_roi_unknown_after_recording_expense(self):
        campaign = self.campaign(baseline=None)
        self.expense(campaign)
        report = referral_operations.performance(self.promoter.id, campaign['id'])
        self.assertIsNone(report['spend_fen'])
        self.assertIsNone(report['return_bps'])
        self.assertEqual(report['known_spend_fen'], 700)
        ledger = referral_expenses.listing(self.promoter.id, campaign['id'])
        self.assertIsNone(ledger['cumulative_fen'])
        self.assertEqual(ledger['known_cumulative_fen'], 700)
        referral_operations.save_campaign(self.promoter.id, CampaignUpdate(name=campaign['name'], source='微信群', active=True, revision=campaign['revision'], spend_fen=0), campaign['id'])
        self.assertEqual(referral_operations.performance(self.promoter.id, campaign['id'])['spend_fen'], 700)

    def test_voucher_caps_cross_campaign_expenses_and_restore_rechecks_total(self):
        voucher = self.voucher()
        first, second = self.campaign('活动甲'), self.campaign('活动乙')
        expense = self.expense(first)
        with self.assertRaises(HTTPException):
            self.expense(second, 400, ' fp-six /物料', 'six-expense-0002')
        self.assertEqual(referral_expenses.listing(self.promoter.id, second['id'])['total'], 0)
        body = CampaignExpenseUpdate(**{key: expense[key] for key in ('expense_date', 'category', 'amount_fen', 'evidence', 'note', 'revision', 'source_ref')}, active=False)
        voided = referral_expenses.save(self.promoter.id, first['id'], body, expense['id'])
        self.expense(second, 400, 'FP-SIX/物料', 'six-expense-0002')
        with self.assertRaises(HTTPException):
            referral_expenses.save(self.promoter.id, first['id'], body.model_copy(update={'active': True, 'revision': voided['revision']}), expense['id'])
        with self.assertRaises(HTTPException):
            cost_vouchers.save(self.promoter.id, CostVoucherInput(admin_id=self.promoter.id, reference='fp-six', name=voucher['name'], total_fen=399, evidence='核对减少金额', revision=voucher['revision']), voucher['id'])
        self.assertEqual(cost_vouchers.listing(self.promoter.id)['items'][0]['expense_fen'], 400)

    def test_voucher_cost_and_deduction_caps_are_independent_and_cross_order_safe(self):
        self.voucher(1000)
        self.expense(self.campaign(), 900)
        first, second = self.paid(), self.another('six-second-buyer')
        def costs(order, amount, suffix):
            return settlements.confirm_costs(self.admin.id, order['id'], CostsInput(revision=self.reward(order)['revision'], channel_fee_fen=0, shared_fees=[{'name': '实际物料', 'source_ref': 'FP-SIX/' + suffix, 'amount_fen': amount}], evidence='原始凭据分摊', confirmed=True))
        costs(first, 900, '第一单')
        with self.assertRaises(HTTPException):
            costs(second, 101, '第二单')
        self.assertIsNone(self.reward(second)['costs'])
        statement = settlements.create_statement(self.admin.id, StatementInput(order_ids=[first['id']]))
        body = ReviewInput(revision=statement['revision'], personal_fees=[{'name': '个人材料', 'source_ref': 'FP-SIX/个人材料', 'amount_fen': 101}], tax_fen=0, evidence='个人费用核对', confirmed=True)
        with self.assertRaises(HTTPException):
            settlements.approve(self.admin.id, statement['id'], body)
        approved = settlements.approve(self.admin.id, statement['id'], body.model_copy(update={'personal_fees': []}))
        self.payout(approved)
        self.refund(first)
        with self.assertRaises(HTTPException):
            costs(second, 101, '第二单')  # 退款不会释放已实际扣除的凭据额度。
        value = cost_vouchers.listing(self.promoter.id)['items'][0]
        self.assertEqual((value['expense_fen'], value['deduction_fen']), (900, 900))

    def test_concurrent_allocations_cannot_overdraw_voucher_and_foreign_owner_is_rejected(self):
        self.voucher(1000)
        campaigns = [self.campaign('并发活动甲'), self.campaign('并发活动乙')]

        def allocate(index):
            try:
                self.expense(campaigns[index], 600, 'FP-SIX/并发' + str(index), 'six-concurrent-' + str(index))
                return 200
            except HTTPException as error:
                return error.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(allocate, range(2))), [200, 422])
        self.assertEqual(cost_vouchers.listing(self.promoter.id)['items'][0]['expense_fen'], 600)
        foreign = referral_operations.save_campaign(self.admin.id, CampaignInput(name='其他归属活动', source='微信群', spend_fen=0))
        with self.assertRaises(HTTPException):
            referral_expenses.save(self.admin.id, foreign['id'], CampaignExpense(expense_date='2026-10-15', category='广告', amount_fen=1, evidence='凭据归属核对', source_ref='FP-SIX/其他归属', request_key='six-foreign-0001'))
        self.assertEqual(referral_expenses.listing(self.admin.id, foreign['id'])['total'], 0)

    def test_voucher_files_scope_dedup_revision_and_http_permissions(self):
        self.sign_in(self.promoter)
        response = self.client.post('/api/v1/admin/settlements/cost-vouchers', json={'admin_id': self.promoter.id, 'reference': 'FP-SIX', 'name': '原始凭据', 'total_fen': 1000, 'evidence': '原始票据说明'})
        self.assertEqual(response.status_code, 200, response.text)
        voucher = response.json()
        content = b'%PDF-1.4\nfixture\n%%EOF'
        endpoint = '/api/v1/admin/settlements/cost-vouchers/' + voucher['id'] + '/files?name=invoice.pdf'
        first = self.client.post(endpoint, content=content, headers={'Content-Type': 'application/octet-stream'})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(self.client.post(endpoint, content=content).json(), first.json())
        download = '/api/v1/admin/settlements/cost-voucher-files/' + first.json()['id']
        self.assertEqual(self.client.get(download).content, content)
        outsider = user_store.create_user('six-outsider', 'test-password', role='admin')
        admin_access.save_permissions(self.admin.id, outsider.id, 1, {'referrals': ['view', 'create']})
        self.sign_in(outsider)
        self.assertEqual(self.client.get(download).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/admin/settlements/cost-vouchers').json()['total'], 0)
        self.assertEqual(self.client.post(endpoint, content=content).status_code, 403)

    def test_payout_candidates_mark_reserved_and_selection_catches_stale_status(self):
        statement = self.approve(self.draft(self.paid()))
        candidates = settlement_batches.candidates(self.admin.id)
        self.assertEqual(candidates['items'][0]['payout_issues'], [])
        batch = settlement_batches.create(self.admin.id, PayoutBatchInput(name='测试付款批次', statement_ids=[statement['id']], request_key='six-batch-0001'))
        selected = settlement_batches.selection(self.admin.id, [statement['id']])
        self.assertEqual(selected['blocked'], 1)
        self.assertEqual(selected['total_fen'], statement['net_fen'])
        self.assertEqual(selected['items'][0]['batch_id'], batch['id'])
        settlements.cancel_statement(self.admin.id, statement['id'], VoidInput(revision=statement['revision'], reason='重新核对资料'))
        self.assertTrue(settlement_batches.selection(self.admin.id, [statement['id']])['items'][0]['payout_issues'])
        draft = self.draft(self.another('six-pending-review'))
        pending = settlement_batches.selection(self.admin.id, [draft['id'], 'missing-statement'])
        self.assertEqual((pending['blocked'], pending['total_fen']), (2, 0))
        self.sign_in(self.promoter)
        self.assertEqual(self.client.get('/api/v1/admin/settlements/payout-candidates').status_code, 403)

    def test_comparison_periods_cost_completeness_sort_and_scoped_access(self):
        campaign = self.campaign()
        self.expense(campaign, 700)
        order = self.paid()
        with db() as conn:
            conn.execute('UPDATE mini_orders SET referral=referral || ?::jsonb,paid_at=? WHERE id=?', (json.dumps({'campaign_id': campaign['id']}), int(datetime(2026, 10, 15, tzinfo=ZONE).timestamp()), order['id']))
        report = referral_comparison.comparison(self.promoter.id, '2026-10-01', '2026-10-31')
        self.assertEqual(report['previous_start'], '2026-08-31')
        self.assertEqual(report['previous_end'], '2026-09-30')
        item = report['items'][0]
        self.assertEqual((item['spend_fen'], item['paying_users'], item['cost_per_payer_fen']), (700, 1, 700))
        self.assertEqual(item['previous']['paying_users'], 0)
        unknown = self.campaign('未知成本活动', baseline=None)
        self.assertFalse(next(item for item in referral_comparison.comparison(self.promoter.id, '2026-10-01', '2026-10-31')['items'] if item['id'] == unknown['id'])['cost_complete'])
        with self.assertRaises(HTTPException):
            referral_comparison.comparison(self.promoter.id, '2026-10-01', '2026-10-31', admin_id=self.admin.id)

    def test_comparison_requires_dated_baseline_and_excludes_virtual_test_orders(self):
        campaign = self.campaign(baseline=700)
        order, sandbox = self.paid(), self.paid('six-sandbox')
        with db() as conn:
            for item in (order, sandbox):
                conn.execute('UPDATE mini_orders SET referral=referral || ?::jsonb,paid_at=? WHERE id=?', (json.dumps({'campaign_id': campaign['id']}), int(datetime(2026, 10, 15, tzinfo=ZONE).timestamp()), item['id']))
            conn.execute("UPDATE mini_orders SET payment_channel='virtual',virtual_env=1 WHERE id=?", (sandbox['id'],))
        fields = dict(category='广告', evidence='此前累计明细', included_in_baseline=True)
        referral_expenses.save(self.promoter.id, campaign['id'], CampaignExpense(**fields, expense_date='2026-10-15', amount_fen=300, source_ref='FP-SIX/本期', request_key='six-baseline-0001'))
        item = referral_comparison.comparison(self.promoter.id, '2026-10-01', '2026-10-31')['items'][0]
        self.assertFalse(item['cost_complete'])
        self.assertIsNone(item['cost_per_payer_fen'])
        referral_expenses.save(self.promoter.id, campaign['id'], CampaignExpense(**fields, expense_date='2026-09-15', amount_fen=400, source_ref='FP-SIX/前期', request_key='six-baseline-0002'))
        item = referral_comparison.comparison(self.promoter.id, '2026-10-01', '2026-10-31')['items'][0]
        self.assertTrue(item['cost_complete'])
        self.assertEqual((item['spend_fen'], item['previous']['spend_fen'], item['cost_per_payer_fen']), (300, 400, 300))
        self.assertEqual(item['paid_fen'], order['amount_fen'])
        self.assertEqual(referral_operations.performance(self.promoter.id, campaign['id'])['spend_fen'], 700)

    def test_month_end_requires_latest_complete_reconciliation_with_all_differences(self):
        stamp = int(datetime(2026, 10, 15, tzinfo=ZONE).timestamp())
        order = self.paid()
        with db() as conn:
            conn.execute('UPDATE mini_orders SET paid_at=? WHERE id=?', (stamp, order['id']))
            conn.execute("INSERT INTO mini_reconciliations(id,bill_date,status,summary_json,created_at,updated_at) VALUES(?,?,'complete',?,?,?)", ('six-old', '2026-10-15', json.dumps({'differences': 0}), stamp, stamp))
        self.assertEqual(finance_close.checklist(self.admin.id, '2026-10')['bills'], [])
        with db() as conn:
            conn.execute("INSERT INTO mini_reconciliations(id,bill_date,status,created_at,updated_at) VALUES(?,?,'running',?,?)", ('six-latest', '2026-10-15', stamp + 1, stamp + 1))
        self.assertEqual(finance_close.checklist(self.admin.id, '2026-10')['bills'][0]['reason'], '核对未完成')
        with db() as conn:
            conn.execute("UPDATE mini_reconciliations SET status='complete',summary_json=? WHERE id='six-latest'", (json.dumps({'differences': 2}),))
        self.assertEqual(finance_close.checklist(self.admin.id, '2026-10')['bills'][0]['reason'], '差异未完整留存')
        with db() as conn:
            conn.execute("UPDATE mini_reconciliations SET differences_json=? WHERE id='six-latest'", (json.dumps([{'reason': '差异甲'}, {'reason': '差异乙'}]),))
        self.assertEqual(finance_close.checklist(self.admin.id, '2026-10')['bills'][0]['reason'], '存在账单差异')
        with db() as conn:
            conn.execute("UPDATE mini_reconciliations SET summary_json=?,differences_json='[]' WHERE id='six-latest'", (json.dumps({'differences': 0}),))
        self.assertEqual(finance_close.checklist(self.admin.id, '2026-10')['bills'], [])

    def test_month_end_lists_unarchived_missing_bills_and_respects_responsibilities(self):
        stamp = int(datetime(2026, 10, 15, tzinfo=ZONE).timestamp())
        order = self.paid()
        campaign = self.campaign(baseline=None)
        with db() as conn:
            conn.execute('UPDATE mini_orders SET paid_at=? WHERE id=?', (stamp, order['id']))
            conn.execute('UPDATE referral_campaigns SET created_at=? WHERE id=?', (stamp, campaign['id']))
            conn.execute('INSERT INTO referral_ledger_events(source,beneficiary,kind,amount_fen,occurred_at) VALUES(?,?,?,?,?)', ('six-event', 'admin:' + str(self.promoter.id), 'adjustment', 100, stamp))
        report = finance_close.checklist(self.admin.id, '2026-10')
        self.assertEqual(report['archives']['total'], 1)
        self.assertEqual(report['bills'][0]['day'], '2026-10-15')
        self.assertEqual(report['costs']['total'], 1)
        self.sign_in(self.admin)
        response = self.client.get('/api/v1/admin/settlements/month-end?month=2026-10')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['archives']['items'][0]['closing_fen'], 100)
        self.assertIsInstance(response.json()['archives']['items'][0]['closing_fen'], int)
        reader = user_store.create_user('six-bill-reader', 'test-password', role='admin')
        admin_access.save_permissions(self.admin.id, reader.id, 1, {'reconciliations': ['view']})
        self.sign_in(reader)
        response = self.client.get('/api/v1/admin/settlements/month-end?month=2026-10')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()['archives'])
        self.assertIsNone(response.json()['costs'])
        self.assertIsNone(response.json()['disputes'])
        self.assertEqual(len(response.json()['bills']), 1)
        admin_access.save_permissions(self.admin.id, reader.id, 2, {'settlementReview': ['view']})
        response = self.client.get('/api/v1/admin/settlements/month-end?month=2026-10')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()['bills'])
        self.assertIsNone(response.json()['costs'])
        self.assertEqual(response.json()['archives']['total'], 1)
