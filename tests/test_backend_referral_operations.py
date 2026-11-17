"""推广运营与财务扩展只在隔离数据库验证，不调用真实支付。"""

import io
import json
import time
import zipfile
from datetime import datetime
from unittest.mock import patch
from xml.etree import ElementTree

import test_backend_growth as growth
import test_backend_settlements as settlement_tests
from fastapi import HTTPException
from PIL import Image

from app.db import db
from app.models.referral_operations import CampaignInput, CampaignUpdate
from app.models.settlements import (
    BillImportInput,
    BudgetInput,
    CostsInput,
    PayeeInput,
    ReceiptInput,
    RecoveryInput,
    ReviewInput,
    Revision,
    SettlementApplyInput,
    SettlementFilters,
    SettlementPreviewInput,
    StatementInput,
)
from app.routers import referrals as referral_routes
from app.routers import settlements as routes
from app.services import (
    admin_access,
    payment_bills,
    referral_operations,
    referrals,
    settlement_bills,
    settlement_export,
    settlement_operations,
    settlement_queries,
    settlements,
    user_store,
)


class ReferralOperationsContracts(growth.GrowthBase):
    configure = settlement_tests.SettlementContracts.configure
    create_order = settlement_tests.SettlementContracts.create_order
    paid_value = settlement_tests.SettlementContracts.paid_value
    rules = settlement_tests.SettlementContracts.rules
    reward = settlement_tests.SettlementContracts.reward
    costs = settlement_tests.SettlementContracts.costs
    paid = settlement_tests.SettlementContracts.paid
    another = settlement_tests.SettlementContracts.another
    draft = settlement_tests.SettlementContracts.draft
    approve = settlement_tests.SettlementContracts.approve
    payout = settlement_tests.SettlementContracts.payout
    refund = settlement_tests.SettlementContracts.refund
    batch_order = settlement_tests.SettlementContracts.batch_order

    def setUp(self):
        super().setUp()
        self.client.app.include_router(routes.router)
        self.client.app.include_router(referral_routes.router)
        self.configure()
        self.promoter = user_store.create_user('finance-owner', 'test-password', role='admin')
        self.code = referrals.admin_code(self.admin.id, self.promoter.id)['code']
        with db() as conn:
            referrals.initialize_user(conn, self.viewer.id, self.code)
        self.rules(channel_rate_bps=60)

    def apply(self, ids):
        quote = settlements.preview_request(self.promoter.id, SettlementPreviewInput(order_ids=ids))
        return settlements.apply_request(self.promoter.id, SettlementApplyInput(order_ids=ids, quote_digest=quote['quote_digest'], request_key='application-' + str(time.time_ns()), confirmed=True))

    def test_scoped_search_summary_status_and_export(self):
        first = self.paid()
        second = self.another('holding-order')
        with db() as conn:
            conn.execute("UPDATE referral_rewards SET policy=jsonb_set(policy,'{hold_days}','14') WHERE order_id=?", (second['id'],))
        filters = SettlementFilters(q=first['id'], channel='wechat')
        self.assertEqual(settlements.listing(self.promoter.id, filters=filters)['total'], 1)
        summary = settlement_queries.summary(self.promoter.id)
        self.assertEqual(summary['available']['count'], 1)
        self.assertEqual(summary['holding']['count'], 1)
        self.assertEqual(summary['available']['amount_fen'], 395)
        self.assertEqual(settlements.listing(self.promoter.id, filters=SettlementFilters(status='holding'))['items'][0]['order_id'], second['id'])
        with self.assertRaises(HTTPException):
            settlements.listing(self.promoter.id, filters=SettlementFilters(admin_id=self.admin.id))
        admin_access.save_permissions(self.admin.id, self.promoter.id, 1, {'settlements': ['view', 'create', 'export']})
        self.sign_in(self.promoter)
        for path in ('summary', 'notices', 'admins'):
            self.assertEqual(self.client.get('/api/v1/admin/settlements/' + path).status_code, 200)
        response = self.client.get('/api/v1/admin/settlements/export.xlsx?kind=rewards&q=' + first['id'])
        self.assertEqual(response.status_code, 200, response.text[:100] if response.status_code != 200 else '')
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            text = archive.read('xl/worksheets/sheet2.xml').decode()
            self.assertIn(first['id'], text)
            self.assertNotIn(second['id'], text)

    def test_finance_http_permissions_upload_and_campaign_revision(self):
        admin_access.save_permissions(self.admin.id, self.promoter.id, 1,
                                      {'settlements': ['view', 'create', 'export'], 'referrals': ['view', 'create', 'export']})
        base = '/api/v1/admin/settlements'
        self.sign_in(self.promoter)
        response = self.client.put(base + '/payee', json={'name': '测试收款人', 'method': 'bank', 'account': '6222000012345678', 'bank': '测试银行'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['account'], '****5678')
        draft = self.draft(self.paid())
        statement = base + '/statements/' + draft['id']
        self.assertEqual(self.client.get(statement).status_code, 200)
        self.assertEqual(self.client.post(statement + '/payee/reveal').status_code, 403)
        self.assertEqual(self.client.get(base + '/bills').status_code, 403)
        self.assertEqual(self.client.put('/api/v1/admin/referrals/budget/' + str(self.promoter.id), json={'budget_fen': 1}).status_code, 403)
        campaign_path = '/api/v1/admin/referrals/campaigns'
        campaign = self.client.post(campaign_path, json={'name': '家长微信群', 'source': '微信群'})
        self.assertEqual(campaign.status_code, 200, campaign.text)
        update = {'name': '周末家长群', 'source': '微信群', 'revision': 1, 'active': False}
        path = campaign_path + '/' + campaign.json()['id']
        self.assertEqual(self.client.put(path, json=update).status_code, 200)
        self.assertEqual(self.client.put(path, json=update).status_code, 409)
        self.sign_in(self.admin)
        self.assertEqual(self.client.post(statement + '/payee/reveal').json()['account'], '6222000012345678')
        content = io.BytesIO()
        Image.new('RGB', (2, 2), 'white').save(content, 'PNG')
        upload = self.client.post(statement + '/attachments?name=evidence.png', content=content.getvalue(), headers={'Content-Type': 'application/octet-stream'})
        self.assertEqual(upload.status_code, 200, upload.text)
        self.sign_in(self.promoter)
        download = self.client.get(base + '/attachments/' + upload.json()['id'])
        self.assertEqual(download.content, content.getvalue())
        self.assertEqual(download.headers['x-content-type-options'], 'nosniff')
        other = user_store.create_user('finance-api-other', 'test-password', role='admin')
        admin_access.save_permissions(self.admin.id, other.id, 1, {'settlements': ['view'], 'referrals': ['view', 'create']})
        self.sign_in(other)
        self.assertEqual(self.client.get(statement).status_code, 404)
        self.assertEqual(self.client.get(base + '/attachments/' + upload.json()['id']).status_code, 404)
        self.assertEqual(self.client.put(path, json={**update, 'revision': 2}).status_code, 404)

    def test_cap_only_applies_to_new_order_and_is_preserved_after_rule_change(self):
        old = self.paid()
        self.rules(max_reward_fen=50, rate_bps=10000)
        new = self.another('new-capped')
        self.assertIsNone(self.reward(old)['policy']['max_reward_fen'])
        self.assertEqual(self.costs(new)['commission_fen'], 50)
        self.rules(max_reward_fen=1)
        self.assertEqual(self.costs(new)['commission_fen'], 50)
        self.assertEqual(settlement_queries.summary(self.promoter.id)['available']['amount_fen'], 445)

    def test_recover_refunded_batch_preserves_costs_and_original_and_requires_revision(self):
        first, second = self.paid(), self.another('recover-second')
        self.costs(second)
        original = self.apply([first['id'], second['id']])
        self.refund(first)
        detail = settlements.request_detail(self.promoter.id, original['id'])
        self.assertEqual(detail['request']['status'], 'invalidated')
        from app import db as database
        queries = []
        execute = database._PgConn.execute
        def record_query(conn, sql, args=()):
            queries.append(sql)
            return execute(conn, sql, args)
        with patch.object(database._PgConn, 'execute', record_query):
            preview = settlement_operations.recovery_preview(self.promoter.id, original['id'])
        self.assertLessEqual(len(queries), 10)
        self.assertFalse(any('advisory' in query for query in queries))
        self.assertEqual(preview['order_ids'], [second['id']])
        self.assertEqual(len(preview['excluded']), 1)
        body = RecoveryInput(revision=preview['revision'], reason='排除已退款订单重新核对', confirmed=True)
        recovered = settlement_operations.recover(self.promoter.id, original['id'], body)
        self.assertEqual(recovered['snapshot']['source_request_id'], original['id'])
        self.assertIsNotNone(recovered['snapshot']['items'][0]['costs'])
        self.assertEqual(settlements.request_detail(self.promoter.id, original['id'])['request']['snapshot'], original['snapshot'])
        with self.assertRaises(HTTPException):
            settlement_operations.recover(self.promoter.id, original['id'], body)
        self.assertEqual(settlements.listing(self.promoter.id, 'requests')['total'], 2)

    def test_difference_reason_required_and_audit_contains_comparison(self):
        order = self.paid()
        application = self.apply([order['id']])
        settlements.start_request(self.admin.id, application['id'], Revision(revision=application['revision']))
        self.costs(order)
        draft = settlements.create_statement(self.admin.id, StatementInput(settlement_request_id=application['id']))
        body = ReviewInput(revision=draft['revision'], personal_fees=[], tax_fen=0, evidence='账单核定金额', confirmed=True)
        with self.assertRaises(HTTPException) as error:
            settlements.approve(self.admin.id, draft['id'], body)
        self.assertEqual(error.exception.status_code, 422)
        settlements.approve(self.admin.id, draft['id'], body.model_copy(update={'difference_reason': '实际发生资料成本，按凭据扣除'}))
        detail = settlements.request_detail(self.promoter.id, application['id'])
        self.assertEqual(detail['difference']['items'][0]['before_fen'], 395)
        self.assertEqual(detail['difference']['items'][0]['after_fen'], 375)
        self.assertIn('资料成本', detail['difference']['reason'])
        self.assertTrue(any(item['kind'] == 'approve' for item in detail['timeline']))

    def test_payee_encrypted_snapshot_immutable_and_payout_time(self):
        value = PayeeInput(name='测试收款人', method='bank', account='6222000012345678', bank='测试银行')
        saved = settlement_operations.save_payee(self.promoter.id, value)
        self.assertEqual(saved['account'], '****5678')
        draft = self.draft(self.paid())
        self.assertEqual(draft['snapshot']['payee']['account'], '****5678')
        settlement_operations.save_payee(self.promoter.id, value.model_copy(update={'revision': 1, 'account': '6222111198765432'}))
        self.assertEqual(settlement_operations.reveal_payee(self.admin.id, draft['id'])['account'], value.account)
        with db() as conn:
            enc = conn.execute('SELECT value_enc FROM referral_payout_accounts WHERE statement_id=?', (draft['id'],)).fetchone()[0]
            self.assertNotIn(value.account, enc)
        approved = self.approve(draft)
        with self.assertRaises(HTTPException):
            settlements.record_payout(self.admin.id, approved['id'], ReceiptInput(revision=approved['revision'], amount_fen=approved['net_fen'], receipt='流水-001', transferred_at=int(time.time()) + 3600))
        paid = settlements.record_payout(self.admin.id, approved['id'], ReceiptInput(revision=approved['revision'], amount_fen=approved['net_fen'], receipt='流水-001', transferred_at=int(time.time())))
        self.assertEqual(paid['payout']['payee']['account'], '****5678')
        self.assertNotIn(value.account, json.dumps(settlements.listing(self.promoter.id, 'statements')))

    def test_attachment_validation_ownership_and_download(self):
        draft = self.draft(self.paid())
        image = io.BytesIO()
        Image.new('RGB', (2, 2), 'white').save(image, 'PNG')
        value = settlement_operations.upload_attachment(self.admin.id, draft['id'], '凭证.png', image.getvalue())
        self.assertEqual(settlement_operations.attachment(self.promoter.id, value['id'])['content'], image.getvalue())
        self.assertEqual(settlement_operations.upload_attachment(self.admin.id, draft['id'], '同一凭证.png', image.getvalue()), value)
        other = user_store.create_user('unrelated-finance', 'test-password', role='admin')
        with self.assertRaises(HTTPException):
            settlement_operations.attachment(other.id, value['id'])
        for content in (b'<html>bad</html>', b'x' * (2 * 1024 * 1024 + 1)):
            with self.assertRaises(HTTPException):
                settlement_operations.upload_attachment(self.admin.id, draft['id'], 'bad.png', content)

    def test_nonzero_payment_requires_captured_account_and_actual_time_zero_writeoff_is_allowed(self):
        approved = self.approve(self.draft(self.paid()))
        body = ReceiptInput(revision=approved['revision'], amount_fen=approved['net_fen'], receipt='完整留档测试', transferred_at=int(time.time()))
        with self.assertRaises(HTTPException) as error:
            settlements.record_payout(self.admin.id, approved['id'], body)
        self.assertIn('收款资料', error.exception.detail['error'])
        settlement_operations.save_payee(self.promoter.id, PayeeInput(name='测试收款人', method='bank', account='6222000012345678', bank='测试银行'))
        approved = settlement_operations.attach_payee(self.admin.id, approved['id'], approved['revision'])
        body = body.model_copy(update={'revision': approved['revision']})
        with self.assertRaises(HTTPException) as error:
            settlements.record_payout(self.admin.id, approved['id'], body.model_copy(update={'transferred_at': None}))
        self.assertIn('实际付款时间', error.exception.detail['error'])
        paid = settlements.record_payout(self.admin.id, approved['id'], body)
        self.assertEqual(settlements.record_payout(self.admin.id, approved['id'], body), paid)
        order = self.another('zero-writeoff')
        draft = self.draft(order)
        zero = self.approve(draft, personal=0, tax=draft['gross_fen'])
        with db() as conn:
            conn.execute("UPDATE referral_statements SET snapshot=snapshot-'payee' WHERE id=?", (zero['id'],))
            conn.execute('DELETE FROM referral_payout_accounts WHERE statement_id=?', (zero['id'],))
        self.assertEqual(settlements.record_payout(self.admin.id, zero['id'], ReceiptInput(revision=zero['revision'], amount_fen=0, receipt='零元税款核销'))['status'], 'paid')

    def test_actual_payout_date_filters_list_summary_export_and_excludes_legacy_unknown_times(self):
        order = self.paid()
        application = self.apply([order['id']])
        settlements.start_request(self.admin.id, application['id'], Revision(revision=application['revision']))
        self.costs(order)
        draft = settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id']], settlement_request_id=application['id']))
        paid = self.payout(self.approve(draft))
        old = int(time.time()) - 40 * 86400
        with db() as conn:
            conn.execute('UPDATE referral_statements SET created_at=? WHERE id=?', (old, paid['id']))
            conn.execute('UPDATE referral_settlement_requests SET created_at=? WHERE id=?', (old, application['id']))
        legacy = self.payout(self.approve(self.draft(self.another('legacy-payout-time'))))
        with db() as conn:
            conn.execute("UPDATE referral_statements SET payout=payout-'transferred_at' WHERE id=?", (legacy['id'],))
        today = datetime.now(settlement_queries.ZONE).strftime('%Y-%m-%d')
        filters = SettlementFilters(date_basis='paid', start_date=today, end_date=today)
        self.assertEqual(settlements.listing(self.promoter.id, 'statements', filters=filters)['items'][0]['id'], paid['id'])
        self.assertEqual(settlements.listing(self.promoter.id, 'statements', filters=filters)['total'], 1)
        self.assertEqual(settlements.listing(self.promoter.id, 'requests', filters=filters)['total'], 1)
        self.assertEqual(settlements.listing(self.promoter.id, 'rewards', filters=filters)['total'], 1)
        self.assertEqual(settlement_queries.summary(self.promoter.id, filters)['paid']['amount_fen'], paid['net_fen'])
        with zipfile.ZipFile(io.BytesIO(settlement_export.export(self.promoter.id, 'statements', filters))) as archive:
            self.assertIn('实际付款日期', archive.read('xl/worksheets/sheet4.xml').decode())
            self.assertNotIn(legacy['id'], archive.read('xl/worksheets/sheet1.xml').decode())

    def test_stalled_and_review_payout_deadlines_are_separate_and_filterable(self):
        self.rules(review_days=2, payout_days=2)
        order = self.paid()
        application = self.apply([order['id']])
        old = int(time.time()) - 4 * 86400
        with db() as conn:
            conn.execute('UPDATE referral_settlement_requests SET created_at=? WHERE id=?', (old, application['id']))
        summary = settlement_queries.summary(self.promoter.id)
        self.assertEqual((summary['stalled'], summary['review_overdue'], summary['payout_overdue']), (0, 1, 0))
        self.assertEqual(settlements.listing(self.promoter.id, 'requests', filters=SettlementFilters(timing='review_overdue'))['total'], 1)
        with db() as conn:
            conn.execute("UPDATE referral_settlement_requests SET snapshot=jsonb_set(snapshot,'{service_terms,review_days}','null'),updated_at=? WHERE id=?", (old, application['id']))
        summary = settlement_queries.summary(self.promoter.id)
        self.assertEqual((summary['stalled'], summary['review_overdue']), (1, 0))
        self.assertEqual(settlements.listing(self.promoter.id, 'requests', filters=SettlementFilters(timing='stalled'))['total'], 1)
        settlements.start_request(self.admin.id, application['id'], Revision(revision=application['revision']))
        self.costs(order)
        draft = settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id']], settlement_request_id=application['id']))
        approved = self.approve(draft)
        with db() as conn:
            conn.execute('UPDATE referral_statements SET approved_at=? WHERE id=?', (old, approved['id']))
        summary = settlement_queries.summary(self.promoter.id)
        self.assertEqual((summary['review_overdue'], summary['payout_overdue'], summary['overdue']), (0, 1, 1))
        self.assertEqual(settlements.listing(self.promoter.id, 'requests', filters=SettlementFilters(timing='payout_overdue'))['total'], 1)

    def test_rewards_explain_earlier_order_and_pending_refund_without_exposing_buyer(self):
        earlier = self.create_order('earlier-incomplete')
        order = self.paid()
        row = settlements.listing(self.promoter.id)['items'][0]
        self.assertEqual(row['eligibility_issue']['code'], 'earlier_order')
        self.assertEqual(row['eligibility_issue']['order_id'], earlier['id'])
        self.assertNotIn('buyer', row)
        self.assertNotIn('first_order_id', row)
        with db() as conn:
            conn.execute("UPDATE referral_rewards SET policy=jsonb_set(policy,'{hold_days}','14') WHERE order_id=?", (order['id'],))
        self.assertEqual(settlements.listing(self.promoter.id)['items'][0]['application_state'], 'exception')
        self.assertEqual(settlements.listing(self.promoter.id, filters=SettlementFilters(status='exception'))['total'], 1)
        self.assertEqual(settlement_queries.summary(self.promoter.id)['exception']['count'], 1)
        with db() as conn:
            conn.execute("UPDATE mini_orders SET status='closed' WHERE id=?", (earlier['id'],))
            conn.execute("UPDATE referral_rewards SET policy=jsonb_set(policy,'{hold_days}','0') WHERE order_id=?", (order['id'],))
        self.assertIsNone(settlements.listing(self.promoter.id)['items'][0]['eligibility_issue'])
        from app.models.commerce import RefundInput
        from app.services import mini_refunds
        mini_refunds.request(order['id'], self.viewer.id, RefundInput(reason='异常说明回归'))
        row = settlements.listing(self.promoter.id)['items'][0]
        self.assertEqual(row['eligibility_issue']['code'], 'refund')
        self.assertEqual(row['eligibility_issue']['order_id'], order['id'])

    def bill(self, order, fee='0.15', transaction=None):
        with db() as conn:
            row = conn.execute('SELECT * FROM mini_orders WHERE id=?', (order['id'],)).fetchone()
        day = datetime.fromtimestamp(row['paid_at'], settlement_queries.ZONE).strftime('%Y-%m-%d')
        content = settlement_bills.template() + f"{row['id']},{transaction or row['transaction_id']},wechat,{row['amount_fen']/100:.2f},{fee},0,{day}\r\n"
        return settlement_bills.import_bill(self.admin.id, BillImportInput(name='微信账单.csv', evidence='商户平台下载后按模板转换', content=content))

    def test_bill_import_no_mutation_duplicates_adoption_and_stale_import(self):
        order = self.paid()
        imported = self.bill(order)
        self.assertFalse(imported['duplicate'])
        self.assertTrue(self.bill(order)['duplicate'])
        self.assertIsNone(self.reward(order)['costs'])
        with db() as conn:
            check = settlement_bills.checks(conn, [order['id']])[0]
        self.assertTrue(check['can_adopt'])
        body = CostsInput(revision=1, bill_row_id=check['bill_row_id'], channel_fee_fen=15, shared_fees=[], evidence='采用已匹配的实际账单金额', confirmed=True)
        cost = settlements.confirm_costs(self.admin.id, order['id'], body)
        self.assertEqual(cost['costs']['channel_fee_fen'], 15)
        self.assertNotIn('channel_rate_bps', cost['costs'])
        self.bill(order, fee='0.16')
        with self.assertRaises(HTTPException):
            settlements.confirm_costs(self.admin.id, order['id'], body.model_copy(update={'revision': cost['revision']}))
        self.bill(order, transaction='wrong-transaction')
        with db() as conn:
            check = settlement_bills.checks(conn, [order['id']])[0]
        self.assertFalse(check['can_adopt'])
        self.assertIn('交易号不一致', check['differences'])

    def test_latest_bill_conflicts_block_approval_and_payout_without_rewriting_snapshot(self):
        settlement_operations.save_payee(self.promoter.id, PayeeInput(name='测试收款人', method='bank', account='6222000012345678', bank='测试银行'))
        order = self.paid()
        self.bill(order)
        with db() as conn:
            check = settlement_bills.checks(conn, [order['id']])[0]
        settlements.confirm_costs(self.admin.id, order['id'], CostsInput(revision=self.reward(order)['revision'], bill_row_id=check['bill_row_id'], channel_fee_fen=15, shared_fees=[], evidence='实际渠道账单', confirmed=True))
        draft = settlements.create_statement(self.admin.id, StatementInput(order_ids=[order['id']]))
        self.bill(order, fee='0.16')
        with self.assertRaises(HTTPException) as error:
            self.approve(draft, 0, 0)
        self.assertIn('手续费', error.exception.detail['error'])
        self.bill(order, fee='0.15', transaction='bad-transaction')
        differences = settlement_operations.statement_detail(self.admin.id, draft['id'])['bill_differences']
        self.assertIn('交易号不一致', differences[0]['reasons'])
        self.bill(order, fee='0.15', transaction='new-bill-transaction')
        with db() as conn:
            conn.execute('UPDATE mini_orders SET transaction_id=? WHERE id=?', ('new-bill-transaction', order['id']))
        approved = self.approve(draft, 0, 0)
        original = approved['snapshot']
        self.bill(order, fee='0.17', transaction='new-bill-transaction')
        with self.assertRaises(HTTPException):
            self.payout(approved)
        self.assertEqual(settlement_operations.statement_detail(self.admin.id, approved['id'])['statement']['snapshot'], original)

    def test_latest_completed_wechat_reconciliation_blocks_review_and_payment(self):
        settlement_operations.save_payee(self.promoter.id, PayeeInput(name='测试收款人', method='bank', account='6222000012345678', bank='测试银行'))
        stamp = int(time.time()) - 3 * 86400
        with patch('app.services.mini_orders.time.time', return_value=stamp):
            order = self.paid(at=stamp)
        draft = self.draft(order)
        with db() as conn:
            paid_at = conn.execute('SELECT paid_at FROM mini_orders WHERE id=?', (order['id'],)).fetchone()[0]
        day = datetime.fromtimestamp(paid_at, settlement_queries.ZONE).strftime('%Y-%m-%d')
        refund_day = datetime.now(settlement_queries.ZONE).strftime('%Y-%m-%d')
        now = int(time.time())
        reason = '微信交易号不一致'
        def reconcile(index, values, status='complete', bill_day=day):
            with db() as conn:
                conn.execute('INSERT INTO mini_reconciliations(id,bill_date,status,differences_json,admin_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                             ('reconciliation-' + str(index), bill_day, status, json.dumps(values), self.admin.id, now + index, now + index))
        reconcile(1, [{'order_id': order['id'], 'reason': reason}])
        self.assertIn(reason, settlement_operations.statement_detail(self.admin.id, draft['id'])['bill_differences'][0]['reasons'])
        with self.assertRaises(HTTPException) as error:
            self.approve(draft, 0, 0)
        self.assertIn(reason, error.exception.detail['error'])
        reconcile(2, [{'order_id': 'unrelated-order', 'reason': '无关差异'}])
        reconcile(3, [{'order_id': order['id'], 'reason': reason}], status='running')
        approved = self.approve(draft, 0, 0)
        reconcile(4, [{'order_id': order['id'], 'reason': '微信已退款，本地待同步'}], bill_day=refund_day)
        with self.assertRaises(HTTPException):
            self.payout(approved)
        self.assertEqual(settlement_operations.statement_detail(self.admin.id, approved['id'])['statement']['snapshot'], approved['snapshot'])
        reconcile(5, [], bill_day=refund_day)
        self.assertEqual(self.payout(approved)['status'], 'paid')

    def test_unknown_reward_and_known_zero_counts_match_campaign_budget_and_summary(self):
        campaign = referral_operations.save_campaign(self.promoter.id, CampaignInput(name='未知费用活动', source='微信群'))
        with db() as conn:
            referrals.initialize_user(conn, self.viewer.id, campaign['code'])
        order = self.paid()
        with db() as conn:
            conn.execute("UPDATE referral_rewards SET policy=policy-'channel_rate_bps' WHERE order_id=?", (order['id'],))
        def counts():
            summary = referral_operations.analytics(self.promoter.id)
            item = referral_operations.campaigns(self.promoter.id)['items'][0]
            budget = referral_operations.budget(self.promoter.id, self.promoter.id)
            return [(summary['reward_known'], summary['reward_unknown'], summary['reward_reference_fen']),
                    (item['reward_known'], item['unknown'], item['reward_fen']),
                    (budget['reward_known'], budget['unknown'], budget['used_fen'])]
        self.assertEqual(counts(), [(0, 1, 0)] * 3)
        self.costs(order, fee=1990, shared=0)
        self.assertEqual(counts(), [(1, 0, 0)] * 3)

    def test_wechat_reconciliation_keeps_difference_after_the_first_5000_and_blocks_approval(self):
        stamp = int(time.time()) - 86400
        with patch('app.services.mini_orders.time.time', return_value=stamp):
            order = self.paid(at=stamp)
        draft = self.draft(order)
        day = datetime.fromtimestamp(stamp, settlement_queries.ZONE).strftime('%Y-%m-%d')
        header = '微信订单号,商户订单号,交易状态,订单金额\n'
        records = [f'`remote-{index},`missing-{index},`SUCCESS,`19.90\n' for index in range(5000)]
        records.append(f"`wrong-final-transaction,`{order['id']},`SUCCESS,`19.90\n")
        contents = header + ''.join(records) + '总交易单数\n`5001\n'
        empty = header + '总交易单数\n`0\n'
        with patch.object(payment_bills.WeChatPay, 'bill', side_effect=lambda _day, kind: contents if kind == 'SUCCESS' else empty):
            result = payment_bills.reconcile(self.admin.id, day)
        self.assertEqual(result['summary']['differences'], 5001)
        self.assertEqual(len(result['differences']), 5001)
        self.assertEqual(result['differences'][-1]['order_id'], order['id'])
        self.assertTrue(result['differences_complete'])
        self.assertTrue(payment_bills.listing()['items'][0]['differences_complete'])
        detail = settlement_operations.statement_detail(self.admin.id, draft['id'])
        self.assertIn('微信交易号不一致', detail['bill_differences'][0]['reasons'])
        with self.assertRaises(HTTPException):
            self.approve(draft, 0, 0)

    def test_legacy_incomplete_reconciliation_blocks_omitted_order_until_full_recheck(self):
        stamp = int(time.time()) - 2 * 86400
        with patch('app.services.mini_orders.time.time', return_value=stamp):
            order = self.paid(at=stamp)
        settlement_operations.save_payee(self.promoter.id, PayeeInput(name='测试收款人', method='bank', account='6222000012345678', bank='测试银行'))
        draft = self.draft(order)
        day = datetime.fromtimestamp(stamp, settlement_queries.ZONE).strftime('%Y-%m-%d')
        today = datetime.now(settlement_queries.ZONE).strftime('%Y-%m-%d')
        truncated = [{'order_id': f'omitted-source-{index}', 'reason': '无关差异'} for index in range(5000)]
        now = int(time.time())
        def save(identifier, bill_day, differences, total, offset):
            with db() as conn:
                conn.execute('INSERT INTO mini_reconciliations(id,bill_date,status,summary_json,differences_json,admin_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                             (identifier, bill_day, 'complete', json.dumps({'differences': total}), json.dumps(differences), self.admin.id, now + offset, now + offset))
        save('legacy-truncated', day, truncated, 5001, 0)
        self.assertFalse(payment_bills.get('legacy-truncated')['differences_complete'])
        self.assertFalse(payment_bills.listing()['items'][0]['differences_complete'])
        detail = settlement_operations.statement_detail(self.admin.id, draft['id'])
        self.assertIn('未完整留存', detail['bill_differences'][0]['reasons'][0])
        with self.assertRaises(HTTPException):
            self.approve(draft, 0, 0)
        save('full-recheck', day, [], 0, 1)
        self.assertEqual(settlement_operations.statement_detail(self.admin.id, draft['id'])['bill_differences'], [])
        approved = self.approve(draft, 0, 0)
        save('later-refund-truncated', today, truncated, 5001, 2)
        with self.assertRaises(HTTPException):
            self.payout(approved)
        self.assertEqual(settlement_operations.statement_detail(self.admin.id, approved['id'])['statement']['snapshot'], approved['snapshot'])

    def test_notices_scope_and_mark_read(self):
        application = self.apply([self.paid()['id']])
        other = user_store.create_user('no-notices', 'test-password', role='admin')
        self.assertEqual(settlement_operations.notices(other.id)['unread'], 0)
        notices = settlement_operations.notices(self.promoter.id)
        self.assertEqual(notices['items'][0]['target'], application['id'])
        settlement_operations.read_notices(self.promoter.id, notices['items'][0]['id'])
        self.assertEqual(settlement_operations.notices(self.promoter.id)['unread'], 0)
        with self.assertRaises(HTTPException):
            settlement_operations.read_notices(other.id, notices['items'][0]['id'])

    def test_campaign_attribution_inheritance_disable_and_budget(self):
        campaign = referral_operations.save_campaign(self.promoter.id, CampaignInput(name='家长微信群', source='微信群', budget_fen=0))
        with db() as conn:
            referrals.initialize_user(conn, self.viewer.id, campaign['code'])
            viewer = conn.execute('SELECT referral_code,referral FROM mini_users WHERE id=?', (self.viewer.id,)).fetchone()
            self.assertEqual(viewer['referral']['campaign_id'], campaign['id'])
            inherited = referrals.attribution(conn, viewer['referral_code'])
            self.assertEqual(inherited['campaign_id'], campaign['id'])
        self.paid()
        result = referral_operations.campaigns(self.promoter.id)['items'][0]
        self.assertEqual((result['registrations'], result['paying_users']), (1, 1))
        self.assertTrue(result['budget_reached'])
        referral_operations.save_campaign(self.promoter.id, CampaignUpdate(name='家长微信群', source='微信群', budget_fen=0, revision=1, active=False), campaign['id'])
        with db() as conn:
            self.assertEqual(referrals.attribution(conn, campaign['code'])['source'], 'natural')
            self.assertEqual(referrals.attribution(conn, viewer['referral_code'])['campaign_id'], campaign['id'])
        value = referral_operations.budget(self.admin.id, self.promoter.id, BudgetInput(budget_fen=100))
        self.assertTrue(value['reached'])
        with self.assertRaises(HTTPException):
            referral_operations.budget(self.promoter.id, self.promoter.id, BudgetInput(revision=1, budget_fen=900))

    def test_actual_payment_date_statistics_and_renewal_split(self):
        order = self.paid()
        renewal = self.create_order('renewal-stats')
        from app.services import mini_orders
        mini_orders.confirm_payment(self.paid_value(renewal))
        with db() as conn:
            conn.execute('UPDATE mini_orders SET created_at=created_at-86400*60 WHERE id=?', (order['id'],))
        today = datetime.now(settlement_queries.ZONE).strftime('%Y-%m-%d')
        actual = referral_operations.analytics(self.promoter.id, start_date=today, end_date=today, date_basis='paid')
        created = referral_operations.analytics(self.promoter.id, start_date=today, end_date=today, date_basis='created')
        self.assertEqual(actual['first_paid_fen'], 1990)
        self.assertEqual(actual['renewal_paid_fen'], 1990)
        self.assertEqual(created['first_paid_fen'], 0)
        self.assertEqual(actual['paid_fen'], 3980)

    def test_excel_has_numeric_sheets_filter_scope_and_no_formula_execution(self):
        paid = self.payout(self.approve(self.draft(self.paid())))
        exported = settlement_export.export(self.promoter.id, 'statements', SettlementFilters())
        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            self.assertEqual(len([name for name in archive.namelist() if name.startswith('xl/worksheets/')]), 4)
            text = archive.read('xl/worksheets/sheet1.xml').decode()
            self.assertIn(paid['id'], text)
            self.assertIn('<v>3.45</v>', text)
            for name in archive.namelist():
                ElementTree.fromstring(archive.read(name))
        with zipfile.ZipFile(io.BytesIO(settlement_export.workbook({'财务': [['姓名'], ['=HYPERLINK("bad")']]}))) as archive:
            text = archive.read('xl/worksheets/sheet1.xml').decode()
            self.assertNotIn('<f>', text)
            self.assertIn('t="inlineStr"', text)
