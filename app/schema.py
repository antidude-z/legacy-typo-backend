from sqlalchemy import inspect, text

from .db import engine


def upgrade_local_schema() -> None:
    """Apply additive compatibility columns to an existing local SQLite DB."""
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    with engine.begin() as connection:
        additions = {
            "bills": {"amount": "NUMERIC(10,2) NOT NULL DEFAULT 0", "currency": "VARCHAR(3) NOT NULL DEFAULT 'RUB'", "user_id": "INTEGER", "payer_id": "INTEGER"},
            "users": {"phone": "VARCHAR(50)", "post": "VARCHAR(50)", "deleted_at": "DATETIME", "remember_token": "VARCHAR(100)"},
            "customers": {"inn": "VARCHAR(12)", "phone": "VARCHAR(200)", "address": "TEXT", "description": "TEXT", "profit": "INTEGER NOT NULL DEFAULT 0", "customer_group_id": "INTEGER"},
            "afterprints": {
                "production_book": "BOOLEAN NOT NULL DEFAULT 0", "production_poly": "BOOLEAN NOT NULL DEFAULT 0",
                "production_souvenir": "BOOLEAN NOT NULL DEFAULT 0", "production_wide": "BOOLEAN NOT NULL DEFAULT 0",
                "weight": "INTEGER NOT NULL DEFAULT 0",
            },
            "papers": {"markup": "INTEGER NOT NULL DEFAULT 10"},
            "materials": {
                "description": "TEXT", "measure_id": "INTEGER", "work_type": "VARCHAR(30) DEFAULT 'print'",
                "production_book": "BOOLEAN NOT NULL DEFAULT 0", "production_poly": "BOOLEAN NOT NULL DEFAULT 0",
                "production_souvenir": "BOOLEAN NOT NULL DEFAULT 0", "production_wide": "BOOLEAN NOT NULL DEFAULT 0",
            },
            "printers": {
                "production_book": "BOOLEAN NOT NULL DEFAULT 0", "production_poly": "BOOLEAN NOT NULL DEFAULT 0",
                "production_souvenir": "BOOLEAN NOT NULL DEFAULT 0", "production_wide": "BOOLEAN NOT NULL DEFAULT 0",
            },
        }
        for table, fields in additions.items():
            if table not in inspector.get_table_names():
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, declaration in fields.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}"))
        if "orders" in inspector.get_table_names() and "calc_details" not in {column["name"] for column in inspector.get_columns("orders")}:
            connection.execute(text("ALTER TABLE orders ADD COLUMN calc_details TEXT"))
        if "compiles" in inspector.get_table_names() and "fitting" not in {column["name"] for column in inspector.get_columns("compiles")}:
            connection.execute(text("ALTER TABLE compiles ADD COLUMN fitting INTEGER NOT NULL DEFAULT 0"))
