"""Compare the archived MySQL dump schema with the rework SQLAlchemy schema.

The dump is intentionally parsed as text only.  No SQL from the dump is executed.
"""

import argparse
import json
import re
from pathlib import Path

from .db import Base

_CREATE_TABLE = re.compile(r"^CREATE TABLE `([^`]+)`")
_COLUMN = re.compile(r"^\s*`([^`]+)`\s+")


def dump_schema(path: str | Path) -> dict[str, list[str]]:
    """Return table/column names from a MySQL dump without loading it wholly."""
    tables: dict[str, list[str]] = {}
    current: str | None = None
    with Path(path).open("r", encoding="utf-8", errors="replace") as source:
        for raw_line in source:
            line = raw_line.rstrip("\r\n")
            match = _CREATE_TABLE.match(line)
            if match:
                current = match.group(1)
                tables[current] = []
                continue
            if current is None:
                continue
            if line.startswith(") ENGINE=") or line == ");":
                current = None
                continue
            column = _COLUMN.match(line)
            if column:
                tables[current].append(column.group(1))
    return tables


def rework_schema() -> dict[str, list[str]]:
    """Return the currently declared SQLAlchemy table/column names."""
    from . import models  # noqa: F401  # register all model tables

    return {
        table.name: [column.name for column in table.columns]
        for table in Base.metadata.sorted_tables
    }


def compare_schemas(dump: dict[str, list[str]], rework: dict[str, list[str]]) -> dict[str, object]:
    dump_tables = set(dump)
    rework_tables = set(rework)
    shared = sorted(dump_tables & rework_tables)
    column_differences = {}
    for table in shared:
        dump_columns = set(dump[table])
        rework_columns = set(rework[table])
        missing = sorted(dump_columns - rework_columns)
        extra = sorted(rework_columns - dump_columns)
        if missing or extra:
            column_differences[table] = {"missing_in_rework": missing, "extra_in_rework": extra}
    return {
        "dump_tables": sorted(dump_tables),
        "rework_tables": sorted(rework_tables),
        "missing_tables_in_rework": sorted(dump_tables - rework_tables),
        "extra_tables_in_rework": sorted(rework_tables - dump_tables),
        "column_differences": column_differences,
    }


def build_inventory(dump_path: str | Path) -> dict[str, object]:
    dump = dump_schema(dump_path)
    rework = rework_schema()
    result = compare_schemas(dump, rework)
    result["dump_path"] = str(Path(dump_path))
    result["note"] = "Names only; dump SQL was not executed. Type, constraint, index, and data mapping require separate review."
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    inventory = build_inventory(args.dump)
    rendered = json.dumps(inventory, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()