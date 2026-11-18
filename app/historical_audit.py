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

        payer_associations = {
            "pivot_rows": 0,
            "valid_customer_rows": 0,
            "valid_payer_rows": 0,
            "valid_pairs": 0,
            "orphan_customer_rows": 0,
            "orphan_payer_rows": 0,
            "duplicate_pairs": 0,
            "bills_with_payers": 0,
            "orders_with_customer_and_bill": 0,
        }
        if "customer_payer" in tables:
            payer_associations["pivot_rows"] = connection.execute(text("SELECT COUNT(*) FROM customer_payer")).scalar() or 0
            if "customers" in tables:
                payer_associations["valid_customer_rows"] = connection.execute(text("SELECT COUNT(*) FROM customer_payer p JOIN customers c ON c.id = p.customer_id")).scalar() or 0
            if "payers" in tables:
                payer_associations["valid_payer_rows"] = connection.execute(text("SELECT COUNT(*) FROM customer_payer p JOIN payers x ON x.id = p.payer_id")).scalar() or 0
            if {"customers", "payers"}.issubset(tables):
                payer_associations["valid_pairs"] = connection.execute(text("SELECT COUNT(*) FROM customer_payer p JOIN customers c ON c.id=p.customer_id JOIN payers x ON x.id=p.payer_id")).scalar() or 0
                payer_associations["duplicate_pairs"] = connection.execute(text("SELECT COALESCE(SUM(n-1),0) FROM (SELECT customer_id,payer_id,COUNT(*) n FROM customer_payer GROUP BY customer_id,payer_id HAVING COUNT(*) > 1)")).scalar() or 0
            payer_associations["orphan_customer_rows"] = payer_associations["pivot_rows"] - payer_associations["valid_customer_rows"]
            payer_associations["orphan_payer_rows"] = payer_associations["pivot_rows"] - payer_associations["valid_payer_rows"]
        if "bills" in tables and "payers" in tables:
            payer_associations["bills_with_payers"] = connection.execute(text("SELECT COUNT(*) FROM bills b JOIN payers p ON p.id=b.payer_id WHERE b.payer_id IS NOT NULL")).scalar() or 0
        if {"orders", "customers", "bills"}.issubset(tables):
            payer_associations["orders_with_customer_and_bill"] = connection.execute(text("SELECT COUNT(*) FROM orders o JOIN customers c ON c.id=o.customer_id JOIN bills b ON b.id=o.bill_id WHERE o.customer_id IS NOT NULL AND o.bill_id IS NOT NULL")).scalar() or 0

        payroll_audit = {
            "statements": 0, "paid_statements": 0, "calc_statements": 0,
            "eligible_orders": 0, "snapshot_rows": 0, "orphan_snapshot_rows": 0,
            "duplicate_statement_orders": 0, "deleted_eligible_orders": 0,
            "paid_snapshot_rows": 0, "invalid_percent_rows": 0,
        }
        if "payrolls" in tables:
            payroll_audit["statements"] = _count(connection, "payrolls")
            payroll_audit["paid_statements"] = connection.execute(text("SELECT COUNT(*) FROM payrolls WHERE status='paid'")).scalar() or 0
            payroll_audit["calc_statements"] = connection.execute(text("SELECT COUNT(*) FROM payrolls WHERE status='calc'")).scalar() or 0
        if {"payroll_orders", "payrolls"}.issubset(tables):
            payroll_audit["snapshot_rows"] = _count(connection, "payroll_orders")
            payroll_audit["paid_snapshot_rows"] = connection.execute(text("SELECT COUNT(*) FROM payroll_orders po JOIN payrolls p ON p.id=po.payroll_id WHERE p.status='paid'")).scalar() or 0
            payroll_audit["orphan_snapshot_rows"] = connection.execute(text("SELECT COUNT(*) FROM payroll_orders po LEFT JOIN payrolls p ON p.id=po.payroll_id WHERE p.id IS NULL")).scalar() or 0
            payroll_audit["duplicate_statement_orders"] = connection.execute(text("SELECT COALESCE(SUM(n-1),0) FROM (SELECT payroll_id,order_id,COUNT(*) n FROM payroll_orders GROUP BY payroll_id,order_id HAVING COUNT(*) > 1)")).scalar() or 0
            payroll_audit["invalid_percent_rows"] = connection.execute(text("SELECT COUNT(*) FROM payroll_orders WHERE percent < 0 OR percent > 15")).scalar() or 0
        if {"orders", "bills"}.issubset(tables):
            payroll_audit["eligible_orders"] = connection.execute(text("SELECT COUNT(*) FROM orders o JOIN bills b ON b.id=o.bill_id WHERE o.deleted_at IS NULL AND b.paid=1 AND b.closed=1 AND b.filed=1")).scalar() or 0
            payroll_audit["deleted_eligible_orders"] = connection.execute(text("SELECT COUNT(*) FROM orders o JOIN bills b ON b.id=o.bill_id WHERE o.deleted_at IS NOT NULL AND b.paid=1 AND b.closed=1 AND b.filed=1")).scalar() or 0

    return {
        "table_counts": counts,
        "calculation_details": {**dict(calc), "invalid_samples": calc_samples},
        "distributions": distributions,
        "missing_role_users": missing_role_users,
        "active_payment_total": str(payment_total) if payment_total is not None else None,
        "customer_payer": payer_associations,
        "payroll": payroll_audit,
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