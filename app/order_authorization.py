"""S03 action boundary for the complete Orders route family."""
from fastapi import HTTPException
from .models import Blank, Order, OrderCompile, OrderOtherWork, OrderPrepress, OrderRedaction


ORDER_CAPABILITIES = (
    ('edit_orders', 'Create, edit, copy and recalculate orders'),
    ('delete_orders', 'Delete and restore orders'),
)


def require_order_action(request, user):
    path = request.url.path.rstrip('/')
    if not (path == '/orders' or path.startswith('/orders/') or
            path == '/api/orders' or path.startswith('/api/orders/')):
        return
    required = ['view_menu_orders']
    if request.method not in {'GET', 'HEAD', 'OPTIONS'} and not path.endswith('/filter'):
        lifecycle = request.method == 'DELETE' or path.endswith(('/restore', '/permanent'))
        required.append('delete_orders' if lifecycle else 'edit_orders')
        if path.endswith('/restore'):
            required.append('restore_trashed')
        if path.endswith('/permanent'):
            required.append('delete_trashed')
    if any(not user.has_permission(permission) for permission in required):
        raise HTTPException(status_code=403, detail='order_permission_required')


def require_order_resource(request, user, db):
    """Apply parent, ownership and trash scope before any Orders handler runs."""
    path = request.url.path.rstrip('/')
    if not path.startswith(('/api/orders/', '/orders/')):
        return
    params = request.path_params
    identity = params.get('order_id')
    if identity is None:
        return  # Collection and type/selector routes have no parent resource.
    try:
        identity = int(identity)
    except (TypeError, ValueError):
        raise HTTPException(422, 'invalid_order_id')
    order = db.get(Order, identity)
    if order is None:
        raise HTTPException(404, 'not_found')
    child_kind = params.get('operation')
    if 'blank_id' in params or child_kind == 'blanks':
        child_kind = 'blanks'
    # operations/history are fixed routes rather than dynamic operation names.
    suffix = '/' + '/'.join(path.split('/orders/', 1)[1].split('/')[1:])
    if suffix == '/':
        suffix = ''
    is_child = child_kind in {'blanks', 'prepresses', 'redactions', 'compiles', 'others'} or suffix in {'/blanks', '/operations'}
    unsafe = request.method not in {'GET', 'HEAD', 'OPTIONS'}
    lifecycle = request.method == 'DELETE' or suffix == '/restore'
    if order.deleted_at is not None:
        if is_child or (unsafe and not lifecycle):
            raise HTTPException(404, 'not_found')
        if not unsafe and not user.has_permission('view_trashed'):
            raise HTTPException(404, 'not_found')
        if request.method == 'DELETE' and not user.has_permission('delete_trashed'):
            raise HTTPException(403, 'order_permission_required')
    models = {'blanks': Blank, 'prepresses': OrderPrepress, 'redactions': OrderRedaction,
              'compiles': OrderCompile, 'others': OrderOtherWork}
    child_id = params.get('blank_id', params.get('item_id'))
    if child_kind not in models or child_id is None:
        return
    try:
        child_id = int(child_id)
    except (TypeError, ValueError):
        raise HTTPException(422, 'invalid_child_id')
    child = db.get(models[child_kind], child_id)
    if child is None or child.order_id != order.id:
        raise HTTPException(404, 'not_found')
    if child.deleted_at is not None:
        if request.method == 'DELETE':
            if not user.has_permission('delete_trashed'):
                raise HTTPException(403, 'order_permission_required')
        elif unsafe:
            if not path.endswith('/restore'):
                raise HTTPException(404, 'not_found')
        elif not user.has_permission('view_trashed'):
            raise HTTPException(404, 'not_found')
    elif path.endswith('/permanent'):
        raise HTTPException(409, 'delete_before_permanent_delete')


def order_capabilities(user, order=None):
    readable = user.has_permission('view_menu_orders')
    active = order is None or order.deleted_at is None
    can_delete = readable and user.has_permission('delete_orders')
    return {'edit': readable and active and user.has_permission('edit_orders'),
            'delete': can_delete and (active or user.has_permission('delete_trashed')),
            'restore': can_delete and user.has_permission('restore_trashed'),
            'permanent_delete': can_delete and user.has_permission('delete_trashed')}