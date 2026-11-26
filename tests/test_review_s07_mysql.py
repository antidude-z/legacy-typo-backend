"""S07 opt-in real-session revocation on owned disposable MySQL tables."""
import os
import unittest
from tests import test_review_credential_revocation as credentials
from tests import test_review_s03_mysql as mysql


@unittest.skipUnless(os.getenv('S07_MYSQL_ENABLED') == '1', 'Requires isolated S07 MySQL')
class MySQLCredentialRevocationTests(mysql.MySQLFixture, credentials.CredentialRevocationTests):
    pass