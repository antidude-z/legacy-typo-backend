"""S11 real-session CSRF boundary on guarded disposable MySQL."""
import os
import unittest
from tests import test_review_s11_csrf as s11
from tests import test_review_s03_mysql as mysql


@unittest.skipUnless(os.getenv('S11_MYSQL_ENABLED') == '1', 'Requires isolated S11 MySQL')
class MySQLS11CSRFTests(mysql.MySQLFixture, s11.S11RealSessionTests):
    pass