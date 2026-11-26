"""S04 real-session regressions against empty guarded historical MySQL tables."""
import os
import unittest

from tests import test_review_employee_authorization as employee_tests
from tests import test_review_s03_mysql as mysql_tests


@unittest.skipUnless(os.getenv('S04_MYSQL_ENABLED') == '1', 'Requires isolated S04 MySQL')
class MySQLDelegationReviewTests(mysql_tests.MySQLFixture, employee_tests.EmployeeAuthorizationReviewTests):
    pass