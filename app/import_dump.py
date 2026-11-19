"""Opt-in, data-only MySQL dump conversion to a new disposable SQLite file."""

import argparse
import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, create_engine, inspect, text

from .db import Base
from .schema_inventory import dump_schema

FRAMEWORK_TABLES = {"migrations", "schema_migrations", "schema_versions", "password_resets"}
HEADER = re.compile(r"^INSERT INTO `([^`]+)`(?:\s*\(([^)]*)\))?\s+VALUES\s+", re.I)
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
ESCAPES = {"0": "\0", "b": "\b", "n": "\n", "r": "\r", "t": "\t", "Z": "\x1a"}
MAX_ROW_CHARS = 32 * 1024 * 1024


def _statement_rows(statement):
    match = HEADER.match(statement)
    if not match:
        return None
    table = match.group(1)
    columns = re.findall(r"`([^`]+)`", match.group(2)) if match.group(2) else None
    text_values = statement[match.end():]
    rows = []
    row = []
    token = []
    quoted = False
    escaped = False
    depth = 0
    for char in text_values:
        if quoted:
            token.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "'":
                quoted = False
            continue
        if char == "'":
            quoted = True
            token.append(char)
        elif char == "(":
            depth += 1
            if depth == 1:
                row = []
        elif char == ")":
            depth -= 1
            if depth == 0:
                row.append(_token(token))
                rows.append(row)
                token = []
            else:
                token.append(char)
        elif char == "," and depth == 1:
            row.append(_token(token))
            token = []
        else:
            if depth:
                token.append(char)
    if quoted or depth:
        raise ValueError("malformed INSERT statement")
    return table, columns, rows


def _token(token):
    raw = "".join(token).strip()
    if raw.upper() == "NULL":
        return None
    if raw.startswith("'") and raw.endswith("'"):
        value = raw[1:-1]
        return re.sub(r"\\([0abnrtZ\\'\"])", lambda m: ESCAPES.get(m.group(1), m.group(1)), value)
    if NUMBER.fullmatch(raw):
        return raw
    raise ValueError("unsupported SQL value")


def _statements(path):
    buffer = []
    quoted = False
    escaped = False
    with Path(path).open(encoding="utf-8", errors="strict") as source:
        for line in source:
            for char in line:
                buffer.append(char)
                if quoted:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == "'":
                        quoted = False
                elif char == "'":
                    quoted = True
                elif char == ";":
                    statement = "".join(buffer).strip()
                    buffer.clear()
                    if statement:
                        yield statement[:-1].strip()


def _coerce(column, value):
    if value is None:
        return None
    if isinstance(column.type, DateTime):
        return None if value.startswith("0000-00-00") else datetime.fromisoformat(value.replace(" ", "T"))
    if isinstance(column.type, Date):
        return None if value == "0000-00-00" else date.fromisoformat(value)
    if isinstance(column.type, Boolean):
        return value == "1"
    if isinstance(column.type, Integer):
        return int(Decimal(value))
    if isinstance(column.type, Numeric):
        return Decimal(value)
    return value


def import_dump(database_engine, dump_path, *, dry_run=False, limit=None, tables=None):
    from . import models  # noqa: F401
    if database_engine.dialect.name != "sqlite":
        raise ValueError("only disposable SQLite targets are supported")
    allowed = set(Base.metadata.tables) - FRAMEWORK_TABLES
    selected = allowed if tables is None else set(tables)
    if selected - allowed:
        raise ValueError(f"unapproved table selection: {sorted(selected - allowed)}")
    source_schema = dump_schema(dump_path)
    counts, skipped, statement_count = {}, {}, 0
    with database_engine.begin() as connection:
        existing = set(inspect(connection).get_table_names())
        for name in selected:
            if name not in existing:
                raise ValueError(f"target table is missing: {name}")
            if connection.execute(Base.metadata.tables[name].select().limit(1)).first():
                raise ValueError(f"target table is not empty: {name}")
        connection.execute(text("CREATE TABLE IF NOT EXISTS legacy_import_rows (table_name TEXT NOT NULL, row_number INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY (table_name, row_number))"))
        seen = {}
        for statement in _statements(dump_path):
            parsed = _statement_rows(statement)
            if parsed is None:
                continue
            table_name, columns, rows = parsed
            statement_count += 1
            if table_name not in selected:
                skipped[table_name] = skipped.get(table_name, 0) + len(rows)
                continue
            columns = columns or source_schema.get(table_name)
            if not columns:
                raise ValueError(f"missing source columns for {table_name}")
            target = Base.metadata.tables[table_name]
            for row in rows:
                if len(row) != len(columns):
                    raise ValueError(f"column/value count mismatch in {table_name}")
                seen[table_name] = seen.get(table_name, 0) + 1
                if limit is not None and sum(counts.values()) >= limit:
                    break
                raw = dict(zip(columns, row, strict=True))
                payload = {key: _coerce(target.c[key], value) for key, value in raw.items() if key in target.c}
                if table_name == "actions" and "actionable_id" in raw:
                    if raw.get("actionable_type") != "App\\Order":
                        raise ValueError("unsupported polymorphic action type")
                    payload["item_id"] = _coerce(target.c.item_id, raw["actionable_id"])
                required = {column.name for column in target.c if not column.nullable and column.default is None and column.server_default is None}
                if required - set(payload):
                    raise ValueError(f"missing required fields in {table_name}: {sorted(required - set(payload))}")
                connection.execute(target.insert().values(payload))
                connection.execute(text("INSERT INTO legacy_import_rows (table_name, row_number, payload) VALUES (:table, :row, :payload)"), {"table": table_name, "row": seen[table_name], "payload": json.dumps(raw, ensure_ascii=False)})
                counts[table_name] = counts.get(table_name, 0) + 1
            if limit is not None and sum(counts.values()) >= limit:
                break
        result = {"dry_run": dry_run, "statements": statement_count, "rows": counts, "skipped_rows": skipped}
        if dry_run:
            connection.rollback()
            # begin() context will not commit after an explicit rollback.
            return result
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--tables", nargs="+")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.dump.is_file() or args.target.exists() or (args.report and args.report.exists()):
        parser.error("source must exist; target/report must not already exist")
    from . import models  # noqa: F401
    args.target.parent.mkdir(parents=True, exist_ok=True)
    target_engine = create_engine(f"sqlite:///{args.target.resolve()}")
    try:
        Base.metadata.create_all(target_engine)
        result = import_dump(target_engine, args.dump, dry_run=args.dry_run, limit=args.limit, tables=args.tables)
    finally:
        target_engine.dispose()
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()