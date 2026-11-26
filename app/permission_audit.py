"""Permission coverage manifest for the migrated route families.

This is intentionally declarative.  Existing route handlers retain their
compatibility behavior; the manifest makes the authorization contract
reviewable and testable before production cutover.
"""

ROUTE_PERMISSION_AUDIT = (
    {
        "family": "orders",
        "paths": ["/api/orders", "/api/orders/*", "/orders", "/orders/*"],
        "read": "view_menu_orders",
        "write": "view_menu_orders AND edit_orders; delete requires delete_orders",
        "lifecycle": ["view_trashed", "restore_trashed", "delete_trashed"],
        "notes": "Active parent and matching child ownership required; generic trash grants never replace domain-delete authority. Filters are read-authorized session state.",
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
        "read": "view_menu_accounting_payers",
        "write": "view_menu_accounting_payers AND edit_accounting_payers; delete requires delete_accounting_payers",
        "lifecycle": ["restore_trashed", "delete_trashed"],
        "notes": "Restore/permanent delete require domain-delete AND generic lifecycle grants.",
    },
    {
        "family": "references",
        "paths": ["/api/options/{kind}", "/api/references/*", "/api/customer-references", "/api/customer-references/*", "/api/reference-works/*"],
        "read": "domain read grant; see s03_policy.domains",
        "write": "domain read AND dedicated domain edit/delete capability; see s03_policy.domains",
        "lifecycle": ["view_trashed", "restore_trashed", "delete_trashed"],
        "notes": "Administration differs from order-scoped selectors. Nested resources require active matching parents. New action capabilities are not auto-granted.",
    },
    {
        "family": "user administration",
        "paths": ["/api/employee-references", "/api/employee-references/*"],
        "read": "view_menu_references_users",
        "write": ["user_create", "user_edit", "user_assign_role", "user_reset_credentials"],
        "lifecycle": ["user_delete", "restore_trashed", "delete_trashed"],
        "notes": "Role changes require explicit delegation; credential changes require reset authority. Non-security administrators may only manage targets/assign roles whose grants are a subset of their own. Self-role changes are denied; lifecycle and last-admin checks still apply. S04 acceptance remains in progress.",
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
        "read": "parent domain read: view_accounting_bills or view_menu_orders; bill order-document collection requires both",
        "write": "view_menu_options_reports for report settings",
        "lifecycle": [],
        "notes": "Discovery, forms and GET/POST generation require active readable parents. Raw transcripts require Orders read. Settings authority does not grant document access. Payroll has its separate policy below.",
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
    {"family": "orders", "method": "GET", "path": "/api/orders", "unauthenticated": 401, "unauthorized": "view_menu_orders"},
    {"family": "orders", "method": "POST", "path": "/api/orders/{id}/prepresses", "unauthenticated": 401, "unauthorized": "view_menu_orders AND edit_orders"},
    {"family": "orders", "method": "POST", "path": "/api/orders/{id}/restore", "unauthenticated": 401, "unauthorized": "view_menu_orders AND delete_orders AND restore_trashed"},
    {"family": "pricing", "method": "GET", "path": "/api/prices/{kind}/{item}/records", "unauthenticated": 401, "unauthorized": "authenticated-only"},
    {"family": "pricing", "method": "POST", "path": "/api/prices/{kind}/{item}/records", "unauthenticated": 401, "unauthorized": "edit_price"},
    {"family": "accounting bills", "method": "GET", "path": "/api/accounting/bills", "unauthenticated": 401, "unauthorized": "view_accounting_bills"},
    {"family": "accounting bills", "method": "POST", "path": "/api/accounting/bills", "unauthenticated": 401, "unauthorized": "edit_accounting_bills"},
    {"family": "accounting payments", "method": "POST", "path": "/api/accounting/bills/{id}/payments", "unauthenticated": 401, "unauthorized": "edit_accounting_bills"},
    {"family": "accounting payers", "method": "GET", "path": "/api/accounting/payers", "unauthenticated": 401, "unauthorized": "view_menu_accounting_payers"},
    {"family": "references", "method": "GET", "path": "/api/references/{kind}", "unauthenticated": 401, "unauthorized": "domain read grant; see s03_policy.domains"},
    {"family": "user administration", "method": "POST", "path": "/api/employee-references", "unauthenticated": 401, "unauthorized": "user_create"},
    {"family": "user administration", "method": "PATCH", "path": "/api/employee-references/{id}", "unauthenticated": 401, "unauthorized": "user_edit"},
    {"family": "permissions administration", "method": "GET", "path": "/api/options/permissions", "unauthenticated": 401, "unauthorized": "view_menu_options_permissions"},
    {"family": "reports", "method": "GET", "path": "/api/reports/for/{model}/{id}", "unauthenticated": 401, "unauthorized": "authenticated-only"},
    {"family": "report settings", "method": "PATCH", "path": "/api/report-settings/{id}", "unauthenticated": 401, "unauthorized": "view_menu_options_reports"},
    {"family": "payroll", "method": "GET", "path": "/api/reports/payrolls/{id}", "unauthenticated": 401, "unauthorized": "view_menu_reports_payrolls"},
    {"family": "payroll", "method": "POST", "path": "/api/reports/payrolls", "unauthenticated": 401, "unauthorized": "edit_reports_payrolls"},
)


def audit_payload(permission_ids=None) -> dict:
    from .s03_policy import policy_payload
    s03 = policy_payload()
    dedicated = DEDICATED_PERMISSION_IDS | {domain[action] for domain in s03['domains'] for action in ('edit', 'delete')}
    available = set(permission_ids or ())
    return {
        "enforcement_verified": False,
        "verification_note": "Declarative inventory, not executable security certification. See permanent real-session review tests and review-progress.md for run evidence.",
        "s03_policy": s03,
        "families": [dict(item) for item in ROUTE_PERMISSION_AUDIT],
        "dedicated_permissions": sorted(dedicated),
        "missing_catalog_permissions": sorted(dedicated - available) if permission_ids is not None else [],
        "catalog_complete": permission_ids is None or not (dedicated - available),
        "authorization_matrix": [dict(item) for item in AUTHORIZATION_MATRIX],
    }