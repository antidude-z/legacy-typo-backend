import unittest

from app.mysql_test_guard import validate_test_url, validate_grants


class MySQLTestGuardTests(unittest.TestCase):
    def test_restricted_grants(self):
        validate_grants(['GRANT USAGE ON *.* TO `qa`@`%`',
                         r'GRANT ALL PRIVILEGES ON `typography\_fullclone\_test`.* TO `qa`@`%`'],
                        'typography_fullclone_test')

    def test_rejects_global_cross_database_roles_and_grant_option(self):
        for grant in ('GRANT ALL PRIVILEGES ON *.* TO `qa`@`%`',
                      'GRANT ALL PRIVILEGES ON `typography_fullclone_test`.* TO `qa`@`%`',
                      'GRANT SELECT ON `typography_restored`.* TO `qa`@`%`',
                      'GRANT `admin`@`%` TO `qa`@`%`',
                      'GRANT ALL PRIVILEGES ON `typography_fullclone_test`.* TO `qa`@`%` WITH GRANT OPTION'):
            with self.subTest(grant=grant), self.assertRaises(ValueError):
                validate_grants([grant], 'typography_fullclone_test')

    def test_connection_preflight_checks_actual_database_and_grants(self):
        from unittest.mock import patch, MagicMock
        from app.mysql_test_guard import verify_test_database
        engine = MagicMock()
        connection = engine.connect.return_value.__enter__.return_value
        connection.scalar.side_effect = ['typography_fullclone_test', '8.0.46']
        connection.scalars.return_value = [
            r'GRANT ALL PRIVILEGES ON `typography\_fullclone\_test`.* TO `qa`@`%`']
        with patch('app.mysql_test_guard.create_engine', return_value=engine):
            self.assertEqual(verify_test_database('mysql+pymysql://qa:p@mysql/typography_fullclone_test')['server_version'], '8.0.46')
        engine.dispose.assert_called_once()

    def test_mismatched_server_database_is_rejected(self):
        from unittest.mock import patch, MagicMock
        from app.mysql_test_guard import verify_test_database
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value.scalar.return_value = 'typography_restored'
        with patch('app.mysql_test_guard.create_engine', return_value=engine), self.assertRaises(ValueError):
            verify_test_database('mysql+pymysql://qa:p@mysql/typography_fullclone_test')
        engine.dispose.assert_called_once()
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