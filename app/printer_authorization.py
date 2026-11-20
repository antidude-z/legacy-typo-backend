"""Shared S03 policy for printer definitions and their production hierarchy."""
from fastapi import HTTPException


PRINTER_CAPABILITIES = (
    ('edit_reference_printers', 'Create and edit printer configuration'),
    ('delete_reference_printers', 'Delete and restore printer configuration'),
)


def require_printer_action(request, user):
    if user is None:
        raise HTTPException(401, 'Unauthorized')
    required = ['view_menu_references_printers']
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        lifecycle = request.method == 'DELETE' or request.url.path.endswith('/restore')
        required.append('delete_reference_printers' if lifecycle else 'edit_reference_printers')
    if any(not user.has_permission(permission) for permission in required):
        raise HTTPException(403, 'Printer permission required')
    return user


def printer_permissions(user):
    delete = user.has_permission('delete_reference_printers')
    return {'can_edit': user.has_permission('edit_reference_printers'),
            'can_delete': delete,
            'can_restore': delete and user.has_permission('restore_trashed'),
            'can_delete_trashed': delete and user.has_permission('delete_trashed')}