import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.backup import backup, restore


class BackupTests(unittest.TestCase):
    def make_database(self, path, value="before"):
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE values_table (value TEXT NOT NULL)")
        connection.execute("INSERT INTO values_table VALUES (?)", (value,))
        connection.commit(); connection.close()

    def test_backup_creates_verified_copy_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "source.db", Path(directory) / "backup.db"
            self.make_database(source)
            result = backup(source, target)
            self.assertEqual(result["source_check"]["integrity"], "ok")
            connection = sqlite3.connect(target)
            self.assertEqual(connection.execute("SELECT value FROM values_table").fetchone()[0], "before")
            connection.close()
            self.assertTrue(source.exists())

    def test_restore_requires_explicit_replace_and_is_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "source.db", Path(directory) / "target.db"
            self.make_database(source, "restored")
            self.make_database(target, "original")
            with self.assertRaisesRegex(ValueError, "replace explicitly"):
                restore(source, target)
            result = restore(source, target, replace=True)
            self.assertTrue(result["replaced"])
            connection = sqlite3.connect(target)
            self.assertEqual(connection.execute("SELECT value FROM values_table").fetchone()[0], "restored")
            connection.close()

    def test_corrupt_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "broken.db", Path(directory) / "backup.db"
            source.write_bytes(b"not sqlite")
            with self.assertRaisesRegex(ValueError, "integrity check failed"):
                backup(source, target)