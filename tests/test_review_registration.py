"""S02: actual sessions and valid CSRF, disposable SQLite only."""
from unittest.mock import patch
import unittest
import re
from fastapi.routing import APIRoute
from sqlalchemy import select
from app.main import app
from app.models import Permission, Role
from tests import test_authentication


class RegistrationReviewTests(unittest.TestCase):
    setUp = test_authentication.AuthenticationTests.setUp
    tearDown = test_authentication.AuthenticationTests.tearDown
    # Reuse isolation setup, not the parent's unrelated test cases.
    def test_registration_disabled_aliases_preserve_data(self):
        headers = {'X-CSRF-Token': self.client.get('/api/csrf-token').json()['token']}
        before = self.snapshot()
        for path in ('/auth/register', '/api/auth/register'):
            response = self.client.post(path, headers=headers, data={
                'name': 'Pending', 'email': 'pending@example.test',
                'password': 'secret123', 'password_confirmation': 'secret123'})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(before, self.snapshot())

    def snapshot(self):
        from app.db import Base
        return {table.name: [tuple(row) for row in self.db.execute(select(table))]
                for table in Base.metadata.sorted_tables}

    def test_pending_roleless_and_empty_role_all_business_routes(self):
        self.client.post('/api/auth/login', data={'email': self.user.email, 'password': self.password})
        headers = {'X-CSRF-Token': self.client.get('/api/csrf-token').json()['token']}
        empty = Role(title='No approval')
        self.db.add(empty); self.db.commit()
        for role in (None, empty):
            self.user.role = role; self.db.commit()
            self.assertFalse(self.client.get('/api/session').json()['business_access'])
            before = self.snapshot()
            for route in app.routes:
                if not isinstance(route, APIRoute) or route.path in {'/', '/health', '/api/health', '/session', '/api/session', '/api/csrf-token'} or route.path.startswith(('/auth/', '/api/auth/', '/password/', '/api/password/')):
                    continue
                path = re.sub(r'\{[^}]+\}', '1', route.path)
                for method in route.methods - {'HEAD', 'OPTIONS'}:
                    response = self.client.request(method, path, headers=headers, json={})
                    self.assertEqual(response.status_code, 403, (method, path, response.text))
            self.assertEqual(before, self.snapshot())
        permission = Permission(id='view_menu_orders', title='Orders', module='orders')
        empty.permissions.append(permission); self.db.commit()
        self.assertTrue(self.client.get('/api/session').json()['business_access'])
        self.assertEqual(self.client.get('/api/orders').status_code, 200)

    def test_guest_business_routes_and_inventory_are_read_only(self):
        from app.audit_pending_accounts import inventory
        headers = {'X-CSRF-Token': self.client.get('/api/csrf-token').json()['token']}
        before = self.snapshot()
        for route in app.routes:
            if not isinstance(route, APIRoute) or route.path in {'/', '/health', '/api/health', '/session', '/api/session', '/api/csrf-token'} or route.path.startswith(('/auth/', '/api/auth/', '/password/', '/api/password/')):
                continue
            path = re.sub(r'\{[^}]+\}', '1', route.path)
            for method in route.methods - {'HEAD', 'OPTIONS'}:
                response = self.client.request(method, path, headers=headers, json={})
                self.assertEqual(response.status_code, 401, (method, path, response.text))
        self.assertEqual(inventory(self.db), [{'id': self.user.id, 'role_id': None,
            'fired': False, 'deleted': False, 'reason': 'missing_role'}])
        self.assertEqual(before, self.snapshot())

    def test_approval_revocation_and_logout(self):
        self.client.post('/api/auth/login', data={'email': self.user.email, 'password': self.password})
        role = Role(title='Approved', permissions=[Permission(id='view_menu_orders', title='Orders', module='orders')])
        self.user.role = role; self.db.commit()
        self.assertEqual(self.client.get('/api/orders').status_code, 200)
        role.permissions.clear(); self.db.commit()
        self.assertEqual(self.client.get('/api/orders').status_code, 403)
        headers = {'X-CSRF-Token': self.client.get('/api/csrf-token').json()['token']}
        self.assertEqual(self.client.post('/api/auth/logout', headers=headers, follow_redirects=False).status_code, 303)
        self.assertFalse(self.client.get('/api/session').json()['authenticated'])

    def test_opt_in_registration_is_pending(self):
        with patch('app.main.PUBLIC_REGISTRATION_ENABLED', True):
            response = self.client.post('/api/auth/register', data={
                'name': 'Pending', 'email': 'pending@example.test',
                'password': 'secret123', 'password_confirmation': 'secret123'}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertFalse(self.client.get('/api/session').json()['business_access'])
        self.assertEqual(self.client.get('/api/orders').status_code, 403)