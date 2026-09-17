"""Database startup must not race when multiple PostgreSQL workers boot."""

import unittest
from unittest.mock import patch

from app import db as database


class DatabaseStartupContracts(unittest.TestCase):
    def test_postgres_schema_initialization_holds_the_shared_lock(self):
        with patch.object(database, "db") as connection, \
                patch.object(database, "_migrate_pg"), \
                patch.object(database, "_init_reliability_schema"), \
                patch("app.library_schema.init_library_schema"):
            database.init_db()
        connection.assert_called_once_with(serialized=tuple(database._LOCK_IDS))

    def test_missing_database_url_fails_closed(self):
        from app import config

        with patch.object(config.get_settings(), "database_url", ""):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                database._database_url()
