"""Run against a disposable local database named lc_verify*, never the configured app DB.

LC_TEST_PG_DSN=postgresql://.../lc_verify python -m unittest discover -s tests -p postgres_experience.py
Every case owns a random schema and removes only that schema on completion.
"""

import os
import unittest
import uuid
from unittest.mock import patch
from urllib.parse import parse_qsl, urlencode, urlsplit

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

import test_backend_experience as contracts
import test_backend_growth as growth
import test_backend_guest_profile as guest_profile
from app import db as database
from app.config import get_settings
from app.services import mini_auth, user_store


class PostgreSQLSetup:
    def setUp(self):
        super().setUp()
        dsn = os.environ['LC_TEST_PG_DSN']
        if not dsn.startswith(('postgresql://', 'postgres://')):
            raise RuntimeError('LC_TEST_PG_DSN must be a PostgreSQL URI')
        config = conninfo_to_dict(dsn)
        if config.get('host') not in ('127.0.0.1', 'localhost') or not config.get('dbname', '').startswith('lc_verify'):
            raise RuntimeError('Only local disposable lc_verify* databases are accepted')
        schema = 'lc_case_' + uuid.uuid4().hex
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))

        def cleanup():
            with psycopg.connect(dsn, autocommit=True) as conn:
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

        self.stack.callback(cleanup)
        uri = urlsplit(dsn)
        query = dict(parse_qsl(uri.query))
        query['options'] = '-csearch_path=' + schema
        case_dsn = uri._replace(query=urlencode(query)).geturl()
        self.stack.enter_context(patch.object(get_settings(), 'database_url', case_dsn))
        self.stack.callback(database.close_pg_pool)
        self.assertTrue(database._use_pg())
        database.init_db()
        self.admin = user_store.create_user('catalog-admin', 'test-password', role='admin')
        self.author = user_store.create_user('catalog-reader', 'author-password')
        self.viewer = mini_auth.get_user(mini_auth.register('catalog-reader', 'test-password')['user']['id'])
        self.other = mini_auth.get_user(mini_auth.register('other-reader', 'test-password')['user']['id'])
        self.sign_in(self.admin)


@unittest.skipUnless(os.environ.get('LC_TEST_PG_DSN'), 'Requires a disposable PostgreSQL database')
class PostgreSQLExperienceContracts(PostgreSQLSetup, contracts.ExperienceContracts):
    pass


@unittest.skipUnless(os.environ.get('LC_TEST_PG_DSN'), 'Requires a disposable PostgreSQL database')
class PostgreSQLEngagementContracts(PostgreSQLSetup, growth.EngagementContracts):
    pass


@unittest.skipUnless(os.environ.get('LC_TEST_PG_DSN'), 'Requires a disposable PostgreSQL database')
class PostgreSQLCommerceContracts(PostgreSQLSetup, growth.CommerceContracts):
    pass


@unittest.skipUnless(os.environ.get('LC_TEST_PG_DSN'), 'Requires a disposable PostgreSQL database')
class PostgreSQLGuestProfileContracts(PostgreSQLSetup, guest_profile.GuestProfileContracts):
    pass
