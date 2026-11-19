"""Phase 1 S01 regressions: real sessions, disposable in-memory data only."""
import unittest

import bcrypt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Permission, Role, User


class EmployeeAuthorizationReviewTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool,
                                    connect_args={'check_same_thread': False})
        self.assertIsNone(self.engine.url.database)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.previous = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = lambda: self.db
        self.role = Role(title='Synthetic staff')
        self.actor = User(name='Actor', email='actor@example.test', role=self.role,
                          password=bcrypt.hashpw(b'test-secret', bcrypt.gensalt()).decode())
        self.target = User(name='Target', email='target@example.test', password='unused')
        self.db.add_all([self.actor, self.target]); self.db.commit()
        # No lifespan: startup must never initialize the configured working DB.
        self.client = TestClient(app, follow_redirects=False)
        self.headers = {'X-CSRF-Token': self.client.get('/api/csrf-token').json()['token']}
        response = self.client.post('/api/auth/login', headers=self.headers,
                                    data={'email': self.actor.email, 'password': 'test-secret'})
        self.assertEqual(response.status_code, 303)
        self.path = f'/api/employee-references/{self.target.id}'

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear(); app.dependency_overrides.update(self.previous)
        self.db.close(); self.engine.dispose()

    def grant(self, *names):
        for name in names:
            permission = self.db.get(Permission, name)
            if permission is None:
                permission = Permission(id=name, title=name, module='test')
            self.role.permissions.append(permission)
        self.db.commit()

    def snapshot(self):
        return {table.name: [tuple(row) for row in self.db.execute(select(table)).all()]
                for table in Base.metadata.sorted_tables}

    def test_roleless_and_reader_denials_preserve_every_table(self):
        self.actor.role = None; self.db.commit()
        before = self.snapshot()
        for method, path in [('GET', '/api/employee-references'), ('GET', self.path),
                             ('DELETE', self.path), ('POST', self.path + '/restore')]:
            self.assertEqual(self.client.request(method, path, headers=self.headers).status_code, 403)
        self.assertEqual(self.snapshot(), before)
        self.actor.role = self.role
        self.grant('view_menu_references_users')
        self.assertEqual(self.client.get(self.path).status_code, 200)
        self.assertFalse(self.client.get(self.path).json()['can_delete'])
        before = self.snapshot()
        self.assertEqual(self.client.delete(self.path, headers=self.headers).status_code, 403)
        self.assertEqual(self.snapshot(), before)

    def test_domain_and_lifecycle_grants_are_both_required(self):
        self.grant('restore_trashed', 'delete_trashed')
        before = self.snapshot()
        self.assertEqual(self.client.delete(self.path, headers=self.headers).status_code, 403)
        self.assertEqual(self.client.post(self.path + '/restore', headers=self.headers).status_code, 403)
        self.assertEqual(self.snapshot(), before)
        self.grant('user_delete')
        self.assertEqual(self.client.delete(self.path, headers=self.headers).status_code, 200)
        self.assertIsNotNone(self.target.deleted_at)
        self.assertEqual(self.client.post(self.path + '/restore', headers=self.headers).status_code, 200)
        self.assertIsNone(self.target.deleted_at)
        self.assertEqual(self.client.delete(self.path, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.delete(self.path, headers=self.headers).status_code, 200)
        self.assertIsNone(self.db.get(User, self.target.id))

    def test_self_delete_and_firing_are_rejected_without_changes(self):
        self.grant('user_delete', 'user_edit')
        path = f'/api/employee-references/{self.actor.id}'
        payload = {'name': 'Actor', 'surname': 'Staff', 'phone': '123',
                   'email': self.actor.email, 'post': 'Staff', 'role_id': self.role.id,
                   'fired': True}
        before = self.snapshot()
        self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 403)
        self.assertEqual(self.client.patch(path, headers=self.headers, json=payload).status_code, 403)
        self.assertEqual(self.snapshot(), before)
        payload['fired'] = False
        self.assertEqual(self.client.patch(path, headers=self.headers, json=payload).status_code, 200)

    def test_privileged_target_and_self_role_change_are_denied(self):
        self.grant('user_delete', 'user_edit')
        admin_role = Role(title='Security administrator', permissions=[Permission(
            id='view_menu_options_permissions', title='Security', module='options')])
        self.target.role = admin_role
        self.db.commit()
        payload = {'name': 'Target', 'surname': 'Staff', 'phone': '123',
                   'email': self.target.email, 'post': 'Staff', 'role_id': self.role.id,
                   'fired': False}
        before = self.snapshot()
        self.assertEqual(self.client.delete(self.path, headers=self.headers).status_code, 403)
        self.assertEqual(self.client.patch(self.path, headers=self.headers, json=payload).status_code, 403)
        own = {**payload, 'name': 'Actor', 'email': self.actor.email, 'role_id': admin_role.id}
        self.assertEqual(self.client.patch(f'/api/employee-references/{self.actor.id}',
                                           headers=self.headers, json=own).status_code, 403)
        self.assertEqual(self.snapshot(), before)

    def test_security_administrator_cannot_disable_or_revoke_security_admin(self):
        self.grant('user_delete', 'user_edit', 'view_menu_options_permissions')
        self.target.role = self.role
        self.db.commit()
        path = self.path
        payload = {'name': 'Target', 'surname': 'Staff', 'phone': '123',
                   'email': self.target.email, 'post': 'Staff', 'role_id': self.role.id,
                   'fired': True}
        before = self.snapshot()
        self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 409)
        self.assertEqual(self.client.patch(path, headers=self.headers, json=payload).status_code, 409)
        self.assertEqual(self.client.post('/api/options/permissions', headers=self.headers,
                         json={'permissions': {'view_menu_options_permissions': []}}).status_code, 409)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.client.post('/api/options/permissions', headers=self.headers,
                         json={'permissions': {'view_menu_options_permissions': [self.role.id]}}).status_code, 200)