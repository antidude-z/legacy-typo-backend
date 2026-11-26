"""Dependency-free, tracked schema migrations for the local rework database."""

from datetime import UTC, datetime
import re

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


def migration_2026_11_19_01(connection) -> None:
    """Bridge deployed MySQL column names without discarding historical rows."""
    original_mode = None
    if connection.dialect.name == "mysql":
        original_mode = connection.execute(text("SELECT @@SESSION.sql_mode")).scalar()
        # Legacy DDL contains zero-date defaults; relax only this DDL session.
        connection.execute(text("SET SESSION sql_mode='NO_AUTO_VALUE_ON_ZERO'"))
    try:
        _add_columns(connection, {
            "printers": {"production": "VARCHAR(30)"},
            "afterprints": {"production": "VARCHAR(30)"},
            "actions": {"item_id": "INTEGER"},
        })
        columns = {c["name"] for c in inspect(connection).get_columns("actions")}
        if {"actionable_id", "actionable_type"}.issubset(columns):
            if connection.dialect.name == 'mysql':
                connection.execute(text("UPDATE actions SET item_id=CAST(actionable_id AS UNSIGNED) WHERE item_id IS NULL AND actionable_type=:kind AND actionable_id REGEXP '^[0-9]+$'"), {'kind': 'App\\Order'})
            else:
                for row in connection.execute(text("SELECT id, actionable_id, actionable_type FROM actions WHERE item_id IS NULL")).mappings().all():
                    if row["actionable_type"] == "App\\Order" and str(row["actionable_id"]).isdigit():
                        connection.execute(text("UPDATE actions SET item_id=:item WHERE id=:id"), {"item": int(row["actionable_id"]), "id": row["id"]})
    finally:
        if original_mode is not None:
            connection.execute(text("SET SESSION sql_mode=:mode"), {"mode": original_mode})


def migration_2026_11_19_02(connection) -> None:
    """Permit application NULLs in imported legacy MySQL columns."""
    if connection.dialect.name != "mysql":
        return
    original_mode = connection.execute(text("SELECT @@SESSION.sql_mode")).scalar()
    connection.execute(text("SET SESSION sql_mode='NO_AUTO_VALUE_ON_ZERO'"))
    try:
        inspector = inspect(connection)
        quote = connection.dialect.identifier_preparer.quote
        for table in Base.metadata.sorted_tables:
            for column in inspector.get_columns(table.name):
                model_column = table.c.get(column['name'])
                legacy_action_field = table.name == 'actions' and column['name'] in {'actionable_id', 'actionable_type'}
                if not column['nullable'] and ((model_column is not None and model_column.nullable) or legacy_action_field):
                    declaration = column['type'].compile(dialect=connection.dialect)
                    connection.execute(text(f"ALTER TABLE {quote(table.name)} MODIFY COLUMN {quote(column['name'])} {declaration} NULL DEFAULT NULL"))
    finally:
        connection.execute(text("SET SESSION sql_mode=:mode"), {'mode': original_mode})


def migration_2026_11_19_04(connection) -> None:
    """Restore missing non-unique model indexes on pre-existing tables.

    Do not create foreign keys or uniqueness constraints over historical data.
    Equivalent differently named indexes are retained instead of duplicated.
    """
    inspector = inspect(connection)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        columns = {row['name'] for row in inspector.get_columns(table.name)}
        existing = {tuple(row['column_names']) for row in inspector.get_indexes(table.name)}
        existing.add(tuple(inspector.get_pk_constraint(table.name).get('constrained_columns') or []))
        for index in sorted(table.indexes, key=lambda item: item.name):
            names = tuple(column.name for column in index.columns)
            if not index.unique and set(names).issubset(columns) and names not in existing:
                index.create(bind=connection)
                existing.add(names)


def migration_2026_11_19_05(connection) -> None:
    """Widen confirmed writable MySQL fields without narrowing source data."""
    if connection.dialect.name != 'mysql':
        return
    inspector = inspect(connection)
    mode = connection.scalar(text('SELECT @@SESSION.sql_mode'))
    connection.execute(text("SET SESSION sql_mode='NO_AUTO_VALUE_ON_ZERO'"))
    try:
        for table, field, declaration in (
            ('users', 'surname', 'VARCHAR(255)'),
            ('actions', 'comment', 'VARCHAR(255)'),
            ('order_markups', 'value', 'NUMERIC(10,2)'),
        ):
            columns = {row['name']: row for row in inspector.get_columns(table)}
            current = columns.get(field)
            if current is None:
                continue
            target = Base.metadata.tables[table].c[field].type.compile(dialect=connection.dialect)
            if current['type'].compile(dialect=connection.dialect).upper() == target.upper():
                continue
            nullable = 'NULL' if current['nullable'] else 'NOT NULL'
            # Preserve the imported scalar default, quoted by the driver.
            default = current.get('default')
            suffix = f' DEFAULT {default}' if default is not None else ''
            connection.execute(text(f'ALTER TABLE {table} MODIFY COLUMN {field} {declaration} {nullable}{suffix}'))
    finally:
        connection.execute(text('SET SESSION sql_mode=:mode'), {'mode': mode})


