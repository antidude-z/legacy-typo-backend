"""Explicit admission state for mocked-authentication CRUD fixtures only."""
from app.models import Permission, Role


def admit_mock_staff(user):
    user.role = Role(title='Synthetic admitted staff', permissions=[
        Permission(id='view_menu_orders', title='Orders', module='orders')])
    return user