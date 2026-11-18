"""Read-only database/startup diagnostics."""

import argparse
import json
from pathlib import Path

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from .config import DATABASE_MODE, DATABASE_URL
from .models import SchemaVersion
from .schema import MIGRATIONS, MIGRATION_TABLE


def _safe_database_url(database_url=DATABASE_URL, database_mode=DATABASE_MODE):
    if database_mode == "sqlite":
        return database_url
    prefix, _, suffix = database_url.partition("@")
    return f"{prefix.split('://', 1)[0]}://<credentials>@{suffix}" if suffix else "<mysql-url>"


def database_diagnostics(engine, database_url=DATABASE_URL, database_mode=DATABASE_MODE):
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    result = {
        "status": "ok",
        "database_mode": database_mode,
        "database_url": _safe_database_url(database_url, database_mode),
        "schema_tables": len(tables),
        "schema_migrations": [],
        "application_versions": [],
        "sqlite": None,
    }
    with engine.connect() as connection:
        if MIGRATION_TABLE in tables:
            result["schema_migrations"] = [dict(row) for row in connection.execute(text(f"SELECT version, applied_at FROM {MIGRATION_TABLE} ORDER BY version")).mappings()]
        if "schema_versions" in tables:
            result["application_versions"] = [dict(row) for row in connection.execute(text("SELECT version, applied_at FROM schema_versions ORDER BY version")).mappings()]
        if database_mode == "sqlite":
            integrity = connection.execute(text("PRAGMA integrity_check")).scalar()
            foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar()
            result["sqlite"] = {"integrity": integrity, "foreign_keys": bool(foreign_keys), "journal_mode": connection.execute(text("PRAGMA journal_mode")).scalar()}
            if integrity != "ok":
                result["status"] = "degraded"
    expected = {version for version, _ in MIGRATIONS}
    applied = {row["version"] for row in result["schema_migrations"]}
    result["pending_schema_migrations"] = sorted(expected - applied)
    if result["pending_schema_migrations"]:
        result["status"] = "degraded"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    from .db import engine
    result = database_diagnostics(engine)
    output = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()