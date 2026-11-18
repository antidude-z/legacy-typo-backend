"""Read-only audit of historical domain data in an imported SQLite database."""

import argparse
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, text

from .php_serialization import loads


DOMAINS = {
    "identity": ("users", "roles", "permissions", "role_permissions"),
    "references": ("customers", "customer_groups", "papers", "materials", "printers", "prepresses", "redactions", "compiles", "afterprints"),
    "pricing": ("prices", "rates", "services"),
    "orders": ("orders", "blanks", "order_markups", "order_prepresses", "order_compiles", "order_other_works", "order_redactions"),
    "accounting": ("bills", "payments", "payers"),
    "payroll": ("payrolls", "payroll_orders"),
    "reports": ("reports", "report_params"),
}


def _count(connection, table):
    return connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0


def audit_database(database_engine) -> dict[str, object]:
    with database_engine.connect() as connection:
        tables = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        counts = {domain: {table: _count(connection, table) for table in names if table in tables} for domain, names in DOMAINS.items()}

        calc = Counter()
        calc_samples = []
        if "orders" in tables:
            for order_id, raw in connection.execute(text("SELECT id, calc_details FROM orders WHERE calc_details IS NOT NULL AND calc_details <> ''")):
                try:
                    decoded = loads(raw)
                    if not isinstance(decoded, dict):
                        raise ValueError("top-level value is not an array")
                    calc["decoded"] += 1
                    if not {"printing", "blanks", "design", "editing", "compile", "other"}.intersection(decoded):
                        calc["decoded_without_known_sections"] += 1
                except Exception as exc:
                    calc["invalid"] += 1
                    if len(calc_samples) < 20:
                        calc_samples.append({"order_id": order_id, "error": type(exc).__name__})
            calc["empty"] = connection.execute(text("SELECT COUNT(*) FROM orders WHERE calc_details IS NULL OR calc_details = ''")).scalar() or 0

        distributions = {}
        for table, column in (("orders", "order_type"), ("orders", "status_id"), ("bills", "currency"), ("bills", "paid"), ("bills", "closed"), ("bills", "filed"), ("payrolls", "status")):
            if table in tables:
                distributions[f"{table}.{column}"] = {str(key): value for key, value in connection.execute(text(f"SELECT {column}, COUNT(*) FROM {table} GROUP BY {column}")).all()}

        missing_role_users = 0
        if {"users", "roles"}.issubset(tables):
            missing_role_users = connection.execute(text("SELECT COUNT(*) FROM users u LEFT JOIN roles r ON u.role_id=r.id WHERE u.role_id IS NOT NULL AND r.id IS NULL")).scalar() or 0
        payment_total = None
        if "payments" in tables:
            payment_total = connection.execute(text("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE deleted_at IS NULL")).scalar()

    return {
        "table_counts": counts,
        "calculation_details": {**dict(calc), "invalid_samples": calc_samples},
        "distributions": distributions,
        "missing_role_users": missing_role_users,
        "active_payment_total": str(payment_total) if payment_total is not None else None,
        "read_only": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("database does not exist")
    result = audit_database(create_engine(f"sqlite:///{args.database.resolve()}"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()