"""Shared bill/order read scope for detail and document consumers."""
from fastapi import HTTPException

from .models import Bill, Order


READ_PERMISSIONS = {Bill: 'view_accounting_bills', Order: 'view_menu_orders'}


def require_resource_read(user, model):
    permission = READ_PERMISSIONS.get(model)
    if permission is None or not user.has_permission(permission):
        raise HTTPException(403, 'resource_read_permission_required')


def readable_resource(db, user, model, identity, *, active_only=False):
    require_resource_read(user, model)
    item = db.get(model, identity)
    if item is None or (item.deleted_at is not None and
                        (active_only or not user.has_permission('view_trashed'))):
        raise HTTPException(404, 'not_found')
    return item