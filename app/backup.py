"""Safe SQLite backup and restore helpers for local operations."""

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _check_sqlite(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"SQLite database does not exist: {path}")
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            raise ValueError(f"SQLite integrity check failed: {exc}") from exc
        if result != "ok":
            raise ValueError(f"SQLite integrity check failed: {result}")
        pages = connection.execute("PRAGMA page_count").fetchone()[0]
        return {"integrity": result, "page_count": pages}
    finally:
        connection.close()


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup(source, destination) -> dict:
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError("Backup destination must differ from source")
    source_check = _check_sqlite(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError(f"Backup destination already exists: {destination}")
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        source_connection = sqlite3.connect(source)
        target_connection = sqlite3.connect(temporary)
        try:
            source_connection.backup(target_connection)
        finally:
            target_connection.close()
            source_connection.close()
        _check_sqlite(temporary)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"operation": "backup", "source": str(source), "destination": str(destination), "source_check": source_check, "sha256": _digest(destination), "created_at": datetime.now(timezone.utc).isoformat()}


def restore(source, destination, replace=False) -> dict:
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError("Restore source must differ from destination")
    source_check = _check_sqlite(source)
    if destination.exists() and not replace:
        raise ValueError(f"Restore destination exists; use replace explicitly: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.restore.tmp")
    try:
        source_connection = sqlite3.connect(source)
        target_connection = sqlite3.connect(temporary)
        try:
            source_connection.backup(target_connection)
        finally:
            target_connection.close()
            source_connection.close()
        _check_sqlite(temporary)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"operation": "restore", "source": str(source), "destination": str(destination), "replaced": replace, "source_check": source_check, "sha256": _digest(destination), "restored_at": datetime.now(timezone.utc).isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("source", type=Path)
    backup_parser.add_argument("destination", type=Path)
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("source", type=Path)
    restore_parser.add_argument("destination", type=Path)
    restore_parser.add_argument("--replace", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = backup(args.source, args.destination) if args.operation == "backup" else restore(args.source, args.destination, args.replace)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()