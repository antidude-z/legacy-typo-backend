import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.mysql_recovery import backup


class MySQLRecoveryTests(unittest.TestCase):
    def test_backup_and_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            defaults = Path(directory) / 'client.cnf'
            defaults.write_text('[client]\n')
            defaults.chmod(0o600)
            target = Path(directory) / 'backup.sql'

            def execute(command, **kwargs):
                if command[0] == 'mysql':
                    return subprocess.CompletedProcess(command, 0, r'GRANT ALL PRIVILEGES ON `typography\_fullclone\_test`.* TO `qa`@`%`')
                self.assertIn('--lock-all-tables', command)
                kwargs['stdout'].write(b'CREATE TABLE sample (id int);\n')

            with patch('app.mysql_recovery.subprocess.run', side_effect=execute) as run:
                result = backup(target, defaults)
                self.assertEqual(result['bytes'], target.stat().st_size)
                self.assertEqual(len(result['backup_sha256']), 64)
                with self.assertRaises(ValueError):
                    backup(target, defaults)
                self.assertEqual(run.call_count, 2)
            self.assertFalse(target.with_name('backup.sql.partial').exists())

    def test_failed_dump_removes_partial_and_rejects_global_grants(self):
        with tempfile.TemporaryDirectory() as directory:
            defaults = Path(directory) / 'client.cnf'
            defaults.write_text('[client]\n')
            defaults.chmod(0o600)
            target = Path(directory) / 'backup.sql'
            with patch('app.mysql_recovery.subprocess.run') as run:
                run.return_value.stdout = 'GRANT ALL PRIVILEGES ON *.* TO `root`@`%`'
                with self.assertRaises(ValueError):
                    backup(target, defaults)
                self.assertEqual(run.call_count, 1)
            with patch('app.mysql_recovery.subprocess.run') as run:
                run.side_effect = [subprocess.CompletedProcess([], 0, r'GRANT ALL PRIVILEGES ON `typography\_fullclone\_test`.* TO `qa`@`%`'), subprocess.CalledProcessError(1, 'mysqldump')]
                with self.assertRaises(subprocess.CalledProcessError):
                    backup(target, defaults)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_name('backup.sql.partial').exists())