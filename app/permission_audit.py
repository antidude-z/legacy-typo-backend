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

AUTHORIZATION_MATRIX = (
    {"family": "orders", "method": "GET", "path": "/api/orders", "unauthenticated": 401, "unauthorized": "authenticated-only"},
    {"family": "orders", "method": "POST", "path": "/api/orders/{id}/prepresses", "unauthenticated": 401, "unauthorized": "authenticated-only"},
    {"family": "orders", "method": "POST", "path": "/api/orders/{id}/restore", "unauthenticated": 401, "unauthorized": "restore_trashed"},
    {"family": "pricing", "method": "GET", "path": "/api/prices/{kind}/{item}/records", "unauthenticated": 401, "unauthorized": "authenticated-only"},
    {"family": "pricing", "method": "POST", "path": "/api/prices/{kind}/{item}/records", "unauthenticated": 401, "unauthorized": "edit_price"},
    {"family": "accounting bills", "method": "GET", "path": "/api/accounting/bills", "unauthenticated": 401, "unauthorized": "view_accounting_bills"},
    {"family": "accounting bills", "method": "POST", "path": "/api/accounting/bills", "unauthenticated": 401, "unauthorized": "edit_accounting_bills"},
    {"family": "accounting payments", "method": "POST", "path": "/api/accounting/bills/{id}/payments", "unauthenticated": 401, "unauthorized": "edit_accounting_bills"},
    {"family": "accounting payers", "method": "GET", "path": "/api/accounting/payers", "unauthenticated": 401, "unauthorized": "authenticated-only"},
    {"family": "references", "method": "GET", "path": "/api/references/{kind}", "unauthenticated": 401, "unauthorized": "authenticated-only"},
    {"family": "user administration", "method": "POST", "path": "/api/employee-references", "unauthenticated": 401, "unauthorized": "user_create"},
    {"family": "user administration", "method": "PATCH", "path": "/api/employee-references/{id}", "unauthenticated": 401, "unauthorized": "user_edit"},
    {"family": "permissions administration", "method": "GET", "path": "/api/options/permissions", "unauthenticated": 401, "unauthorized": "view_menu_options_permissions"},
    {"family": "reports", "method": "GET", "path": "/api/reports/for/{model}/{id}", "unauthenticated": 401, "unauthorized": "authenticated-only"},
    {"family": "report settings", "method": "PATCH", "path": "/api/report-settings/{id}", "unauthenticated": 401, "unauthorized": "view_menu_options_reports"},
    {"family": "payroll", "method": "GET", "path": "/api/reports/payrolls/{id}", "unauthenticated": 401, "unauthorized": "view_menu_reports_payrolls"},
    {"family": "payroll", "method": "POST", "path": "/api/reports/payrolls", "unauthenticated": 401, "unauthorized": "edit_reports_payrolls"},
)


def audit_payload(permission_ids=None) -> dict:
    available = set(permission_ids or ())
    return {
        "families": [dict(item) for item in ROUTE_PERMISSION_AUDIT],
        "dedicated_permissions": sorted(DEDICATED_PERMISSION_IDS),
        "missing_catalog_permissions": sorted(DEDICATED_PERMISSION_IDS - available) if permission_ids is not None else [],
        "catalog_complete": permission_ids is None or not (DEDICATED_PERMISSION_IDS - available),
        "authorization_matrix": [dict(item) for item in AUTHORIZATION_MATRIX],
    }