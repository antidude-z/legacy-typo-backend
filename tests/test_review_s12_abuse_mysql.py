"""S12 auth side effects on owned historical FK-free MySQL tables."""
import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.schema import CreateTable
from sqlalchemy import text
from app.db import Base
from app.mysql_test_guard import verify_test_database
from tests import test_review_s12_abuse as abuse


@unittest.skipUnless(os.getenv('S12_MYSQL_ENABLED') == '1', 'Requires isolated S12 MySQL')
class MySQLAbuseTests(abuse.AbuseEndpointTests):
    def setUp(self):
        url = os.environ['MYSQL_ADMIN_TEST_URL']
        verify_test_database(url, os.getenv('DATABASE_URL'))
        engine = create_engine(url)
        self.addCleanup(engine.dispose)
        storage = os.environ['S03_MYSQL_ENGINE']
        if storage not in {'InnoDB', 'MyISAM'}:
            raise RuntimeError('Unsupported storage')
        with engine.begin() as connection:
            if list(connection.scalars(text('SHOW TABLES'))):
                raise RuntimeError('Requires empty disposable database')
            for table in Base.metadata.sorted_tables:
                ddl = str(CreateTable(table, include_foreign_key_constraints=[]).compile(engine))
                connection.execute(text(ddl + ' ENGINE=' + storage + ' DEFAULT CHARSET=utf8mb3'))
        self.addCleanup(lambda: Base.metadata.drop_all(engine))
        # Only substitute the test fixture's engine creation; endpoint DB override
        # and real bcrypt/session setup remain the same. No working URL is used.
        with patch('tests.test_authentication.create_engine', return_value=engine):
            super().setUp()