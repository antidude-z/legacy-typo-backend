"""Reviewed S10 contracts. Inventory membership never implies enforcement proof.

The exact method/path/module baseline selects one of these policies. New
routes cannot acquire a policy merely by matching a prefix at audit time.
"""

POLICIES = {
    'orders': {
        'read': ['view_menu_orders'],
        'write': ['view_menu_orders', 'edit_orders'],
        'delete': ['view_menu_orders', 'delete_orders'],
        'conditions': 'GET add requires edit_orders; filter POST is read-only session state. Restore adds restore_trashed; permanent/repeated DELETE adds delete_trashed. Parent/trash/child ownership checked.',
        'evidence': ['tests.test_review_s03_matrix', 'tests.test_review_order_authorization'],
    },
    'pricing': {
        'read': ['staff_admission'], 'write': ['edit_price'], 'delete': ['delete_price'],
        'conditions': 'All reads require approved staff, not arbitrary authenticated accounts. Prices must belong to the requested priceable resource.',
        'evidence': ['tests.test_review_s10_authorization'],
    },
    'employees': {
        'read': ['view_menu_references_users'], 'write': ['user_create', 'user_edit'],
        'delete': ['user_delete'],
        'conditions': 'POST/form uses user_create; PATCH uses user_edit. Create/role assignment adds user_assign_role; credential changes add user_reset_credentials; firing adds user_delete. Target grants must be a subset unless security administrator. Self-disable/role and last-admin guards apply; restore/permanent add lifecycle grants.',
        'evidence': ['tests.test_review_employee_authorization', 'tests.test_review_s10_authorization'],
    },
    'permissions': {
        'read': ['view_menu_options_permissions'], 'write': ['view_menu_options_permissions'],
        'conditions': 'Serialized matrix writer preserves a surviving security administrator.',
        'evidence': ['tests.test_review_employee_authorization', 'tests.test_review_s10_authorization'],
    },
    'bills': {
        'read': ['view_accounting_bills'], 'write': ['view_accounting_bills', 'edit_accounting_bills'],
        'delete': ['view_accounting_bills', 'delete_accounting_bills'],
        'conditions': 'Filter POST uses read only; form requires edit. Restore/permanent adds lifecycle grants. Payment parent must be active and match.',
        'evidence': ['tests.test_review_accounting_deletion', 'tests.test_review_s10_authorization'],
    },
    'payroll': {
        'read': ['view_menu_reports_payrolls'], 'write': ['edit_reports_payrolls'],
        'conditions': 'Read includes export/form and never refreshes draft rows without edit. Editors may refresh drafts on detail/export GET; POST/PATCH require edit. Paid snapshot rules are separate functional findings.',
        'evidence': ['tests.test_review_s10_authorization'],
    },
    'report_settings': {
        'read': ['view_menu_options_reports'], 'write': ['view_menu_options_reports'],
        'conditions': 'Parameter identity must match report. Settings grants do not grant document access.',
        'evidence': ['tests.test_review_report_authorization', 'tests.test_review_s10_authorization'],
    },
    'documents': {
        'read_any_by_model': {'orders': ['view_menu_orders'], 'bills': ['view_accounting_bills']},
        'conditions': 'Both GET and POST generation are read operations. Resolve report model, then require active readable parent; bill order collection requires both grants. Transcript requires Orders read. Unknown models fail closed.',
        'evidence': ['tests.test_review_report_authorization'],
    },
    'main_options': {
        'read': ['view_menu_options_main'], 'conditions': 'Read-only options.',
        'evidence': ['tests.test_review_s10_authorization'],
    },
    'diagnostics': {
        'read': ['staff_admission'],
        'conditions': 'In PRODUCTION additionally requires view_menu_options_permissions. Nonproduction diagnostics intentionally admit approved staff. Deployment mode is S11.',
        'evidence': ['tests.test_review_s10_authorization'],
    },
}

for domain, suite in (
    ('customers', 'customer'), ('printers', 'printer'), ('afterprints', 'afterprint'),
    ('compiles', 'compile'), ('paper', 'inventory'), ('materials', 'inventory'),
    ('prepresses', 'work'), ('redactions', 'work'),
):
    POLICIES['reference_' + domain] = {
        'read': ['view_menu_references_' + domain],
        'write': ['view_menu_references_' + domain, 'edit_reference_' + domain],
        'delete': ['view_menu_references_' + domain, 'delete_reference_' + domain],
        'conditions': 'Restore/permanent add lifecycle grants; trash and matching active parent enforced. Work form-options requires edit.',
        'evidence': ['tests.test_review_s03_matrix', 'tests.test_review_' + suite + '_authorization'],
    }

POLICIES['payers'] = {
    'read': ['view_menu_accounting_payers'],
    'write': ['view_menu_accounting_payers', 'edit_accounting_payers'],
    'delete': ['view_menu_accounting_payers', 'delete_accounting_payers'],
    'conditions': 'Restore/permanent add lifecycle grants; form requires edit.',
    'evidence': ['tests.test_review_s03_matrix', 'tests.test_review_payer_authorization'],
}

for kind, reads in (
    ('paper_type', ['view_menu_options_paper_type', 'view_menu_references_paper_type']),
    ('paper_format', ['view_menu_options_paper_format']),
    ('measures', ['view_menu_options_measures']),
    ('customer_group', ['view_menu_options_customer_group']),
):
    POLICIES['dictionary_' + kind] = {
        'read_any': reads, 'write': ['edit_dictionary_' + kind],
        'delete': ['delete_dictionary_' + kind],
        'conditions': 'Write/delete also requires one read grant; restore/permanent adds lifecycle grants.',
        'evidence': ['tests.test_review_s03_matrix', 'tests.test_review_dictionary_authorization'],
    }