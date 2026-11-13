"""Dependency-free, tracked schema migrations for the local rework database."""

from datetime import UTC, datetime

from sqlalchemy import inspect, text

from .db import Base, engine

MIGRATION_TABLE = "schema_migrations"


def _add_columns(connection, additions: dict[str, dict[str, str]]) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    for table, fields in additions.items():
        if table not in tables:
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, declaration in fields.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}"))


def migration_2026_11_13_01(connection) -> None:
    """Add columns introduced while porting the deployed legacy schema."""
    _add_columns(connection, {
        "bills": {"amount": "NUMERIC(10,2) NOT NULL DEFAULT 0", "currency": "VARCHAR(3) NOT NULL DEFAULT 'RUB'", "user_id": "INTEGER", "payer_id": "INTEGER"},
        "users": {"phone": "VARCHAR(50)", "post": "VARCHAR(50)", "deleted_at": "DATETIME", "remember_token": "VARCHAR(100)"},
        "customers": {"inn": "VARCHAR(12)", "phone": "VARCHAR(200)", "address": "TEXT", "description": "TEXT", "profit": "INTEGER NOT NULL DEFAULT 0", "customer_group_id": "INTEGER"},
        "afterprints": {"production_book": "BOOLEAN NOT NULL DEFAULT 0", "production_poly": "BOOLEAN NOT NULL DEFAULT 0", "production_souvenir": "BOOLEAN NOT NULL DEFAULT 0", "production_wide": "BOOLEAN NOT NULL DEFAULT 0", "weight": "INTEGER NOT NULL DEFAULT 0"},
        "papers": {"markup": "INTEGER NOT NULL DEFAULT 10"},
        "materials": {"description": "TEXT", "measure_id": "INTEGER", "work_type": "VARCHAR(30) DEFAULT 'print'", "production_book": "BOOLEAN NOT NULL DEFAULT 0", "production_poly": "BOOLEAN NOT NULL DEFAULT 0", "production_souvenir": "BOOLEAN NOT NULL DEFAULT 0", "production_wide": "BOOLEAN NOT NULL DEFAULT 0"},
        "printers": {"production_book": "BOOLEAN NOT NULL DEFAULT 0", "production_poly": "BOOLEAN NOT NULL DEFAULT 0", "production_souvenir": "BOOLEAN NOT NULL DEFAULT 0", "production_wide": "BOOLEAN NOT NULL DEFAULT 0"},
        "orders": {"calc_details": "TEXT"},
        "compiles": {"fitting": "INTEGER NOT NULL DEFAULT 0"},
    })


MIGRATIONS = (("2026-11-13-01", migration_2026_11_13_01),)


def _ensure_migration_table(database_engine) -> None:
    with database_engine.begin() as connection:
        connection.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
                version VARCHAR(64) PRIMARY KEY,
                applied_at DATETIME NOT NULL
            )
        """))


def apply_migrations(database_engine=engine) -> list[str]:
    """Create the model baseline and apply unrecorded migrations in order."""
    from . import models  # Register tables even when invoked directly from the CLI.

    Base.metadata.create_all(bind=database_engine)
    _ensure_migration_table(database_engine)
    with database_engine.begin() as connection:
        done = {row[0] for row in connection.execute(text(f"SELECT version FROM {MIGRATION_TABLE}")).all()}
        applied = []
        for version, migration in MIGRATIONS:
            if version in done:
                continue
            migration(connection)
            connection.execute(
                text(f"INSERT INTO {MIGRATION_TABLE} (version, applied_at) VALUES (:version, :applied_at)"),
                {"version": version, "applied_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")},
            )
            applied.append(version)
    return applied


def migration_status(database_engine=engine) -> list[dict[str, object]]:
    inspector = inspect(database_engine)
    if MIGRATION_TABLE not in inspector.get_table_names():
        done = set()
    else:
        with database_engine.connect() as connection:
            done = {row[0] for row in connection.execute(text(f"SELECT version FROM {MIGRATION_TABLE}")).all()}
    return [{"version": version, "applied": version in done} for version, _ in MIGRATIONS]


def upgrade_local_schema() -> None:
    """Compatibility wrapper for old callers."""
    apply_migrations(engine)