"""S03 action boundary for the complete Orders route family."""
from fastapi import HTTPException


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