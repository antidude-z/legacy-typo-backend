import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.mysql_clone_reset import CONFIRMATION, reset_clone


class MySQLCloneResetTests(unittest.TestCase):
    def test_confirmation_is_required_before_running_commands(self):
        with patch('app.mysql_clone_reset.subprocess.run') as run:
            with self.assertRaises(ValueError):
                reset_clone(Path('missing'), Path('missing'), 'wrong')
            run.assert_not_called()

    def test_reset_targets_only_dedicated_database(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / 'dump.sql'
            defaults = Path(directory) / 'client.cnf'
            dump.write_bytes(b'INSERT INTO sample VALUES (1);')
            defaults.write_text('[client]\n')
            defaults.chmod(0o600)
            with patch('app.mysql_clone_reset.subprocess.run') as run:
                run.return_value.stdout = r'GRANT ALL PRIVILEGES ON `typography\_fullclone\_test`.* TO `test`@`%`'
                reset_clone(dump, defaults, CONFIRMATION)
            self.assertEqual(run.call_count, 3)
            self.assertIn('`typography_fullclone_test`', run.call_args_list[1].args[0][-1])
            self.assertEqual(run.call_args_list[2].args[0][-1], 'typography_fullclone_test')

    def test_global_account_is_rejected_before_drop(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / 'dump.sql'
            defaults = Path(directory) / 'client.cnf'
            dump.write_text('SELECT 1;')
            defaults.write_text('[client]\n')
            defaults.chmod(0o600)
            with patch('app.mysql_clone_reset.subprocess.run') as run:
                run.return_value.stdout = 'GRANT ALL PRIVILEGES ON *.* TO `root`@`%`'
                with self.assertRaises(ValueError):
                    reset_clone(dump, defaults, CONFIRMATION)
                self.assertEqual(run.call_count, 1)