def _sqlite_redeclare(connection, table, field, declaration):
    """Rebuild a table while retaining extra columns, indexes and triggers."""
    sql = connection.scalar(text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:name"), {'name': table})
    if not sql:
        return
    # These fixed targets have no incoming model foreign keys. Fail closed if
    # a deployment added one rather than silently cascading on DROP TABLE.
    for other in inspect(connection).get_table_names():
        if any(fk['referred_table'] == table for fk in inspect(connection).get_foreign_keys(other)):
            raise RuntimeError(f'Cannot rebuild {table}: incoming foreign key from {other}')
    pattern = rf'(?P<prefix>(?:"{field}"|\b{field}\b)\s+)(?:NUMERIC\s*\([^)]*\)|INTEGER)(?:\s+NOT NULL)?'
    changed, count = re.subn(pattern, lambda match: match['prefix'] + declaration, sql, count=1, flags=re.I)
    if count != 1:
        raise RuntimeError(f'Unrecognized SQLite declaration: {table}.{field}')
    temp = f'_upgrade_{table}'
    changed = re.sub(r'^(CREATE TABLE\s+)(?:"' + table + r'"|' + table + r')(?=\s|\()', lambda m: m[1] + '"' + temp + '"', changed, count=1, flags=re.I)
    objects = connection.execute(text("SELECT sql FROM sqlite_master WHERE tbl_name=:name AND type IN ('index','trigger') AND sql IS NOT NULL"), {'name': table}).scalars().all()
    quote = connection.dialect.identifier_preparer.quote
    columns = ', '.join(quote(c['name']) for c in inspect(connection).get_columns(table))
    connection.execute(text(changed))
    connection.execute(text(f'INSERT INTO {quote(temp)} ({columns}) SELECT {columns} FROM {quote(table)}'))
    connection.execute(text(f'DROP TABLE {quote(table)}'))
    connection.execute(text(f'ALTER TABLE {quote(temp)} RENAME TO {quote(table)}'))
    for statement in objects:
        connection.execute(text(statement))


def migration_2026_11_19_06(connection):
    if connection.dialect.name == 'sqlite':
        for table in ('order_prepresses', 'order_redactions'):
            column = next(c for c in inspect(connection).get_columns(table) if c['name'] == 'quantity')
            if str(column['type']).upper() != 'NUMERIC(8, 2)':
                _sqlite_redeclare(connection, table, 'quantity', 'NUMERIC(8,2) NOT NULL')
        column = next(c for c in inspect(connection).get_columns('actions') if c['name'] == 'item_id')
        if not column['nullable']:
            _sqlite_redeclare(connection, 'actions', 'item_id', 'INTEGER')
    elif connection.dialect.name == 'mysql':
        column = next(c for c in inspect(connection).get_columns('order_markups') if c['name'] == 'markup_type')
        if column['type'].length < 50:
            mode = connection.scalar(text('SELECT @@SESSION.sql_mode'))
            connection.execute(text("SET SESSION sql_mode='NO_AUTO_VALUE_ON_ZERO'"))
            try:
                connection.execute(text('ALTER TABLE order_markups MODIFY COLUMN markup_type VARCHAR(50) NOT NULL'))
            finally:
                connection.execute(text('SET SESSION sql_mode=:mode'), {'mode': mode})


def migration_2026_11_26_01(connection):
    """Add revocation stamp without modifying existing credential or business data."""
    if connection.dialect.name != 'mysql':
        _add_columns(connection, {'users': {'security_stamp': 'VARCHAR(64)'}})
        return
    mode = connection.scalar(text('SELECT @@SESSION.sql_mode'))
    connection.execute(text("SET SESSION sql_mode='NO_AUTO_VALUE_ON_ZERO'"))
    try:
        _add_columns(connection, {'users': {'security_stamp': 'VARCHAR(64)'}})
    finally:
        connection.execute(text('SET SESSION sql_mode=:mode'), {'mode': mode})


MIGRATIONS = (
    ("2026-11-13-01", migration_2026_11_13_01),
    ("2026-11-19-01", migration_2026_11_19_01),
    ("2026-11-19-02", migration_2026_11_19_02),
    ("2026-11-19-03", migration_2026_11_19_02),
    ("2026-11-19-04", migration_2026_11_19_04),
    ("2026-11-19-05", migration_2026_11_19_05),
    ("2026-11-19-06", migration_2026_11_19_06),
    ("2026-11-26-01", migration_2026_11_26_01),
)


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