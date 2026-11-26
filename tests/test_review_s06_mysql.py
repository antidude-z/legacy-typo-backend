"""Opt-in S06 lifecycle matrix on owned disposable historical MySQL tables."""
import os
import unittest

from tests import test_review_accounting_deletion as accounting
from tests import test_review_s03_mysql as mysql


@unittest.skipUnless(os.getenv('S06_MYSQL_ENABLED') == '1', 'Requires isolated S06 MySQL')
class MySQLAccountingDeletionTests(mysql.MySQLFixture, accounting.AccountingDeletionTests):
    pass