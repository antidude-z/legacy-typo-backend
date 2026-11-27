"""Final S12 contracts on isolated historical MySQL storage engines."""
import os
import unittest
from unittest.mock import patch
from tests import test_review_s03_mysql as fixture
from tests import test_review_s12_final as final
from tests import test_review_s12_abuse_mysql as abuse


@unittest.skipUnless(os.getenv('S12F_MYSQL_ENABLED') == '1', 'Requires isolated final S12 MySQL')
class MySQLAuditTests(fixture.MySQLFixture, final.AuditTests):
    pass


@unittest.skipUnless(os.getenv('S12F_MYSQL_ENABLED') == '1', 'Requires isolated final S12 MySQL')
class MySQLGenericTests(abuse.MySQLAbuseTests):
    __unittest_skip__ = False
    test_existing_new_registration_same_response_and_no_session = final.GenericResponseTests.test_existing_new_registration_same_response_and_no_session
    test_delivery_failure_and_unknown_account_have_identical_response = final.GenericResponseTests.test_delivery_failure_and_unknown_account_have_identical_response