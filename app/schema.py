from sqlalchemy import inspect, text

from .db import engine


def upgrade_local_schema() -> None:
    """Apply additive compatibility columns to an existing local SQLite DB."""
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    with engine.begin() as connection:
        if "orders" in inspector.get_table_names() and "calc_details" not in {column["name"] for column in inspector.get_columns("orders")}:
            connection.execute(text("ALTER TABLE orders ADD COLUMN calc_details TEXT"))
        if "compiles" in inspector.get_table_names() and "fitting" not in {column["name"] for column in inspector.get_columns("compiles")}:
            connection.execute(text("ALTER TABLE compiles ADD COLUMN fitting INTEGER NOT NULL DEFAULT 0"))
