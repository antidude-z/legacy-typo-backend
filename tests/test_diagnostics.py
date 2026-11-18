import unittest

from sqlalchemy import create_engine, text

from app.diagnostics import database_diagnostics
from app.schema import apply_migrations


class DiagnosticsTests(unittest.TestCase):
    def test_sqlite_diagnostics_reports_integrity_and_versions(self):
        engine = create_engine("sqlite://")
        apply_migrations(engine)
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM schema_versions")) if "schema_versions" in {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))} else None
            connection.execute(text("CREATE TABLE IF NOT EXISTS schema_versions (version VARCHAR(50) PRIMARY KEY, applied_at DATETIME NOT NULL)"))
            connection.execute(text("INSERT INTO schema_versions VALUES ('app-test','2026-01-01 00:00:00')"))
        result = database_diagnostics(engine, "sqlite://", "sqlite")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["sqlite"]["integrity"], "ok")
        self.assertIn("2026-11-13-01", [row["version"] for row in result["schema_migrations"]])
        self.assertEqual(result["application_versions"][0]["version"], "app-test")
        engine.dispose()

    def test_pending_migration_is_degraded(self):
        engine = create_engine("sqlite://")
        result = database_diagnostics(engine, "sqlite://", "sqlite")
        self.assertEqual(result["status"], "degraded")
        self.assertTrue(result["pending_schema_migrations"])
        engine.dispose()

    def test_mysql_diagnostics_masks_credentials(self):
        engine = create_engine("sqlite://")
        result = database_diagnostics(engine, "mysql+pymysql://user:secret@mysql/typography", "mysql")
        self.assertNotIn("secret", result["database_url"])
        engine.dispose()