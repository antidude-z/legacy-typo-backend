"""Bill and bill-owned payment lifecycle policy; no implicit role grants."""
from fastapi import HTTPException


def accounting_capabilities(user):
    readable = user.has_permission('view_accounting_bills')
    deletable = readable and user.has_permission('delete_accounting_bills')
    return {'can_edit': user.has_permission('edit_accounting_bills'),
            'can_delete': deletable,
            'can_restore': deletable and user.has_permission('restore_trashed'),
            'can_delete_trashed': deletable and user.has_permission('delete_trashed')}


def require_accounting_delete(user, lifecycle=None):
    required = ['view_accounting_bills', 'delete_accounting_bills']
    if lifecycle:
        required.append(lifecycle)
    if any(not user.has_permission(permission) for permission in required):
        raise HTTPException(403, 'accounting_delete_permission_required')