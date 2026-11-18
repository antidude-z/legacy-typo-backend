"""Validate a disposable SQLite database created by the legacy dump importer."""

import argparse
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Date, DateTime, Integer, Numeric, create_engine, inspect, select, text

from .db import Base
from .historical_data_policy import POLICY


def validate_import(database_engine) -> dict[str, object]:
    from . import models  # noqa: F401

    inspector = inspect(database_engine)
    tables = set(inspector.get_table_names())
    violations = []
    with database_engine.connect() as connection:
        foreign_key_rows = connection.execute(text("PRAGMA foreign_key_check")).all()
        for row in foreign_key_rows:
            violations.append({"type": "foreign_key", "table": row[0], "rowid": row[1], "parent": row[2]})

        nulls = {}
        conversion = {"invalid_dates": [], "invalid_datetimes": [], "invalid_decimals": [], "invalid_integers": []}
        soft_deleted = {}
        row_counts = {}
        uniqueness = []
        for table in Base.metadata.sorted_tables:
            if table.name not in tables:
                violations.append({"type": "missing_table", "table": table.name})
                continue
            row_counts[table.name] = connection.execute(select(table.count())).scalar() if hasattr(table, "count") else connection.execute(text(f"SELECT COUNT(*) FROM {table.name}")).scalar()
            deleted = table.c.get("deleted_at")
            if deleted is not None:
                soft_deleted[table.name] = connection.execute(text(f"SELECT COUNT(*) FROM {table.name} WHERE deleted_at IS NOT NULL")).scalar()
            required = [column for column in table.columns if not column.nullable and column.default is None and column.server_default is None]
            for column in required:
                count = connection.execute(text(f"SELECT COUNT(*) FROM {table.name} WHERE {column.name} IS NULL")).scalar()
                if count:
                    nulls[f"{table.name}.{column.name}"] = count
            for column in table.columns:
                values = connection.execute(select(column).where(column.is_not(None)).limit(1000)).scalars().all()
                for value in values:
                    try:
                        if isinstance(column.type, Date) and not isinstance(column.type, DateTime) and not isinstance(value, date):
                            raise ValueError()
                        if isinstance(column.type, DateTime) and not isinstance(value, datetime):
                            raise ValueError()
                        if isinstance(column.type, Numeric) and not isinstance(value, (int, float)):
                            # SQLite may return Decimal or numeric strings depending on driver.
                            from decimal import Decimal
                            Decimal(str(value))
                        if isinstance(column.type, Integer) and not isinstance(value, int):
                            int(value)
                    except Exception:
                        key = "invalid_dates" if isinstance(column.type, Date) else "invalid_datetimes" if isinstance(column.type, DateTime) else "invalid_decimals" if isinstance(column.type, Numeric) else "invalid_integers"
                        conversion[key].append(f"{table.name}.{column.name}")
            for constraint in inspector.get_unique_constraints(table.name):
                columns = constraint.get("column_names") or []
                if not columns:
                    continue
                grouped = ", ".join(columns)
                duplicate = connection.execute(text(f"SELECT COUNT(*) FROM (SELECT {grouped} FROM {table.name} GROUP BY {grouped} HAVING COUNT(*) > 1)")).scalar()
                if duplicate:
                    uniqueness.append({"table": table.name, "columns": columns, "duplicate_groups": duplicate})

        if "actions" in tables:
            unsupported = connection.execute(text("SELECT COUNT(*) FROM actions WHERE item_id IS NULL")).scalar()
            if unsupported:
                violations.append({"type": "action_mapping", "null_item_id": unsupported})
    foreign_key_summary = dict(sorted(Counter(
        f"{item.get('table')}->{item.get('parent')}" for item in violations if item.get("type") == "foreign_key"
    ).items()))
    strict_valid = not violations and not nulls and not uniqueness and not any(conversion.values())
    orphan_only = bool(violations) and all(item.get("type") == "foreign_key" for item in violations)
    return {
        "policy": POLICY,
        "row_counts": row_counts,
        "foreign_key_violations": violations,
        "foreign_key_summary": foreign_key_summary,
        "required_nulls": nulls,
        "uniqueness_violations": uniqueness,
        "conversion_anomalies": {key: sorted(set(values)) for key, values in conversion.items()},
        "soft_deleted_rows": soft_deleted,
        "strict_valid": strict_valid,
        "preservation_valid": (strict_valid or orphan_only) and not nulls and not uniqueness and not any(conversion.values()),
        "valid": strict_valid,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("database does not exist")
    database_engine = create_engine(f"sqlite:///{args.database.resolve()}")
    result = validate_import(database_engine)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["valid"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()