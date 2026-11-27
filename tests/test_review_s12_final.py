"""S12 private audit and generic auth responses with disposable fixtures."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import security_audit
from app.models import User, PasswordReset
from tests import test_review_employee_authorization as employee
from tests import test_authentication as auth


class AuditTests(unittest.TestCase):
    mysql = False
    setUp = employee.EmployeeAuthorizationReviewTests.setUp
    tearDown = employee.EmployeeAuthorizationReviewTests.tearDown
    grant = employee.EmployeeAuthorizationReviewTests.grant
    snapshot = employee.EmployeeAuthorizationReviewTests.snapshot

    def test_denied_and_successful_delete_attributable_and_secret_free(self):
        self.grant('view_menu_references_users')
        before = self.snapshot()
        self.assertEqual(self.client.delete(self.path, headers=self.headers).status_code, 403)
        self.assertEqual(before, self.snapshot())
        self.grant('user_delete')
        self.assertEqual(self.client.delete(self.path, headers=self.headers).status_code, 200)
        events = security_audit.view(security_audit.destination(self.db))
        self.assertEqual([row['outcome'] for row in events[:2]], ['success', 'denied'])
        self.assertTrue(all(row['actor'] == self.actor.id for row in events))
        self.assertTrue(all(row['target'] == self.target.id for row in events))
        content = str(events)
        for secret in (self.actor.email, self.actor.password, 'test-secret', self.target.email):
            self.assertNotIn(secret, content)
        self.assertIn('denied_or_error', security_audit.view(security_audit.destination(self.db), alerts=True))

    def test_intent_failure_prevents_mutation(self):
        self.grant('view_menu_references_users', 'user_delete')
        before = self.snapshot()
        with patch('app.security_audit.begin', side_effect=OSError('secret-not-logged')):
            self.assertEqual(self.client.delete(self.path, headers=self.headers).status_code, 503)
        self.assertEqual(before, self.snapshot())

    def test_outcome_failure_leaves_intent_and_requires_reconciliation(self):
        self.grant('view_menu_references_users', 'user_delete')
        with patch('app.security_audit.finish', side_effect=OSError('hidden')):
            self.assertEqual(self.client.delete(self.path, headers=self.headers).status_code, 503)
        events = security_audit.view(security_audit.destination(self.db))
        self.assertEqual(events[0]['outcome'], 'intent')
        self.db.refresh(self.target)
        self.assertIsNotNone(self.target.deleted_at)

    def test_guest_privileged_denial_is_recorded(self):
        self.client.cookies.clear()
        self.headers = {'X-CSRF-Token': self.client.get('/api/csrf-token').json()['token']}
        self.assertEqual(self.client.delete(self.path, headers=self.headers).status_code, 401)
        event = security_audit.view(security_audit.destination(self.db))[0]
        self.assertIsNone(event['actor'])
        self.assertEqual(event['outcome'], 'denied')

    def test_matrix_and_operator_changes_are_audited(self):
        self.grant('view_menu_options_permissions')
        response = self.client.post('/api/options/permissions', headers=self.headers, json={'permissions': {}})
        self.assertEqual(response.status_code, 200)
        from app.assign_role import assign_role
        result = assign_role(self.db, f'id:{self.target.id}', f'id:{self.role.id}', True)
        self.assertTrue(result['applied'])
        rows = security_audit.view(security_audit.destination(self.db))
        self.assertEqual(rows[0]['action'], 'assign_role.assign_role')
        self.assertEqual(rows[0]['outcome'], 'success')
        self.assertEqual(rows[1]['action'], 'permissions.update_matrix')
        self.assertIn('grants', rows[1]['before_state'])

    def test_bulk_delete_alert_and_readonly_view(self):
        path = security_audit.destination(self.db)
        for _ in range(5):
            identity = security_audit.begin(path, self.actor.id, 'reference_users.delete', self.target.id, {})
            security_audit.finish(path, identity, 'denied', {})
        self.assertTrue(security_audit.view(path, alerts=True)['bulk_delete_alert'])


class GenericResponseTests(unittest.TestCase):
    setUp = auth.AuthenticationTests.setUp
    tearDown = auth.AuthenticationTests.tearDown

    def test_existing_new_registration_same_response_and_no_session(self):
        headers = {'X-CSRF-Token': self.client.get('/api/csrf-token').json()['token']}
        with patch('app.main.PUBLIC_REGISTRATION_ENABLED', True):
            values = []
            for email in (self.user.email, 'new@example.test'):
                response = self.client.post('/api/auth/register', headers=headers, data={'name': 'New', 'email': email,
                    'password': 'secret123', 'password_confirmation': 'secret123'}, follow_redirects=False)
                values.append((response.status_code, response.json()))
                self.assertFalse(self.client.get('/api/session').json()['authenticated'])
        self.assertEqual(values[0], values[1])

    def test_delivery_failure_and_unknown_account_have_identical_response(self):
        headers = {'X-CSRF-Token': self.client.get('/api/csrf-token').json()['token']}
        from datetime import datetime
        self.db.add(PasswordReset(email=self.user.email, token='preserved', created_at=datetime(2026, 1, 1)))
        self.db.commit()
        with patch('app.main.RESET_MAIL_MODE', 'smtp'), patch('app.main.deliver_reset_mail', side_effect=OSError('mail-secret')):
            known = self.client.post('/api/password/email', headers=headers, data={'email': self.user.email})
            unknown = self.client.post('/api/password/email', headers=headers, data={'email': 'unknown@example.test'})
        self.assertEqual((known.status_code, known.json()), (unknown.status_code, unknown.json()))
        self.assertEqual(known.status_code, 200)
        self.assertEqual(self.db.get(PasswordReset, self.user.email).token, 'preserved')