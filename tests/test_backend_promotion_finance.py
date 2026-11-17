"""推广业务扩展使用隔离测试库，覆盖账本、权限和回单重放。"""

import csv
import io
import time
import zipfile
from datetime import datetime, timedelta
from unittest.mock import patch
from xml.etree import ElementTree

import test_backend_growth as growth
import test_backend_settlements as original
from fastapi import HTTPException

from app import db as database
from app.db import db
from app.models.promotion_finance import (
    CampaignExpense,
    CampaignExpenseUpdate,
    DisputeInput,
    DisputeReply,
    FinanceControls,
    MonthlyArchive,
    PayoutBatchInput,
    PayoutImportInput,
)
from app.models.referral_operations import CampaignInput, CampaignUpdate
from app.models.settlements import (
    BillImportInput,
    CostsInput,
    PayeeInput,
    ReceiptInput,
    ReviewInput,
    StatementInput,
    VoidInput,
)
from app.routers import referrals as referral_routes
from app.routers import settlements as routes
from app.services import (
    admin_access,
    referral_expenses,
    referral_operations,
    referral_quality,
    referrals,
    settlement_batches,
    settlement_bills,
    settlement_disputes,
    settlement_ledger,
    settlement_operations,
    settlements,
    user_store,
)
from app.services.settlement_queries import ZONE


