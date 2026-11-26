"""Phase 1 S01 regressions: real sessions, disposable in-memory data only."""
import unittest
import os

import bcrypt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Action, Permission, Role, User


class EmployeeAuthorizationReviewTests(unittest.TestCase):
    mysql = False

    def setUp(self):
        if self.mysql:
            from app.mysql_test_guard import verify_test_database
            url = os.environ['MYSQL_ADMIN_TEST_URL']
            verify_test_database(url, os.getenv('DATABASE_URL'))
            self.engine = create_engine(url)
        else:
            self.engine = create_engine('sqlite://', poolclass=StaticPool,
                                        connect_args={'check_same_thread': False})
            self.assertIsNone(self.engine.url.database)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.assertIsNone(self.db.scalar(select(User.id).limit(1)), 'Requires empty disposable fixture')
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
        self.db.rollback()
        if self.mysql:
            for table in reversed(Base.metadata.sorted_tables):
                self.db.execute(table.delete())
            self.db.commit()
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

    def test_role_and_credential_escalation_require_explicit_delegation(self):
        self.grant('user_edit', 'user_create')
        admin_role = Role(title='Security administrator', permissions=[Permission(
            id='view_menu_options_permissions', title='Security', module='options')])
        self.db.add(admin_role); self.db.commit()
        update = {'name': 'Target', 'surname': 'Staff', 'phone': '123',
                  'email': 'taken-over@example.test', 'post': 'Staff',
                  'role_id': admin_role.id, 'fired': False,
                  'change_password': True, 'password': 'changed-secret',
                  'password_confirmation': 'changed-secret'}
        before = self.snapshot()
        self.assertEqual(self.client.patch(self.path, headers=self.headers, json=update).status_code, 403)
        self.assertEqual(self.client.post('/api/employee-references', headers=self.headers, json={
            'name': 'New', 'surname': 'Admin', 'phone': '123', 'email': 'new-admin@example.test',
            'post': 'Staff', 'role_id': admin_role.id, 'password': 'new-secret',
            'password_confirmation': 'new-secret', 'fired': False}).status_code, 403)
        self.assertEqual(self.snapshot(), before)

    def test_delegated_editor_can_manage_equal_or_weaker_role_and_credentials(self):
        self.grant('user_edit', 'user_create', 'user_assign_role', 'user_reset_credentials')
        delegated = Role(title='Delegated staff', permissions=[self.db.get(Permission, 'user_edit')])
        self.db.add(delegated); self.db.commit()
        update = {'name': 'Target', 'surname': 'Staff', 'phone': '123',
                  'email': 'changed@example.test', 'post': 'Staff', 'role_id': delegated.id,
                  'fired': False, 'change_password': True, 'password': 'changed-secret',
                  'password_confirmation': 'changed-secret'}
        self.assertEqual(self.client.patch(self.path, headers=self.headers, json=update).status_code, 200)
        self.assertEqual(self.target.email, 'changed@example.test')
        self.assertTrue(bcrypt.checkpw(b'changed-secret', self.target.password.encode()))
        audit = self.db.scalar(select(Action).where(Action.item_id == self.target.id))
        self.assertEqual(audit.user_id, self.actor.id)
        self.assertIn('role_id', audit.comment)
        self.assertIn('password', audit.comment)
        self.assertNotIn('changed-secret', audit.comment)
        self.assertNotIn('changed@example.test', audit.comment)

    def test_stronger_non_admin_target_is_protected_even_with_delegation(self):
        self.grant('user_edit', 'user_delete', 'user_assign_role', 'user_reset_credentials',
                   'view_menu_references_users')
        stronger = Role(title='Accounting specialist', permissions=[Permission(
            id='edit_accounting_bills', title='Bills', module='accounting')])
        self.target.role = stronger
        self.db.commit()
        payload = {'name': 'Target', 'surname': 'Staff', 'phone': '123',
                   'email': self.target.email, 'post': 'Staff', 'role_id': stronger.id,
                   'fired': False}
        before = self.snapshot()
        for changes in ({'post': 'Changed'}, {'email': 'takeover@example.test'},
                        {'fired': True}, {'role_id': self.role.id},
                        {'change_password': True, 'password': 'new-secret',
                         'password_confirmation': 'new-secret'}):
            for _ in range(2):
                response = self.client.patch(self.path, headers=self.headers, json={**payload, **changes})
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.client.delete(self.path, headers=self.headers).status_code, 403)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.client.get(self.path).json()['can_edit'])

    def test_profile_editor_cannot_reset_credentials_or_fire_equal_target(self):
        self.grant('user_edit')
        self.target.role = self.role
        self.db.commit()
        payload = {'name': 'Target', 'surname': 'Staff', 'phone': '123',
                   'email': self.target.email, 'post': 'Staff', 'role_id': self.role.id,
                   'fired': False}
        before = self.snapshot()
        for changes in ({'email': 'takeover@example.test'}, {'fired': True},
                        {'change_password': True, 'password': 'new-secret',
                         'password_confirmation': 'new-secret'}):
            response = self.client.patch(self.path, headers=self.headers, json={**payload, **changes})
            self.assertEqual(response.status_code, 403, response.text)
            self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.client.patch(self.path, headers=self.headers,
                                          json={**payload, 'post': 'Changed'}).status_code, 200)

    def test_delegation_choices_creation_aliases_and_revocation(self):
        self.grant('user_create', 'user_edit', 'view_menu_references_users', 'user_assign_role')
        weak = Role(title='Explicit empty role')
        strong = Role(title='Not delegable', permissions=[Permission(
            id='edit_accounting_bills', title='Bills', module='accounting')])
        self.db.add_all([weak, strong]); self.db.commit()
        choices = self.client.get('/api/employee-references/form').json()
        self.assertTrue(choices['can_create'])
        self.assertEqual({row['id'] for row in choices['roles']}, {weak.id, self.role.id})
        payload = {'user_name': 'New', 'user_surname': 'Staff', 'user_phone': '123',
                   'user_email': 'new@example.test', 'user_post': 'Staff',
                   'user_role': weak.id, 'user_password': 'test-secret',
                   'user_password_confirmation': 'test-secret'}
        before = self.snapshot()
        self.assertEqual(self.client.post('/api/employee-references', headers=self.headers,
                                          json={**payload, 'user_role': strong.id}).status_code, 403)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.client.post('/api/employee-references', headers=self.headers,
                                          json={**payload, 'user_role': ''}).status_code, 422)
        self.assertEqual(self.snapshot(), before)
        response = self.client.post('/api/employee-references', headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        created = self.db.get(User, response.json()['id'])
        self.assertEqual(created.role_id, weak.id)
        audit = self.db.scalar(select(Action).where(Action.item_id == created.id))
        self.assertIsNotNone(audit)
        self.assertNotIn('test-secret', audit.comment)
        self.role.permissions.remove(self.db.get(Permission, 'user_assign_role'))
        self.db.commit()
        before = self.snapshot()
        self.assertFalse(self.client.get('/api/employee-references/form').json()['can_create'])
        self.assertEqual(self.client.post('/api/employee-references', headers=self.headers,
                                          json={**payload, 'user_email': 'another@example.test'}).status_code, 403)
        self.assertEqual(self.snapshot(), before)

    def test_security_admin_still_requires_sensitive_action_grants(self):
        self.grant('user_edit', 'view_menu_options_permissions')
        self.target.role = self.role
        self.db.commit()
        payload = {'name': 'Target', 'surname': 'Staff', 'phone': '123',
                   'email': self.target.email, 'post': 'Staff', 'role_id': self.role.id,
                   'fired': False, 'change_password': True, 'password': 'new-secret',
                   'password_confirmation': 'new-secret'}
        before = self.snapshot()
        self.assertEqual(self.client.patch(self.path, headers=self.headers, json=payload).status_code, 403)
        self.assertEqual(self.snapshot(), before)
        self.grant('user_reset_credentials')
        self.assertEqual(self.client.patch(self.path, headers=self.headers, json=payload).status_code, 200)

    def test_admin_can_disable_peer_but_cannot_revoke_last_admin_grant(self):
        self.grant('user_delete', 'user_edit', 'view_menu_options_permissions')
        self.target.role = self.role
        self.db.commit()
        path = self.path
        payload = {'name': 'Target', 'surname': 'Staff', 'phone': '123',
                   'email': self.target.email, 'post': 'Staff', 'role_id': self.role.id,
                   'fired': True}
        self.assertEqual(self.client.patch(path, headers=self.headers, json=payload).status_code, 200)
        self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
        before = self.snapshot()
        self.assertEqual(self.client.post('/api/options/permissions', headers=self.headers,
                         json={'permissions': {'view_menu_options_permissions': []}}).status_code, 409)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.client.post('/api/options/permissions', headers=self.headers,
                         json={'permissions': {'view_menu_options_permissions': [self.role.id]}}).status_code, 200)

    def test_last_admin_demotion_by_cli_and_repeated_matrix_revocation_are_denied(self):
        from app.assign_role import assign_role
        self.grant('user_delete', 'user_edit', 'view_menu_options_permissions')
        staff = Role(title='Ordinary staff')
        self.db.add(staff); self.db.commit()
        before = self.snapshot()
        for _ in range(2):
            with self.assertRaises(ValueError):
                assign_role(self.db, f'id:{self.actor.id}', f'id:{staff.id}', True)
            self.assertEqual(self.client.post('/api/options/permissions', headers=self.headers,
                             json={'permissions': {'view_menu_options_permissions': []}}).status_code, 409)
        self.assertEqual(self.snapshot(), before)

@unittest.skipUnless(os.getenv('MYSQL_ADMIN_TEST_URL'), 'Dedicated empty MySQL schema required')
class MySQLEmployeeAuthorizationReviewTests(EmployeeAuthorizationReviewTests):
    mysql = True
