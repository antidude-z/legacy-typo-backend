"""Machine-checkable contracts for active report definitions.

This validates supported metadata and configured parameters. It deliberately
does not claim visual, print-layout, or formula parity.
"""

from sqlalchemy import select

from .models import Report, ReportParam


REPORT_CONTRACTS = {
    "order_transcript": {"model": "App\\Order", "kind": "html", "form": False, "media_type": "text/html", "filename": "order_transcript-{id}.html", "params": set()},
    "order_passport": {"model": "App\\Order", "kind": "pdf", "form": False, "media_type": "application/pdf", "filename": "order-passport-{id}.pdf", "params": set()},
    "order_passport_wide": {"model": "App\\Order", "kind": "pdf", "form": False, "media_type": "application/pdf", "filename": "order-passport-{id}.pdf", "params": set()},
    "order_economy": {"model": "App\\Order", "kind": "xls", "form": False, "media_type": "application/vnd.ms-excel", "filename": "order-economy-{id}.xls", "params": set()},
    "order_economy_wide": {"model": "App\\Order", "kind": "xls", "form": False, "media_type": "application/vnd.ms-excel", "filename": "order-economy-{id}.xls", "params": set()},
    "order_design": {"model": "App\\Order", "kind": "xls", "form": False, "media_type": "application/vnd.ms-excel", "filename": "order-design-{id}.xls", "params": set()},
    "order_payment": {"model": "App\\Bill", "kind": "xls", "form": True, "media_type": "application/vnd.ms-excel", "filename": "payment-request-{id}.xls", "params": {"prorector", "zam_prorectora", "boss", "buh", "pfu"}},
    "order_shipping": {"model": "App\\Bill", "kind": "pdf", "form": False, "media_type": "application/pdf", "filename": "order-shipping-{id}.pdf", "params": {"boss", "pto", "buh"}},
}


def audit_report_catalog(db):
    rows = db.scalars(select(Report).where(Report.deleted_at.is_(None))).all()
    issues = []
    active = []
    for row in rows:
        contract = REPORT_CONTRACTS.get(row.id)
        if contract is None:
            issues.append({"report": row.id, "issue": "no_supported_contract"})
            continue
        active.append(row.id)
        for field in ("model", "kind", "form"):
            if getattr(row, field) != contract[field]:
                issues.append({"report": row.id, "issue": f"{field}_mismatch", "expected": contract[field], "actual": getattr(row, field)})
        aliases = {param.alias for param in db.scalars(select(ReportParam).where(ReportParam.report_id == row.id, ReportParam.deleted_at.is_(None))).all()}
        for alias in sorted(contract["params"] - aliases):
            issues.append({"report": row.id, "issue": "missing_parameter", "alias": alias})
    return {"active_reports": sorted(active), "supported_reports": sorted(REPORT_CONTRACTS), "issues": issues, "valid": not issues}