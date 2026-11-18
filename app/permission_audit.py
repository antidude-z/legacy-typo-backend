"""Permission coverage manifest for the migrated route families.

This is intentionally declarative.  Existing route handlers retain their
compatibility behavior; the manifest makes the authorization contract
reviewable and testable before production cutover.
"""

ROUTE_PERMISSION_AUDIT = (
    {
        "family": "orders",
        "paths": ["/api/orders", "/api/orders/{order_id}/*"],
        "read": "authenticated session",
        "write": "authenticated session",
        "lifecycle": ["view_trashed", "restore_trashed", "delete_trashed"],
        "notes": "Legacy order routes had no dedicated CRUD permission; lifecycle permissions remain explicit.",
    },
    {
        "family": "pricing",
        "paths": ["/api/pricing/*", "/api/prices/*"],
        "read": "authenticated session",
        "write": "edit_price",
        "lifecycle": ["delete_price"],
        "notes": "The migrated API deliberately enforces edit/delete permissions on writes.",
    },
    {
        "family": "accounting bills",
        "paths": ["/api/accounting/bills/*"],
        "read": "view_accounting_bills",
        "write": "edit_accounting_bills",
        "lifecycle": ["restore_trashed", "delete_trashed"],
        "notes": "Bill and payment access is parent-scoped and permission checked.",
    },
    {
        "family": "accounting payers",
        "paths": ["/api/accounting/payers/*"],
        "read": "authenticated session",
        "write": "authenticated session",
        "lifecycle": ["restore_trashed", "delete_trashed"],
        "notes": "No dedicated payer CRUD permission exists in the legacy catalog.",
    },
    {
        "family": "references",
        "paths": ["/api/options/*", "/api/references/*", "/api/reference-works/*"],
        "read": "authenticated session",
        "write": "authenticated session",
        "lifecycle": ["view_trashed", "restore_trashed", "delete_trashed"],
        "notes": "Legacy catalog has menu permissions but no per-directory CRUD permissions.",
    },
    {
        "family": "user administration",
        "paths": ["/api/references/users/*"],
        "read": "authenticated session",
        "write": ["user_create", "user_edit"],
        "lifecycle": ["user_delete", "restore_trashed", "delete_trashed"],
        "notes": "User route handlers enforce the dedicated legacy user permissions.",
    },
    {
        "family": "permissions administration",
        "paths": ["/api/options/permissions"],
        "read": "view_menu_options_permissions",
        "write": "view_menu_options_permissions",
        "lifecycle": [],
        "notes": "Role matrix administration requires the permission-management capability.",
    },
    {
        "family": "reports",
        "paths": ["/api/reports/*", "/reports/*"],
        "read": "authenticated session",
        "write": "view_menu_options_reports for report settings",
        "lifecycle": [],
        "notes": "Generation is authenticated; report settings require the options permission.",
    },
    {
        "family": "payroll",
        "paths": ["/api/reports/payrolls/*", "/reports/payrolls/*"],
        "read": "view_menu_reports_payrolls",
        "write": "edit_reports_payrolls",
        "lifecycle": [],
        "notes": "Payroll route handlers enforce dedicated report permissions.",
    },
    {
        "family": "authentication",
        "paths": ["/api/auth/*", "/api/password/*"],
        "read": "guest or authenticated session by workflow",
        "write": "guest or authenticated session by workflow",
        "lifecycle": [],
        "notes": "Registration/reset reject already authenticated sessions; password changes invalidate sessions.",
    },
)

DEDICATED_PERMISSION_IDS = frozenset({
    "edit_price", "delete_price", "view_accounting_bills", "edit_accounting_bills",
    "user_create", "user_edit", "user_delete", "view_menu_options_permissions",
    "view_menu_options_reports", "view_menu_reports_payrolls", "edit_reports_payrolls",
})


def audit_payload(permission_ids=None) -> dict:
    available = set(permission_ids or ())
    return {
        "families": [dict(item) for item in ROUTE_PERMISSION_AUDIT],
        "dedicated_permissions": sorted(DEDICATED_PERMISSION_IDS),
        "missing_catalog_permissions": sorted(DEDICATED_PERMISSION_IDS - available) if permission_ids is not None else [],
        "catalog_complete": permission_ids is None or not (DEDICATED_PERMISSION_IDS - available),
    }