class PromotionFinanceContracts(growth.GrowthBase):
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
        self.promoter = user_store.create_user('ledger-owner', 'test-password', role='admin')
        self.code = referrals.admin_code(self.admin.id, self.promoter.id)['code']
        with db() as conn:
            referrals.initialize_user(conn, self.viewer.id, self.code)
        self.rules()
        self.account = '6222000012345678'
        settlement_operations.save_payee(self.promoter.id, PayeeInput(name='测试收款人', method='bank', account=self.account, bank='测试银行'))

    def batch(self, statements):
        return settlement_batches.create(self.admin.id, PayoutBatchInput(name='本月推广款', statement_ids=[s['id'] for s in statements], request_key='batch-unique-key'))

    def contents(self, rows):
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(settlement_batches.HEADERS)
        for statement, amount, result, receipt in rows:
            writer.writerow([statement['id'], '测试收款人', 'bank', '测试银行', self.account, f'{amount / 100:.2f}', receipt, datetime.now(ZONE).strftime('%Y-%m-%d %H:%M:%S'), result, '测试回单'])
        return output.getvalue()

    def second_statement(self):
        owner = user_store.create_user('ledger-second-owner', 'test-password', role='admin')
        self.code = referrals.admin_code(self.admin.id, owner.id)['code']
        settlement_operations.save_payee(owner.id, PayeeInput(name='测试收款人', method='bank', account=self.account, bank='测试银行'))
        return self.approve(self.draft(self.another('second-owner-order')))

    def test_ledger_balances_refund_void_and_backfill_without_duplicate_carry(self):
        month = datetime.now(ZONE).strftime('%Y-%m')
        order = self.paid()
        approved = self.approve(self.draft(order))
        value = settlement_ledger.monthly(self.promoter.id, self.promoter.id, month)
        self.assertEqual(value['closing_fen'], approved['net_fen'])
        paid = self.payout(approved)
        self.assertEqual(settlement_ledger.monthly(self.promoter.id, self.promoter.id, month)['closing_fen'], 0)
        self.refund(order)
        self.assertEqual(settlement_ledger.monthly(self.promoter.id, self.promoter.id, month)['closing_fen'], -approved['gross_fen'])
        with db() as conn:
            settlements.add_adjustment(conn, approved['beneficiary'], approved['beneficiary_name'], -10, 'carry:test-no-double', '测试结转', '已有债项')
            settlement_ledger.backfill(conn)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM referral_ledger_events WHERE source='payment:' || ?", (paid['id'],)).fetchone()[0], 1)
        self.assertEqual(settlement_ledger.monthly(self.promoter.id, self.promoter.id, month)['closing_fen'], -approved['gross_fen'])

    def test_void_approved_reverses_only_the_approval_events(self):
        approved = self.approve(self.draft(self.paid()))
        settlements.cancel_statement(self.admin.id, approved['id'], VoidInput(revision=approved['revision'], reason='费用需重新核定'))
        result = settlement_ledger.monthly(self.promoter.id, self.promoter.id, datetime.now(ZONE).strftime('%Y-%m'))
        self.assertEqual(result['closing_fen'], 0)
        self.assertEqual(result['totals']['void_reward'], -approved['gross_fen'])

    def test_month_archive_is_immutable_late_events_enter_next_open_month(self):
        now = datetime.now(ZONE)
        end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last = end - timedelta(days=1)
        month = last.strftime('%Y-%m')
        with db() as conn:
            settlement_ledger.event(conn, 'test-old', 'admin:' + str(self.promoter.id), 'reward', 100, int(last.timestamp()))
        quoted = settlement_ledger.monthly(self.admin.id, self.promoter.id, month)
        archive = MonthlyArchive(admin_id=self.promoter.id, month=month, quote_digest=quoted['quote_digest'])
        saved = settlement_ledger.archive(self.admin.id, archive)
        with db() as conn:
            settlement_ledger.event(conn, 'test-late', 'admin:' + str(self.promoter.id), 'adjustment', -20, int(last.timestamp()))
        self.assertEqual(saved, settlement_ledger.archive(self.admin.id, archive))
        current = settlement_ledger.monthly(self.promoter.id, self.promoter.id, now.strftime('%Y-%m'))
        self.assertEqual(current['opening_fen'], 100)
        self.assertEqual(current['closing_fen'], 80)
        self.assertEqual(current['items'][0]['original_at'], int(last.timestamp()))
        self.assertEqual(current['items'][0]['occurred_at'], int(end.timestamp()))
        with self.assertRaises(HTTPException):
            settlement_ledger.archive(self.admin.id, MonthlyArchive(admin_id=self.promoter.id, month=now.strftime('%Y-%m'), quote_digest=current['quote_digest']))
        with self.assertRaises(HTTPException):
            settlement_ledger.monthly(self.promoter.id, self.admin.id, month)
        self.assertTrue(settlement_ledger.export(self.promoter.id, self.promoter.id, month).startswith(b'PK'))

    def test_month_archive_rejects_changed_preview_including_opening_balance(self):
        end = datetime.now(ZONE).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month = (end - timedelta(days=1)).strftime('%Y-%m')
        quoted = settlement_ledger.monthly(self.admin.id, self.promoter.id, month)
        body = MonthlyArchive(admin_id=self.promoter.id, month=month, quote_digest=quoted['quote_digest'])
        with db() as conn:
            start, _ = settlement_ledger.month_range(month)
            settlement_ledger.event(conn, 'opening-change', 'admin:' + str(self.promoter.id), 'adjustment', 50, start - 1)
        with self.assertRaises(HTTPException) as raised:
            settlement_ledger.archive(self.admin.id, body)
        self.assertEqual(raised.exception.status_code, 409)
        with db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM referral_monthly_reports').fetchone()[0], 0)
        fresh = settlement_ledger.monthly(self.admin.id, self.promoter.id, month)
        self.assertNotEqual(fresh['quote_digest'], quoted['quote_digest'])
        saved = settlement_ledger.archive(self.admin.id, body.model_copy(update={'quote_digest': fresh['quote_digest']}))
        self.assertEqual(saved['opening_fen'], 50)
        self.assertEqual(saved['quote_digest'], fresh['quote_digest'])

    def test_old_database_upgrade_adds_finance_tables_and_backfills_existing_statements(self):
        approved = self.approve(self.draft(self.paid()))
        with db(ddl=True) as conn:
            conn.execute('DROP TABLE referral_dispute_files,referral_dispute_messages,referral_disputes,referral_payout_imports,referral_payout_batch_items,referral_payout_batches,referral_monthly_reports,referral_ledger_events,referral_finance_controls,referral_campaign_expenses')
            conn.execute('DELETE FROM schema_migrations WHERE version=?', (database.SCHEMA_VERSION,))
            conn.execute('INSERT INTO schema_migrations(version) VALUES(2026111106) ON CONFLICT DO NOTHING')
        with self.assertRaises(RuntimeError):
            database.init_db(migrate=False)
        database.init_db(migrate=True)
        database.init_db(migrate=False)
        with db() as conn:
            self.assertEqual(database._verify_schema(conn)[0], [])
            self.assertEqual(conn.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0], database.SCHEMA_VERSION)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM referral_ledger_events WHERE statement_id=?', (approved['id'],)).fetchone()[0], 3)
            settlement_ledger.backfill(conn)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM referral_ledger_events WHERE statement_id=?', (approved['id'],)).fetchone()[0], 3)
        self.assertEqual(settlement_ledger.monthly(self.promoter.id, self.promoter.id, datetime.now(ZONE).strftime('%Y-%m'))['closing_fen'], approved['net_fen'])

    def test_batch_zero_writeoff_accepts_no_transfer_time_but_keeps_receipt_validation(self):
        draft = self.draft(self.paid())
        approved = self.approve(draft, personal=draft['gross_fen'], tax=0)
        self.assertEqual(approved['net_fen'], 0)
        batch = self.batch([approved])
        rows = list(csv.DictReader(io.StringIO(settlement_batches.export(self.admin.id, batch['id']).decode('utf-8-sig'))))
        rows[0].update({'流水号': 'zero-writeoff-proof', '结果': '成功'})
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=settlement_batches.HEADERS)
        writer.writeheader()
        writer.writerows(rows)
        content = output.getvalue()
        self.assertEqual(settlement_batches.preview(self.admin.id, batch['id'], content)['blocked'], 0)
        self.assertTrue(settlement_batches.parse(content.replace('zero-writeoff-proof', ''))[0]['issues'])
        self.assertTrue(settlement_batches.parse(content.replace('0.00', '1.00'))[0]['issues'])
        result = settlement_batches.import_receipts(self.admin.id, batch['id'], PayoutImportInput(revision=1, content=content, confirmed=True))
        self.assertEqual(result['paid'], 1)
        row = settlement_operations.statement_detail(self.admin.id, approved['id'])['statement']
        self.assertEqual(row['status'], 'paid')
        self.assertIsNone(row['payout']['transferred_at'])

    def test_bill_import_rechecks_permission_after_parsing_before_write(self):
        user = user_store.create_user('bill-costs-delegate', 'test-password', role='admin')
        admin_access.save_permissions(self.admin.id, user.id, 1, {'settlementCosts': ['view', 'run']})
        original_money = settlement_bills.money
        revoked = False

        def parse_money(value):
            nonlocal revoked
            if not revoked:
                admin_access.save_permissions(self.admin.id, user.id, 2, {'settlements': ['view']})
                revoked = True
            return original_money(value)

        content = settlement_bills.template() + 'order-test,transaction-test,wechat,10.00,0.01,0.00,2026-10-01\r\n'
        with patch.object(settlement_bills, 'money', side_effect=parse_money), self.assertRaises(HTTPException) as raised:
            settlement_bills.import_bill(user.id, BillImportInput(name='导入期间撤销授权', evidence='测试账单', content=content))
        self.assertEqual(raised.exception.status_code, 403)
        with db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM referral_bill_imports').fetchone()[0], 0)

    def test_expense_retry_returns_original_record_even_after_edit_and_void(self):
        campaign = referral_operations.save_campaign(self.promoter.id, CampaignInput(name='费用重试活动', source='微信群'))
        body = CampaignExpense(expense_date=datetime.now(ZONE).strftime('%Y-%m-%d'), category='广告', amount_fen=2000, evidence='重试凭据001', request_key='expense-retry-key')
        first = referral_expenses.save(self.promoter.id, campaign['id'], body)
        self.assertEqual(referral_expenses.save(self.promoter.id, campaign['id'], body), first)
        with self.assertRaises(HTTPException) as raised:
            referral_expenses.save(self.promoter.id, campaign['id'], body.model_copy(update={'amount_fen': 3000}))
        self.assertEqual(raised.exception.status_code, 409)
        update = CampaignExpenseUpdate(**{**body.model_dump(exclude={'request_key'}), 'amount_fen': 2500}, revision=1, active=False)
        changed = referral_expenses.save(self.promoter.id, campaign['id'], update, first['id'])
        self.assertEqual(referral_expenses.save(self.promoter.id, campaign['id'], body), changed)
        self.assertEqual(referral_expenses.listing(self.promoter.id, campaign['id'])['total'], 1)
        with db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM referral_settlement_audit WHERE target=? AND kind='campaign_expense_saved'", (first['id'],)).fetchone()[0], 2)

    def test_batch_mixed_receipts_match_retry_and_idempotence(self):
        first = self.approve(self.draft(self.paid()))
        second = self.second_statement()
        batch = self.batch([first, second])
        self.assertEqual(batch, self.batch([first, second]))
        self.assertIn(self.account, settlement_batches.export(self.admin.id, batch['id']).decode())
        content = self.contents([(first, first['net_fen'], '成功', 'bank-first'), (second, second['net_fen'], '失败', '')])
        self.assertEqual(settlement_batches.preview(self.admin.id, batch['id'], content)['matched'], 2)
        body = PayoutImportInput(revision=batch['revision'], content=content, confirmed=True)
        result = settlement_batches.import_receipts(self.admin.id, batch['id'], body)
        self.assertEqual((result['paid'], result['failed']), (1, 1))
        self.assertTrue(settlement_batches.import_receipts(self.admin.id, batch['id'], body)['duplicate'])
        self.assertEqual(settlement_operations.statement_detail(self.admin.id, second['id'])['statement']['status'], 'approved')
        retry = self.contents([(second, second['net_fen'], '成功', 'bank-second')])
        result = settlement_batches.import_receipts(self.admin.id, batch['id'], PayoutImportInput(revision=2, content=retry, confirmed=True))
        self.assertEqual(result['paid'], 1)
        self.assertEqual(settlement_batches.listing(self.admin.id)['items'][0]['status'], 'completed')
        with db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM referral_ledger_events WHERE kind='payment'").fetchone()[0], 2)

    def test_batch_rechecks_account_amount_and_refund_and_releases_on_cancel(self):
        order = self.paid()
        first = self.approve(self.draft(order))
        batch = self.batch([first])
        with self.assertRaises(HTTPException):
            self.payout(first)
        invalid = self.contents([(first, first['net_fen'] + 1, '成功', 'wrong-amount')]).replace(self.account, 'wrong-account')
        check = settlement_batches.preview(self.admin.id, batch['id'], invalid)
        self.assertEqual(check['blocked'], 1)
        self.assertIn('收款账号', ' '.join(check['items'][0]['issues']))
        result = settlement_batches.import_receipts(self.admin.id, batch['id'], PayoutImportInput(revision=1, content=invalid, confirmed=True))
        self.assertEqual((result['paid'], result['blocked']), (0, 1))
        valid = self.contents([(first, first['net_fen'], '成功', 'valid-after-refund')])
        self.refund(order)
        self.assertEqual(settlement_batches.preview(self.admin.id, batch['id'], valid)['blocked'], 1)
        settlement_batches.cancel(self.admin.id, batch['id'], 2)
        with db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM referral_payout_batch_items WHERE status IN ('pending','failed')").fetchone()[0], 0)

    def test_delegated_stage_permissions_and_independent_review_payment(self):
        actors = []
        for stage in ('Costs', 'Review', 'Payout'):
            user = user_store.create_user('finance-' + stage.lower(), 'test-password', role='admin')
            actors.append(user)
            admin_access.save_permissions(self.admin.id, user.id, 1, {'settlement' + stage: ['view', 'run', *(['export'] if stage == 'Payout' else [])]})
        costs, review, payout = actors
        controls = FinanceControls(revision=1, separate_review=True, separate_payment=True)
        from app.routers.promotion_finance import save_controls
        save_controls(controls, self.admin)
        order = self.paid()
        reward = self.reward(order)
        costs_body = CostsInput(revision=reward['revision'], channel_fee_fen=12, shared_fees=[], evidence='账单核对凭据', confirmed=True)
        settlements.confirm_costs(costs.id, order['id'], costs_body)
        draft = settlements.create_statement(costs.id, StatementInput(order_ids=[order['id']]))
        body = ReviewInput(revision=draft['revision'], personal_fees=[], tax_fen=0, evidence='复核凭据', confirmed=True)
        with self.assertRaises(HTTPException):
            settlements.approve(costs.id, draft['id'], body)
        # 即使一个账号同时得到两种授权，独立复核规则仍拦截同人操作。
        admin_access.save_permissions(self.admin.id, costs.id, 2, {'settlementCosts': ['view', 'run'], 'settlementReview': ['view', 'run']})
        with self.assertRaises(HTTPException):
            settlements.approve(costs.id, draft['id'], body)
        approved = settlements.approve(review.id, draft['id'], body)
        payout_body = ReceiptInput(revision=approved['revision'], amount_fen=approved['net_fen'], receipt='delegated-payment', transferred_at=int(time.time()))
        with self.assertRaises(HTTPException):
            settlements.record_payout(review.id, approved['id'], payout_body)
        admin_access.save_permissions(self.admin.id, review.id, 2, {'settlementReview': ['view', 'run'], 'settlementPayout': ['view', 'run']})
        with self.assertRaises(HTTPException) as raised:
            settlements.record_payout(review.id, approved['id'], payout_body)
        self.assertEqual(raised.exception.status_code, 409)
        settled = settlements.record_payout(payout.id, approved['id'], payout_body)
        self.assertEqual(settled['status'], 'paid')
        admin_access.save_permissions(self.admin.id, costs.id, 3, {'settlementCosts': ['view', 'run']})
        self.sign_in(costs)
        self.assertEqual(self.client.get('/api/v1/admin/settlements/list/statements').json()['total'], 1)
        self.assertEqual(self.client.post('/api/v1/admin/settlements/statements/' + draft['id'] + '/approve', json=body.model_dump()).status_code, 403)
        self.assertIn(self.promoter.id, [item['id'] for item in self.client.get('/api/v1/admin/settlements/admins').json()['items']])
        self.assertEqual(self.client.get('/api/v1/admin/settlements/batches').status_code, 403)

    def test_expense_ledger_scope_versions_void_period_and_roi(self):
        campaign = referral_operations.save_campaign(self.promoter.id, CampaignInput(name='投入测试活动', source='微信群', spend_fen=1000))
        day = datetime.now(ZONE).strftime('%Y-%m-%d')
        body = CampaignExpense(expense_date=day, category='广告', amount_fen=2000, evidence='广告账单-001', note='本次新增', request_key='expense-draft-key')
        item = referral_expenses.save(self.promoter.id, campaign['id'], body)
        value = referral_expenses.listing(self.promoter.id, campaign['id'], day, day)
        self.assertEqual((value['baseline_fen'], value['period_fen'], value['cumulative_fen']), (1000, 2000, 3000))
        self.assertEqual(referral_operations.performance(self.promoter.id, campaign['id'])['spend_fen'], 3000)
        update = CampaignExpenseUpdate(**body.model_dump(exclude={'request_key'}), revision=1, active=False)
        referral_expenses.save(self.promoter.id, campaign['id'], update, item['id'])
        self.assertEqual(referral_expenses.listing(self.promoter.id, campaign['id'])['cumulative_fen'], 1000)
        with self.assertRaises(HTTPException):
            referral_expenses.save(self.promoter.id, campaign['id'], update, item['id'])
        other = user_store.create_user('expense-other', 'test-password', role='admin')
        with self.assertRaises(HTTPException):
            referral_expenses.listing(other.id, campaign['id'])
        with self.assertRaises(HTTPException):
            referral_expenses.save(self.promoter.id, campaign['id'], body.model_copy(update={'expense_date': '2026-02-30'}))

    def test_finance_cost_ledger_aggregates_original_records_and_preserves_cumulative_scope(self):
        day = datetime.now(ZONE).strftime('%Y-%m-%d')
        campaigns = [referral_operations.save_campaign(self.admin.id, CampaignInput(admin_id=owner, name=name, source='微信群', spend_fen=baseline)) for owner, name, baseline in [(self.promoter.id, '财务汇总甲', 1000), (self.admin.id, '财务汇总乙', 2000), (self.admin.id, '成本未知活动', None)]]
        for index, campaign in enumerate(campaigns[:2]):
            referral_expenses.save(self.admin.id, campaign['id'], CampaignExpense(expense_date=day, category='广告', amount_fen=(index + 1) * 200, evidence='原始广告凭据', request_key=f'finance-expense-{index}'))
        result = referral_expenses.finance_listing(self.admin.id)
        self.assertEqual((result['total'], result['period_fen'], result['baseline_fen'], result['cumulative_fen'], result['unknown_campaigns']), (2, 600, 3000, 3600, 1))
        result = referral_expenses.finance_listing(self.admin.id, admin_id=self.promoter.id)
        self.assertEqual((result['total'], result['cumulative_fen']), (1, 1200))
        filtered = referral_expenses.finance_listing(self.admin.id, campaign_id=campaigns[0]['id'], end_date='2020-01-01')
        self.assertEqual((filtered['total'], filtered['period_fen'], filtered['cumulative_fen']), (0, 0, 1200))
        self.assertEqual(referral_expenses.finance_listing(self.admin.id, q='%')['total'], 0)
        row = result['items'][0]
        referral_expenses.save(self.admin.id, row['campaign_id'], CampaignExpenseUpdate(expense_date=day, category=row['category'], amount_fen=row['amount_fen'], evidence=row['evidence'], note=row['note'], revision=row['revision'], active=False), row['id'])
        voided = referral_expenses.finance_listing(self.admin.id, admin_id=self.promoter.id, state='void')
        self.assertEqual((voided['total'], voided['period_fen'], voided['cumulative_fen']), (1, 0, 1000))
        with self.assertRaises(HTTPException):
            referral_expenses.finance_listing(self.admin.id, start_date=day, end_date='2020-01-01')

    def test_finance_cost_scope_requires_live_finance_view_without_granting_promotion_access(self):
        campaign = referral_operations.save_campaign(self.promoter.id, CampaignInput(name='财务只读成本', source='微信群'))
        actor = user_store.create_user('finance-cost-viewer', 'test-password', role='admin')
        admin_access.save_permissions(self.admin.id, actor.id, 1, {'settlementCosts': ['view']})
        self.sign_in(actor)
        self.assertEqual(self.client.get('/api/v1/admin/settlements/expenses').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/admin/referrals/campaigns/' + campaign['id'] + '/expenses').status_code, 403)
        admin_access.save_permissions(self.admin.id, actor.id, 2, {'settlements': ['view']})
        self.assertEqual(self.client.get('/api/v1/admin/settlements/expenses').status_code, 403)
        with self.assertRaises(HTTPException):
            referral_expenses.finance_listing(actor.id)

    def test_finance_cost_export_includes_full_scope_and_safe_text_with_independent_permission(self):
        day = datetime.now(ZONE).strftime('%Y-%m-%d')
        campaign = referral_operations.save_campaign(self.admin.id, CampaignInput(admin_id=self.promoter.id, name='台账导出活动', source='微信群', spend_fen=1000))
        for index in range(25):
            referral_expenses.save(self.admin.id, campaign['id'], CampaignExpense(expense_date=day, category='广告', amount_fen=100 + index, evidence='=1+1', note='原始凭据', request_key=f'export-expense-{index}'))
        actor = user_store.create_user('cost-export-reader', 'test-password', role='admin')
        admin_access.save_permissions(self.admin.id, actor.id, 1, {'settlementCosts': ['view']})
        self.sign_in(actor)
        url = '/api/v1/admin/settlements/expenses/export.xlsx'
        self.assertEqual(self.client.get(url).status_code, 403)
        admin_access.save_permissions(self.admin.id, actor.id, 2, {'settlementCosts': ['view', 'export']})
        response = self.client.get(url, params={'campaign_id': campaign['id'], 'start_date': day, 'end_date': day, 'state': 'active'})
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            rows = archive.read('xl/worksheets/sheet1.xml').decode()
            scope = archive.read('xl/worksheets/sheet2.xml').decode()
        self.assertEqual(rows.count('<row '), 26)
        self.assertIn('=1+1', rows)
        self.assertNotIn('<f>', rows)
        self.assertIn('1.24', rows)
        ns = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        values = {''.join(row[0].itertext()): ''.join(row[1].itertext()) for row in ElementTree.fromstring(scope).findall('.//x:row', ns)}
        self.assertEqual(values['日期范围有效投入（元）'], '28')
        self.assertEqual(values['此前累计投入（元，已填写）'], '10')
        self.assertEqual(values['全部累计投入（元，已知小计）'], '38')
        empty = self.client.get(url, params={'campaign_id': campaign['id'], 'end_date': '2020-01-01'})
        self.assertEqual(empty.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(empty.content)) as archive:
            self.assertEqual(archive.read('xl/worksheets/sheet1.xml').count(b'<row '), 1)
        admin_access.save_permissions(self.admin.id, actor.id, 3, {'settlementCosts': ['view']})
        self.assertEqual(self.client.get(url).status_code, 403)
        with self.assertRaises(HTTPException):
            referral_expenses.finance_export(actor.id)

    def test_finance_cost_export_refuses_silent_truncation(self):
        with patch('app.services.referral_expenses._finance_listing', return_value={'total': 5001}):
            with self.assertRaises(HTTPException) as error:
                referral_expenses.finance_export(self.admin.id)
        self.assertEqual(error.exception.status_code, 422)

    def test_batch_search_pagination_and_independent_detail_keep_live_payout_permission(self):
        statement = self.approve(self.draft(self.paid()))
        current = self.batch([statement])
        with db() as conn:
            for index in range(25):
                conn.execute('INSERT INTO referral_payout_batches(id,name,request_key,actor_id,created_at,status) VALUES(?,?,?,?,?,?)', (f'archive-{index}', f'历史月度批次{index}', f'archive-key-{index}', self.admin.id, index, 'completed'))
            conn.execute('UPDATE referral_payout_batches SET name=? WHERE id=?', ('待付%批次', current['id']))
        listing = settlement_batches.listing(self.admin.id, q='历史月度', status='completed')
        self.assertEqual((listing['total'], len(listing['items'])), (25, 20))
        self.assertEqual(len(settlement_batches.listing(self.admin.id, page=2, q='历史月度', status='completed')['items']), 5)
        self.assertEqual(settlement_batches.listing(self.admin.id, q='%', status='active')['items'][0]['id'], current['id'])
        self.sign_in(self.admin)
        self.assertEqual(self.client.get('/api/v1/admin/settlements/batches/' + current['id']).json()['items'][0]['statement_id'], statement['id'])
        actor = user_store.create_user('batch-detail-reader', 'test-password', role='admin')
        admin_access.save_permissions(self.admin.id, actor.id, 1, {'settlementPayout': ['view']})
        self.sign_in(actor)
        self.assertEqual(self.client.get('/api/v1/admin/settlements/batches/' + current['id']).status_code, 200)
        admin_access.save_permissions(self.admin.id, actor.id, 2, {'settlementCosts': ['view']})
        self.assertEqual(self.client.get('/api/v1/admin/settlements/batches/' + current['id']).status_code, 403)

    def test_finance_personal_disputes_and_notice_read_positions_are_separate(self):
        order = self.paid()
        first = settlement_disputes.create(self.promoter.id, DisputeInput(target_kind='reward', target_id=order['id'], title='本人异议', content='核对本人奖励', request_key='personal-issue-key'))
        other = self.second_statement()
        owner = int(other['beneficiary'].split(':')[1])
        second = settlement_disputes.create(owner, DisputeInput(target_kind='statement', target_id=other['id'], title='其他异议', content='核对其他奖励', request_key='other-issue-key'))
        admin_access.save_permissions(self.admin.id, self.promoter.id, 1, {'settlementReview': ['view', 'run']})
        self.assertEqual(settlement_disputes.listing(self.promoter.id)['total'], 2)
        self.assertEqual([row['id'] for row in settlement_disputes.listing(self.promoter.id, personal=True)['items']], [first['id']])
        with db() as conn, self.assertRaises(HTTPException):
            settlement_disputes.detail(conn, self.promoter.id, second['id'], personal=True)
        with db() as conn:
            settlements.audit(conn, self.admin.id, 'approve', 'foreign-notice', {'beneficiary': 'admin:' + str(owner)})
            settlements.audit(conn, self.admin.id, 'approve', 'own-notice', {'beneficiary': 'admin:' + str(self.promoter.id)})
        before = settlement_operations.notices(self.promoter.id)
        own = settlement_operations.notices(self.promoter.id, personal=True)
        self.assertTrue(all(item['target'] != 'foreign-notice' for item in own['items']))
        settlement_operations.read_notices(self.promoter.id, own['items'][0]['id'], personal=True)
        self.assertEqual(settlement_operations.notices(self.promoter.id, personal=True)['unread'], 0)
        self.assertEqual(settlement_operations.notices(self.promoter.id)['unread'], before['unread'])

    def test_finance_read_first_preserves_personal_cursor_for_new_and_legacy_accounts(self):
        admin_access.save_permissions(self.admin.id, self.promoter.id, 1, {'settlementReview': ['view', 'run']})
        with db() as conn:
            for target in ('first-own-notice', 'latest-own-notice'):
                settlements.audit(conn, self.admin.id, 'approve', target, {'beneficiary': 'admin:' + str(self.promoter.id)})
        initial = settlement_operations.notices(self.promoter.id, personal=True)
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                with db() as conn:
                    conn.execute('DELETE FROM referral_notice_reads WHERE actor_id=?', (self.promoter.id,))
                    if legacy:
                        conn.execute('INSERT INTO referral_notice_reads(actor_id,last_id) VALUES(?,?)', (self.promoter.id, initial['items'][-1]['id']))
                own = settlement_operations.notices(self.promoter.id, personal=True)
                financial = settlement_operations.notices(self.promoter.id)
                settlement_operations.read_notices(self.promoter.id, financial['items'][0]['id'])
                self.assertEqual(settlement_operations.notices(self.promoter.id)['unread'], 0)
                after = settlement_operations.notices(self.promoter.id, personal=True)
                self.assertEqual((after['unread'], after['last_id']), (own['unread'], own['last_id']))
                self.assertGreater(after['unread'], 0)
                settlement_operations.read_notices(self.promoter.id, after['items'][0]['id'], personal=True)
                last_id = settlement_operations.notices(self.promoter.id, personal=True)['last_id']
                settlement_operations.read_notices(self.promoter.id, initial['items'][-1]['id'], personal=True)
                self.assertEqual(settlement_operations.notices(self.promoter.id, personal=True)['last_id'], last_id)

    def test_disputes_scope_idempotence_payment_block_and_resolution_keep_snapshot(self):
        order = self.paid()
        draft = self.draft(order)
        body = DisputeInput(target_kind='reward', target_id=order['id'], title='奖励金额疑问', content='请复核本笔扣费依据', evidence='凭据001', request_key='dispute-key-001')
        issue = settlement_disputes.create(self.promoter.id, body)
        self.assertEqual(issue['id'], settlement_disputes.create(self.promoter.id, body)['id'])
        with self.assertRaises(HTTPException):
            self.approve(draft)
        with self.assertRaises(HTTPException):
            settlement_disputes.reply(self.promoter.id, issue['id'], DisputeReply(revision=1, content='自行关闭问题', status='resolved'))
        other = user_store.create_user('dispute-other', 'test-password', role='admin')
        self.assertEqual(settlement_disputes.listing(other.id)['total'], 0)
        with self.assertRaises(HTTPException):
            settlement_disputes.create(other.id, body)
        settled_issue = settlement_disputes.reply(self.admin.id, issue['id'], DisputeReply(revision=1, content='已核对费用凭据，原金额正确', evidence='费用原始账单', status='resolved'))
        self.assertEqual(settled_issue['status'], 'resolved')
        self.assertEqual(settlement_operations.statement_detail(self.admin.id, draft['id'])['statement']['snapshot'], draft['snapshot'])
        self.assertEqual(self.approve(draft)['status'], 'approved')

    def test_dispute_attachments_validate_content_owner_and_closed_state(self):
        order = self.paid()
        issue = settlement_disputes.create(self.promoter.id, DisputeInput(target_kind='reward', target_id=order['id'], title='凭据问题', content='请查看附件', request_key='dispute-files-key'))
        pdf = b'%PDF-1.4\nexample\n%%EOF'
        file = settlement_disputes.upload(self.promoter.id, issue['id'], 'evidence.pdf', pdf)
        self.assertEqual(file, settlement_disputes.upload(self.promoter.id, issue['id'], 'evidence.pdf', pdf))
        self.assertEqual(settlement_disputes.file(self.admin.id, file['id'])['content'], pdf)
        with self.assertRaises(HTTPException):
            settlement_disputes.upload(self.promoter.id, issue['id'], 'fake.png', b'invalid')
        settlement_disputes.reply(self.admin.id, issue['id'], DisputeReply(revision=2, content='凭据已核对', status='resolved'))
        with self.assertRaises(HTTPException):
            settlement_disputes.upload(self.promoter.id, issue['id'], 'more.pdf', pdf)

    def test_quality_completed_windows_refund_cutoff_and_immature_exclusion(self):
        first = self.paid('quality-first')
        renewal = self.paid('quality-renewal')
        self.refund(first)
        recent = self.another('quality-recent-user')
        now = int(time.time())
        registered = now - 120 * 86400
        with db() as conn:
            conn.execute('UPDATE mini_users SET created_at=? WHERE id=?', (registered, self.viewer.id))
            for order, days in ((first, 5), (renewal, 20)):
                conn.execute('UPDATE mini_orders SET created_at=?,paid_at=? WHERE id=?', (registered + days * 86400, registered + days * 86400, order['id']))
            conn.execute('UPDATE mini_refunds SET completed_at=? WHERE order_id=?', (registered + 45 * 86400, first['id']))
            conn.execute('UPDATE mini_users SET created_at=? WHERE id=(SELECT user_id FROM mini_orders WHERE id=?)', (now - 10 * 86400, recent['id']))
        value = referral_quality.quality(self.promoter.id)
        self.assertEqual(value['total'], 1)
        row30, row60, row90 = value['items']
        self.assertEqual((row30['observed_users'], row30['waiting_users'], row30['paying_users'], row30['renewing_users'], row30['refunded_users']), (1, 1, 1, 1, 0))
        self.assertEqual(row30['net_fen'], first['amount_fen'] + renewal['amount_fen'])
        self.assertEqual(row60['net_fen'], renewal['amount_fen'])
        self.assertEqual(row90['refunded_users'], 1)
        with self.assertRaises(HTTPException):
            referral_quality.quality(self.promoter.id, admin_id=self.admin.id)

    def test_cost_reference_blocks_renamed_duplicates_but_allows_distinct_invoice_items(self):
        order = self.paid()
        reward = self.reward(order)
        def costs(fees):
            return CostsInput(revision=reward['revision'], channel_fee_fen=0, shared_fees=fees, evidence='实际分摊凭据', confirmed=True)
        with self.assertRaises(HTTPException) as raised:
            settlements.confirm_costs(self.admin.id, order['id'], costs([
                {'name': '广告投放', 'amount_fen': 10, 'source_ref': 'ＦＰ００１ / 广告'},
                {'name': '宣传服务', 'amount_fen': 10, 'source_ref': 'fp001/广告'},
            ]))
        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(self.reward(order)['revision'], reward['revision'])
        updated = settlements.confirm_costs(self.admin.id, order['id'], costs([
            {'name': '广告投放', 'amount_fen': 10, 'source_ref': 'ＦＰ００１ / 广告'},
            {'name': '物料印刷', 'amount_fen': 10, 'source_ref': 'FP001/物料'},
        ]))
        self.assertEqual(updated['costs']['shared_fees'][0]['source_ref'], 'fp001/广告')
        statement = settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id']]))
        body = ReviewInput(revision=statement['revision'], personal_fees=[{'name': '另一名称', 'amount_fen': 1, 'source_ref': 'FP001/广告'}], tax_fen=0, evidence='审核凭据', confirmed=True)
        with self.assertRaises(HTTPException) as raised:
            settlements.approve(self.admin.id, statement['id'], body)
        self.assertIn('共同费用', raised.exception.detail['error'])
        valid = body.model_copy(update={'personal_fees': []})
        approved = settlements.approve(self.admin.id, statement['id'], valid)
        from app.models.settlements import SettlementFilters
        from app.services import settlement_export
        with zipfile.ZipFile(io.BytesIO(settlement_export.export(self.admin.id, 'statements', SettlementFilters()))) as archive:
            self.assertIn('fp001/广告', archive.read('xl/worksheets/sheet3.xml').decode())
        self.assertEqual(approved['status'], 'approved')

    def test_expense_reference_is_unique_across_campaigns_retry_void_and_restore(self):
        campaigns = [referral_operations.save_campaign(self.promoter.id, CampaignInput(name=name, source='微信群')) for name in ('费用甲', '费用乙')]
        body = CampaignExpense(expense_date=datetime.now(ZONE).strftime('%Y-%m-%d'), category='广告', amount_fen=500, evidence='凭据说明', source_ref='ＦＰ００２ / 广告', request_key='reference-expense-key')
        item = referral_expenses.save(self.promoter.id, campaigns[0]['id'], body)
        self.assertEqual(referral_expenses.save(self.promoter.id, campaigns[0]['id'], body)['id'], item['id'])
        with self.assertRaises(HTTPException):
            referral_expenses.save(self.promoter.id, campaigns[1]['id'], body.model_copy(update={'source_ref': 'fp002/广告'}))
        update = CampaignExpenseUpdate(**body.model_dump(exclude={'request_key'}), revision=1, active=False)
        referral_expenses.save(self.promoter.id, campaigns[0]['id'], update, item['id'])
        other = referral_expenses.save(self.promoter.id, campaigns[1]['id'], body)
        self.assertEqual(other['source_ref'], 'fp002/广告')
        with self.assertRaises(HTTPException):
            referral_expenses.save(self.promoter.id, campaigns[0]['id'], update.model_copy(update={'revision': 2, 'active': True}), item['id'])
        self.assertFalse(referral_expenses.listing(self.promoter.id, campaigns[0]['id'])['items'][0]['active'])

    def test_historical_expense_details_do_not_add_to_baseline_and_validate_edits(self):
        campaign = referral_operations.save_campaign(self.promoter.id, CampaignInput(name='累计补录', source='微信群', spend_fen=1000))
        day = datetime.now(ZONE).strftime('%Y-%m-%d')
        body = CampaignExpense(expense_date=day, category='物料', amount_fen=700, evidence='历史发票', source_ref='old/物料', included_in_baseline=True, request_key='historical-expense-key')
        item = referral_expenses.save(self.promoter.id, campaign['id'], body)
        extra = body.model_copy(update={'amount_fen': 200, 'source_ref': 'new/广告', 'included_in_baseline': False, 'request_key': 'additional-expense-key'})
        referral_expenses.save(self.promoter.id, campaign['id'], extra)
        result = referral_expenses.finance_listing(self.admin.id, campaign_id=campaign['id'])
        self.assertEqual((result['period_fen'], result['cumulative_fen']), (900, 1200))
        self.assertEqual(referral_operations.performance(self.promoter.id, campaign['id'])['spend_fen'], 1200)
        with self.assertRaises(HTTPException):
            referral_expenses.save(self.promoter.id, campaign['id'], body.model_copy(update={'source_ref': 'old/其他', 'request_key': 'over-baseline-expense'}))
        with self.assertRaises(HTTPException):
            referral_operations.save_campaign(self.promoter.id, CampaignUpdate(name='累计补录', source='微信群', spend_fen=600, active=True, revision=campaign['revision']), campaign['id'])
        self.assertEqual(referral_expenses.listing(self.promoter.id, campaign['id'])['baseline_fen'], 1000)
        legacy = CampaignExpenseUpdate(expense_date=day, category='物料', amount_fen=700, evidence='补充历史说明', revision=1)
        kept = referral_expenses.save(self.promoter.id, campaign['id'], legacy, item['id'])
        self.assertTrue(kept['included_in_baseline'])
        self.assertEqual(kept['source_ref'], 'old/物料')
        update = CampaignExpenseUpdate(**body.model_dump(exclude={'request_key'}), revision=2, active=False)
        referral_expenses.save(self.promoter.id, campaign['id'], update, item['id'])
        self.assertEqual(referral_expenses.listing(self.promoter.id, campaign['id'])['cumulative_fen'], 1200)
        empty = referral_operations.save_campaign(self.promoter.id, CampaignInput(name='尚无累计', source='微信群'))
        with self.assertRaises(HTTPException):
            referral_expenses.save(self.promoter.id, empty['id'], body)

    def test_payment_detail_explains_batch_reservation_until_cancelled(self):
        approved = self.approve(self.draft(self.paid()))
        batch = self.batch([approved])
        value = settlement_operations.statement_detail(self.admin.id, approved['id'])
        self.assertEqual(value['payout_batch_id'], batch['id'])
        self.assertTrue(any(issue.get('purpose') == 'payment' and '付款批次' in issue['reasons'][0] for issue in value['operation_issues']))
        settlement_batches.cancel(self.admin.id, batch['id'], batch['revision'])
        self.assertIsNone(settlement_operations.statement_detail(self.admin.id, approved['id'])['payout_batch_id'])
