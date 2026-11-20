"""Opt-in S03 matrix on EMPTY guarded MySQL, historical FK-free schema."""
import os
import unittest
from sqlalchemy import create_engine, text
from sqlalchemy.schema import CreateTable
from app.db import Base
from app.mysql_test_guard import verify_test_database
from tests import (test_review_order_authorization, test_review_payer_authorization,
                   test_review_customer_authorization, test_review_inventory_authorization,
                   test_review_printer_authorization, test_review_afterprint_authorization,
                   test_review_compile_authorization, test_review_dictionary_authorization,
                   test_review_work_authorization, test_review_s03_matrix)


class MySQLFixture:
    mysql = True

    def setUp(self):
        url = os.environ['MYSQL_ADMIN_TEST_URL']
        verify_test_database(url, os.getenv('DATABASE_URL'))
        storage = os.getenv('S03_MYSQL_ENGINE', 'InnoDB')
        if storage not in {'InnoDB', 'MyISAM'}:
            raise RuntimeError('Unsupported test storage engine')
        engine = create_engine(url)
        try:
            with engine.begin() as connection:
                tables = list(connection.scalars(text('SHOW TABLES')))
                if tables:
                    raise RuntimeError('S03 MySQL requires an empty disposable database')
                for table in Base.metadata.sorted_tables:
                    ddl = str(CreateTable(table, include_foreign_key_constraints=[]).compile(engine))
                    connection.execute(text(ddl + ' ENGINE=' + storage + ' DEFAULT CHARSET=utf8mb3'))
        finally:
            engine.dispose()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        engine = create_engine(os.environ['MYSQL_ADMIN_TEST_URL'])
        try:
            Base.metadata.drop_all(engine)
        finally:
            engine.dispose()


for module in (test_review_order_authorization, test_review_payer_authorization,
               test_review_customer_authorization, test_review_inventory_authorization,
               test_review_printer_authorization, test_review_afterprint_authorization,
               test_review_compile_authorization, test_review_dictionary_authorization,
               test_review_work_authorization, test_review_s03_matrix):
    for name, cls in vars(module).items():
        if isinstance(cls, type) and cls.__module__ == module.__name__ and issubclass(cls, unittest.TestCase):
            generated = type('MySQL' + name, (MySQLFixture, cls), {'__module__': __name__})
            globals()[generated.__name__] = unittest.skipUnless(
                os.getenv('S03_MYSQL_ENABLED') == '1', 'Requires isolated S03 MySQL')(generated)
del module, name, cls, generated