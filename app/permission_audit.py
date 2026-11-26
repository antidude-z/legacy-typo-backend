"""Permission coverage manifest for the migrated route families.

This is intentionally declarative.  Existing route handlers retain their
compatibility behavior; the manifest makes the authorization contract
reviewable and testable before production cutover.
"""

import re
import json
from pathlib import Path


PUBLIC_ROUTE_PATHS = frozenset({
    "/", "/health", "/api/health", "/session", "/api/session", "/api/csrf-token",
})

# Exact method/path exclusions, never an auth-prefix exemption for new routes.
EXCLUDED_ROUTES = {(method, path) for method, paths in (
    ('GET', PUBLIC_ROUTE_PATHS | {'/auth/users', '/api/auth/users'}),
    ('POST', {prefix + action for prefix in ('/auth/', '/api/auth/')
              for action in ('login', 'logout', 'register')} |
             {prefix + action for prefix in ('/password/', '/api/password/')
              for action in ('email', 'reset')}),
) for path in paths}


def _route_pattern_matches(pattern: str, path: str) -> bool:
    expression = re.escape(pattern).replace(r"\*", ".*")
    expression = re.sub(r"\\\{[^}]+\\\}", r"[^/]+", expression)
    return re.fullmatch(expression, path) is not None


def route_coverage(app) -> dict:
    """Classify registered routes; this is inventory evidence, not enforcement certification."""
    from fastapi.routing import APIRoute
    registered, excluded, unmatched, missing_admission = [], [], [], []
    from .main import require_staff_admission

    def has_admission(dependant):
        return dependant.call is require_staff_admission or any(
            has_admission(child) for child in dependant.dependencies)
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods):
            item = {"method": method, "path": route.path, "module": route.endpoint.__module__}
            if (method, route.path) in EXCLUDED_ROUTES:
                excluded.append(item)
                continue
            registered.append(item)
            if not has_admission(route.dependant):
                missing_admission.append(item)
            if not any(_route_pattern_matches(pattern, route.path)
                       for family in ROUTE_PERMISSION_AUDIT for pattern in family["paths"]):
                unmatched.append(item)
    key = lambda item: (item["path"], item["method"])
    reviewed = json.loads(Path(__file__).with_name('reviewed_routes.json').read_text(encoding='utf-8'))
    from .route_policies import POLICIES
    identity = lambda item: (item['method'], item['path'], item['module'])
    reviewed_keys = {identity(item) for item in reviewed}
    registered_keys = {identity(item) for item in registered}
    unreviewed = [item for item in registered if identity(item) not in reviewed_keys]
    missing = [item for item in reviewed if identity(item) not in registered_keys]
    invalid_policies = [item for item in reviewed if not item.get('policies') or
                        any(policy not in POLICIES for policy in item['policies'])]
    return {"registered": sorted(registered, key=key), "excluded": sorted(excluded, key=key),
            "unmatched": sorted(unmatched, key=key),
            "unreviewed": sorted(unreviewed, key=key), "missing": sorted(missing, key=key),
            "reviewed": reviewed, "policies": POLICIES, "invalid_policies": invalid_policies,
            "missing_admission": missing_admission,
            "complete": not (unmatched or unreviewed or missing or invalid_policies or missing_admission)}

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
        "read": "approved staff admission",
        "write": "edit_price",
        "lifecycle": ["delete_price"],
        "notes": "The migrated API deliberately enforces edit/delete permissions on writes.",
    },
    {
        "family": "accounting bills",
        "paths": ["/api/accounting/bills", "/api/accounting/bills/*"],
        "read": "view_accounting_bills",
        "write": "edit_accounting_bills",
        "lifecycle": ["restore_trashed", "delete_trashed"],
        "notes": "Bill/payment lifecycle requires view_accounting_bills AND delete_accounting_bills; restore/permanent deletion also require restore_trashed/delete_trashed. Payments require an active matching parent bill. Edit does not imply delete; grants are unchanged.",
    },
    {
        "family": "accounting payers",
        "paths": ["/api/accounting/payers", "/api/accounting/payers/*"],
        "read": "view_menu_accounting_payers",
        "write": "view_menu_accounting_payers AND edit_accounting_payers; delete requires delete_accounting_payers",
        "lifecycle": ["restore_trashed", "delete_trashed"],
        "notes": "Restore/permanent delete require domain-delete AND generic lifecycle grants.",
    },
    {
        "family": "references",
        "paths": ["/api/options/{kind}", "/api/options/{kind}/*", "/api/references/*", "/api/customer-references", "/api/customer-references/*", "/api/reference-works/*"],
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
        "notes": "Role changes require explicit delegation; credential changes require reset authority. Non-security administrators may only manage targets/assign roles whose grants are a subset of their own. Self-role changes are denied; lifecycle and last-admin checks still apply.",
    },
    {
        "family": "permissions administration",
        "paths": ["/api/options/permissions", "/api/options/permissions/audit"],
        "read": "view_menu_options_permissions",
        "write": "view_menu_options_permissions",
        "lifecycle": [],
        "notes": "Role matrix administration requires the permission-management capability.",
    },
    {
        "family": "reports",
        "paths": ["/api/reports/*", "/reports/*", "/api/report-settings", "/api/report-settings/*"],
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
        "family": "system and main settings",
        "paths": ["/api/system/*", "/api/options/main"],
        "read": "main options: view_menu_options_main; diagnostics: approved staff plus permission administration in PRODUCTION",
        "write": "read-only system/settings routes",
        "lifecycle": [],
        "notes": "Operational diagnostics and main options are explicitly classified.",
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
    "edit_price", "delete_price", "view_accounting_bills", "edit_accounting_bills", "delete_accounting_bills",
    "user_assign_role", "user_reset_credentials",
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
    {"family": "user administration", "method": "DELETE", "path": "/api/employee-references/{id}", "unauthenticated": 401, "unauthorized": "user_delete", "permanent_additionally": "delete_trashed"},
    {"family": "permissions administration", "method": "GET", "path": "/api/options/permissions", "unauthenticated": 401, "unauthorized": "view_menu_options_permissions"},
    {"family": "reports", "method": "GET", "path": "/api/reports/for/{model}/{id}", "unauthenticated": 401, "unauthorized": "domain read grant; see s03_policy.domains", "parent_read_by_model": {"bills": "view_accounting_bills", "orders": "view_menu_orders"}},
    {"family": "report settings", "method": "PATCH", "path": "/api/report-settings/{id}", "unauthenticated": 401, "unauthorized": "view_menu_options_reports"},
    {"family": "payroll", "method": "GET", "path": "/api/reports/payrolls/{id}", "unauthenticated": 401, "unauthorized": "view_menu_reports_payrolls"},
    {"family": "payroll", "method": "POST", "path": "/api/reports/payrolls", "unauthenticated": 401, "unauthorized": "edit_reports_payrolls"},
)


def audit_payload(permission_ids=None, app=None) -> dict:
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
        "route_coverage": route_coverage(app) if app is not None else None,
    }