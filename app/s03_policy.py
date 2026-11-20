"""Declared S03 policy; executable regression coverage is separate from this DTO."""
REFERENCE_MODULES = frozenset({
    'app.reference_customers', 'app.reference_inventory', 'app.reference_printers',
    'app.printer_children', 'app.reference_afterprints', 'app.reference_compiles',
    'app.reference_works', 'app.reference_dictionaries', 'app.accounting_payers',
})
KINDS = {'app.reference_works': ('prepresses', 'redactions'),
         'app.reference_dictionaries': ('paper-type', 'paper-format', 'measures', 'customer-group'),
         'app.reference_inventory': ('paper', 'materials'),
         'app.printer_children': ('fields', 'processes', 'stages')}


def in_scope(route):
    return route.endpoint.__module__ in REFERENCE_MODULES or route.path.startswith(('/api/orders', '/orders'))


def domain_policy(module, path, kind=None):
    if path.startswith(('/api/orders', '/orders')):
        return ('view_menu_orders',), 'edit_orders', 'delete_orders'
    if module == 'app.accounting_payers':
        return ('view_menu_accounting_payers',), 'edit_accounting_payers', 'delete_accounting_payers'
    if module == 'app.reference_dictionaries':
        reads = {'paper-type': ('view_menu_options_paper_type', 'view_menu_references_paper_type'),
                 'paper-format': ('view_menu_options_paper_format',),
                 'measures': ('view_menu_options_measures',),
                 'customer-group': ('view_menu_options_customer_group',)}
        suffix = kind.replace('-', '_')
        return reads[kind], f'edit_dictionary_{suffix}', f'delete_dictionary_{suffix}'
    if module == 'app.reference_customers':
        kind = 'customers'
    elif module in {'app.printer_children', 'app.reference_printers'}:
        kind = 'printers'
    elif module == 'app.reference_afterprints':
        kind = 'afterprints'
    elif module == 'app.reference_compiles':
        kind = 'compiles'
    elif module == 'app.reference_inventory' and kind is None:
        kind = path.split('/')[3]
    return (f'view_menu_references_{kind}',), f'edit_reference_{kind}', f'delete_reference_{kind}'


def declared_routes(app):
    from fastapi.routing import APIRoute
    return sorted((method, route.path, route.endpoint.__module__)
                  for route in app.routes if isinstance(route, APIRoute) and in_scope(route)
                  for method in route.methods)


def policy_payload():
    domains = []
    for module, kinds in (
        ('app.main', (None,)), ('app.accounting_payers', (None,)),
        ('app.reference_customers', (None,)), ('app.reference_printers', (None,)),
        ('app.reference_afterprints', (None,)), ('app.reference_compiles', (None,)),
        ('app.reference_inventory', ('paper', 'materials')),
        ('app.reference_dictionaries', KINDS['app.reference_dictionaries']),
        ('app.reference_works', KINDS['app.reference_works']),
    ):
        for kind in kinds:
            reads, edit, delete = domain_policy(module, '/api/orders' if module == 'app.main' else '', kind)
            domains.append({'domain': edit.removeprefix('edit_'), 'read_any': list(reads),
                            'edit': edit, 'delete': delete,
                            'restore_additionally': 'restore_trashed',
                            'permanent_delete_additionally': 'delete_trashed'})
    return {'status': 'declared_policy_not_release_approval', 'domains': domains,
            'scope': 'Shared-team access; active parents and matching child ownership required.',
            'grant_rollout': 'New action capabilities are never assigned automatically; security administrator must approve role grants.'}