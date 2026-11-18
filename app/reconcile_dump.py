"""Audit dump row counts and model relationships without importing data."""

import argparse
import json
from pathlib import Path

from .db import Base
from .import_dump import FRAMEWORK_TABLES, _statement_rows, _statements
from .schema_inventory import dump_schema


def audit_dump(path: str | Path) -> dict[str, object]:
    from . import models  # noqa: F401

    counts: dict[str, int] = {}
    statements = 0
    malformed: list[str] = []
    for statement in _statements(path):
        try:
            parsed = _statement_rows(statement)
        except ValueError as exc:
            malformed.append(type(exc).__name__)
            continue
        if parsed is None:
            continue
        table, _, rows = parsed
        statements += 1
        counts[table] = counts.get(table, 0) + len(rows)

    source_tables = dump_schema(path)
    model_tables = set(Base.metadata.tables)
    foreign_keys = []
    for table in Base.metadata.sorted_tables:
        for foreign_key in table.foreign_keys:
            foreign_keys.append({
                "table": table.name,
                "column": foreign_key.parent.name,
                "target": f"{foreign_key.column.table.name}.{foreign_key.column.name}",
            })
    return {
        "dump_path": str(Path(path)),
        "insert_statements": statements,
        "row_counts": dict(sorted(counts.items())),
        "framework_rows_excluded": {name: counts.get(name, 0) for name in sorted(FRAMEWORK_TABLES) if counts.get(name, 0)},
        "application_tables_without_rows": sorted(model_tables - set(counts)),
        "dump_tables_without_inserts": sorted(set(source_tables) - set(counts)),
        "model_foreign_keys": foreign_keys,
        "malformed_statement_count": len(malformed),
        "conversion_rules": {
            "zero_dates": "converted to NULL",
            "actions": "App\\Order actionable_id maps to actions.item_id; other polymorphic types are rejected",
            "timestamps": "MySQL timestamp values are converted to Python datetimes",
            "money": "numeric values are converted to Decimal",
        },
        "source_not_modified": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit_dump(args.dump)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()