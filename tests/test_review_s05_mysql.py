"""Opt-in S05 real-session matrix on disposable historical MySQL tables."""
import os
import unittest

from tests import test_review_report_authorization as reports
from tests import test_review_s03_mysql as mysql


@unittest.skipUnless(os.getenv('S05_MYSQL_ENABLED') == '1', 'Requires isolated S05 MySQL')
class MySQLReportAuthorizationReviewTests(mysql.MySQLFixture, reports.ReportAuthorizationReviewTests):
    pass