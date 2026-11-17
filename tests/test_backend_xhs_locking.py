"""小红书按账号准入，与业务域迁移互斥；等待时不占用数据库连接。"""

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

from app.db import db
from app.db_admission import DatabaseBusy, admission


class XhsLockAdmissionContracts(unittest.TestCase):
    def test_same_account_waits_before_borrowing_a_connection(self):
        entered, release = threading.Event(), threading.Event()

        def hold():
            with admission((), None, 1, ('xhs_research', 'account-one')):
                entered.set()
                release.wait(3)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(hold)
            self.assertTrue(entered.wait(1))
            try:
                pool = MagicMock()
                with patch('app.db._get_pg_pool', return_value=pool), patch('app.db.get_settings') as settings:
                    settings.return_value.db_lock_timeout_ms = 20
                    with self.assertRaises(DatabaseBusy), db(lock_key=('xhs_research', 'account-one')):
                        self.fail('进入正在写入的账号')
                    pool.connection.assert_not_called()
            finally:
                release.set()
            future.result(timeout=3)

    def test_different_accounts_can_enter_but_exclusive_domain_waits(self):
        with admission((), None, 1, ('xhs_research', 'account-one')):
            with admission((), None, 0.1, ('xhs_research', 'account-two')):
                pass
            with self.assertRaises(DatabaseBusy), admission(('xhs_research',), None, 0.02):
                self.fail('迁移不能进入正在使用的业务域')

    def test_unknown_domain_fails_instead_of_silently_skipping_admission(self):
        with self.assertRaises(ValueError), admission(('unknown',), None, 0.1):
            self.fail('未知域不能跳过准入')
