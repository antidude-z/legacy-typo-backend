import unittest

from app.mysql_test_guard import validate_test_url


class MySQLTestGuardTests(unittest.TestCase):
    def test_accepts_dedicated_target(self):
        validate_test_url('mysql+pymysql://test:secret@mysql/typography_fullclone_test',
                          'mysql+pymysql://app:secret@mysql/typography_restored')

    def test_rejects_working_or_non_mysql_target(self):
        for target in ('sqlite:///typography_fullclone_test', 'mysql+pymysql://u:p@mysql/typography_restored'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                validate_test_url(target)

    def test_rejects_same_configured_database_even_with_different_credentials(self):
        with self.assertRaises(ValueError):
            validate_test_url('mysql+pymysql://test:p@mysql/typography_fullclone_test',
                              'mysql+pymysql://app:q@mysql:3306/typography_fullclone_test')