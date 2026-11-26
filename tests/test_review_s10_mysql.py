"""S10 residual grant checks on owned disposable historical MySQL schemas."""
import os
import unittest
from tests import test_review_s10_authorization as s10
from tests import test_review_s03_mysql as mysql


@unittest.skipUnless(os.getenv('S10_MYSQL_ENABLED') == '1', 'Requires isolated S10 MySQL')
class MySQLS10AuthorizationTests(mysql.MySQLFixture, s10.S10AuthorizationTests):
    pass