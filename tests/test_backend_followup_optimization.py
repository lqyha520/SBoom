"""结算快照、公共缓存与会话节流的回归；只使用一次性测试数据库。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock, patch

import pytest
import test_backend_catalog as catalog_fixtures
import test_backend_settlements as settlement_fixtures

from app import db as database
from app.config import get_settings
from app.models.settlements import PayeeInput, SettlementFilters
from app.models.site import CategoryInput
from app.public_cache import cached_public, invalidate
from app.services import (
    finance_ledger,
    public_catalog,
    referrals,
    settlement_operations,
    settlement_queries,
    settlements,
    site_content,
    user_store,
    workspace_sessions,
)


@pytest.fixture
def catalog_case():
    case = catalog_fixtures.PublicCatalogContracts('runTest')
    try:
        case.setUp()
        yield case
    finally:
        case.doCleanups()


def test_summary_keeps_one_snapshot_when_payout_commits_between_totals():
    case = settlement_fixtures.SettlementContracts('runTest')
    try:
        case.setUp()
        statement = case.approve(case.draft(case.paid()))
        execute, changed = database._PgConn.execute, False

        def interleave(conn, sql, params=()):
            nonlocal changed
            result = execute(conn, sql, params)
            if not changed and 'FROM referral_statements r WHERE' in sql:
                changed = True
                case.payout(statement)
            return result

        with patch.object(database._PgConn, 'execute', interleave):
            observed = settlement_queries.summary(case.admin.id)
        assert changed
        assert observed['approved'] == {'count': 1, 'amount_fen': statement['net_fen']}
        assert observed['paid'] == {'count': 0, 'amount_fen': 0}
        current = settlement_queries.summary(case.admin.id)
        assert current['approved']['count'] == 0
        assert current['paid'] == {'count': 1, 'amount_fen': statement['net_fen']}
    finally:
        case.doCleanups()


def test_summary_aggregates_once_per_domain_and_matches_filtered_lists():
    case = settlement_fixtures.SettlementContracts('runTest')
    try:
        case.setUp()
        case.rules(channel_rate_bps=100)
        available = case.paid('summary-available')
        paid = case.approve(case.draft(case.another('summary-paid')))
        case.payout(paid)
        approved = case.approve(case.draft(case.another('summary-approved')))
        case.rules(hold_days=7, channel_rate_bps=100)
        case.another('summary-holding')
        case.rules()
        # 一个推广人不能同时有待处理申请和未完成结算单，使用另一位推广人覆盖申请汇总。
        case.promoter = user_store.create_user('summary-request-admin', 'test-password', role='admin')
        case.code = referrals.admin_code(case.admin.id, case.promoter.id)['code']
        settlement_operations.save_payee(case.promoter.id, PayeeInput(
            name='申请收款人', method='bank', account='6222000012345678', bank='测试银行'))
        pending = case.another('summary-pending')
        settlements.apply_request(case.promoter.id, case.application_body([pending]))
        execute, queries = database._PgConn.execute, []

        def counted(conn, sql, params=()):
            queries.append(sql)
            return execute(conn, sql, params)

        with patch.object(database._PgConn, 'execute', counted):
            result = settlement_queries.summary(case.admin.id)
        assert len(queries) <= 6  # 权限核验、事务设置及三次聚合，避免每张卡片重复读取。
        assert result['approved']['amount_fen'] == approved['net_fen']
        assert result['paid']['amount_fen'] == paid['net_fen']
        assert result['pending'] == {'count': 1, 'amount_fen': 0, 'unknown': 1}
        assert result['available']['count'] == result['holding']['count'] == 1
        for filters in (SettlementFilters(), SettlementFilters(admin_id=case.promoter.id),
                        SettlementFilters(q=available['id']), SettlementFilters(channel='wechat'),
                        SettlementFilters(channel='virtual_ios'), SettlementFilters(date_basis='paid'),
                        SettlementFilters(start_date='2000-01-01', end_date='2000-01-02')):
            result = settlement_queries.summary(case.admin.id, filters)
            for kind, states in (('rewards', ('available', 'holding', 'exception')),
                                 ('requests', ('pending', 'reviewing')), ('statements', ('approved', 'paid'))):
                for state in states:
                    listing = settlements.listing(case.admin.id, kind, filters=filters.model_copy(update={'status': state}))
                    assert result[state]['count'] == listing['total'], (filters, state)
        with pytest.raises(Exception) as denied:
            settlement_queries.summary(case.promoter.id, SettlementFilters(admin_id=case.admin.id))
        assert denied.value.status_code == 403
    finally:
        case.doCleanups()


def test_unrelated_transactions_keep_cache_and_public_writes_invalidate_after_commit(catalog_case):
    invalidate()
    loader = Mock(return_value={'public': True})

    @cached_public
    def metadata():
        return loader()

    metadata()
    finance_ledger.create(catalog_case.admin.id, {
        'identifier': 'cache-regression', 'entry_date': '2026-11-14',
        'direction': 'expense', 'category': '测试', 'amount_fen': 100,
    })
    workspace_sessions.create(catalog_case.admin.id)
    for scope in ('accounts', 'generation', 'xhs_research', 'content', ('content', 'accounts')):
        with database.db(serialized=scope) as conn:
            conn.execute('SELECT 1')
        metadata()
    assert loader.call_count == 1
    with pytest.raises(RuntimeError), database.db(invalidate_public=True) as conn:
        conn.execute("UPDATE site_categories SET name='回滚分类'")
        raise RuntimeError('回滚')
    metadata()
    assert loader.call_count == 1
    with database.db(serialized='content', invalidate_public=True) as conn:
        conn.execute('SELECT 1')
        metadata()
        assert loader.call_count == 1
    metadata()
    assert loader.call_count == 2


def test_home_and_catalog_refresh_immediately_after_public_edits(catalog_case):
    previous = site_content.home_payload()
    category = site_content.create_category(CategoryInput(name='缓存新分类'))
    assert category['id'] not in {item['id'] for item in previous['categories']}
    assert category['id'] in {item['id'] for item in site_content.home_payload()['categories']}
    assert public_catalog.public_summary()['papers'] == 0
    publication = catalog_case.publish()
    assert public_catalog.public_summary()['papers'] == 1
    catalog_case.update(publication, status='withdrawn').raise_for_status()
    assert public_catalog.public_summary()['papers'] == 0


def session_state(identifier):
    with database.db() as conn:
        return dict(conn.execute('SELECT last_seen_at, xmin::text AS version FROM workspace_sessions WHERE id=?',
                                 (identifier,)).fetchone())


def test_session_checks_do_not_write_within_minute_or_cache_revocation(catalog_case):
    now = 2_000_000_000
    with patch('app.services.workspace_sessions.time.time', return_value=now):
        identifier = workspace_sessions.create(catalog_case.admin.id)
    original = session_state(identifier)
    for seconds in (0, 15, 30, 59):
        with patch('app.services.workspace_sessions.time.time', return_value=now + seconds):
            assert workspace_sessions.valid(identifier, catalog_case.admin.id)
        assert session_state(identifier) == original
    with patch('app.services.workspace_sessions.time.time', return_value=now + 60):
        assert workspace_sessions.valid(identifier, catalog_case.admin.id)
        assert session_state(identifier)['last_seen_at'] == now + 60
        assert not workspace_sessions.valid(identifier, catalog_case.author.id)
        workspace_sessions.revoke(identifier, catalog_case.admin.id)
        assert not workspace_sessions.valid(identifier, catalog_case.admin.id)


@pytest.mark.parametrize('column', ['last_seen_at', 'expires_at'])
def test_session_touch_never_revives_expired_session(catalog_case, column):
    now = 2_000_000_000
    with patch('app.services.workspace_sessions.time.time', return_value=now):
        identifier = workspace_sessions.create(catalog_case.admin.id)
        with database.db() as conn:
            value = now - get_settings().session_idle_seconds if column == 'last_seen_at' else now
            conn.execute(f'UPDATE workspace_sessions SET {column}=? WHERE id=?', (value, identifier))
        original = session_state(identifier)
        assert not workspace_sessions.valid(identifier, catalog_case.admin.id)
        assert session_state(identifier) == original


def test_concurrent_session_touches_write_once_and_all_requests_remain_valid(catalog_case):
    now = 2_000_000_000
    with patch('app.services.workspace_sessions.time.time', return_value=now):
        identifier = workspace_sessions.create(catalog_case.admin.id)
    barrier, writes = Barrier(4), []
    execute = database._PgConn.execute

    def interleave(conn, sql, params=()):
        result = execute(conn, sql, params)
        if sql.startswith('SELECT last_seen_at FROM workspace_sessions'):
            barrier.wait(timeout=5)
        if sql.startswith('UPDATE workspace_sessions SET last_seen_at'):
            writes.append(result.rowcount)
        return result

    with patch('app.services.workspace_sessions.time.time', return_value=now + 60), \
            patch.object(database._PgConn, 'execute', interleave), ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: workspace_sessions.valid(identifier, catalog_case.admin.id), range(4)))
    assert all(results)
    assert sum(writes) == 1
    assert session_state(identifier)['last_seen_at'] == now + 60


def test_revocation_between_session_read_and_touch_is_rechecked(catalog_case):
    now = 2_000_000_000
    with patch('app.services.workspace_sessions.time.time', return_value=now):
        identifier = workspace_sessions.create(catalog_case.admin.id)
    execute = database._PgConn.execute

    def revoke_after_read(conn, sql, params=()):
        result = execute(conn, sql, params)
        if sql.startswith('SELECT last_seen_at FROM workspace_sessions'):
            workspace_sessions.revoke(identifier, catalog_case.admin.id)
        return result

    with patch('app.services.workspace_sessions.time.time', return_value=now + 60), \
            patch.object(database._PgConn, 'execute', revoke_after_read):
        assert not workspace_sessions.valid(identifier, catalog_case.admin.id)
