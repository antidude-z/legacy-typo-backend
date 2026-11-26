"""Owned limiter files and disposable SQLite only; actual auth and CSRF."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.auth_abuse import reserve, WINDOW, POLICIES
from app.models import PasswordReset, User
from tests import test_authentication as auth


class BudgetTests(unittest.TestCase):
    def test_atomic_account_ip_global_and_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'limits.db'
            with ThreadPoolExecutor(max_workers=8) as pool:
                accepted = list(pool.map(lambda i: reserve(path, 'reset-email', 'same@test', str(i), now=100), range(12)))
            self.assertEqual(sum(accepted), 3)
            self.assertTrue(reserve(path, 'reset-email', 'same@test', 'other', now=100 + WINDOW))
            self.assertNotIn(b'same@test', path.read_bytes())
            self.assertNotIn(b'other', path.read_bytes())
            for index in range(10):
                self.assertTrue(reserve(path, 'register', str(index), 'shared-ip', now=100))
            self.assertFalse(reserve(path, 'register', 'new', 'shared-ip', now=100))
            for index in range(90):
                self.assertTrue(reserve(path, 'register', str(index), str(index), now=100))
            self.assertFalse(reserve(path, 'register', 'last', 'last', now=100))


class AbuseEndpointTests(unittest.TestCase):
    tearDown = auth.AuthenticationTests.tearDown

    def setUp(self):
        auth.AuthenticationTests.setUp(self)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'budgets.db'
        self.addCleanup(patch.stopall)
        patch('app.auth_abuse.PRODUCTION', True).start()
        patch('app.auth_abuse.LOGIN_LIMIT_DB', self.path).start()
        self.headers = {'X-CSRF-Token': self.client.get('/api/csrf-token').json()['token']}

    def test_reset_aliases_share_account_budget_and_preserve_token_when_limited(self):
        with patch('app.main.RESET_MAIL_MODE', 'smtp'), patch('app.main.deliver_reset_mail') as mail:
            for index in range(3):
                path = '/password/email' if index % 2 else '/api/password/email'
                self.assertEqual(self.client.post(path, headers=self.headers, data={'email': self.user.email}).status_code, 200)
            before = self.db.get(PasswordReset, self.user.email).token
            response = self.client.post('/api/password/email', headers=self.headers, data={'email': self.user.email})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers['retry-after'], str(WINDOW))
            self.assertEqual(mail.call_count, 3)
            self.assertEqual(before, self.db.get(PasswordReset, self.user.email).token)

    def test_disabled_registration_is_bounded_without_creating_users(self):
        payload = {'name': 'Pending', 'email': 'pending@example.test', 'password': 'secret123', 'password_confirmation': 'secret123'}
        before = self.db.query(User).count()
        for _ in range(3):
            self.assertEqual(self.client.post('/api/auth/register', headers=self.headers, data=payload).status_code, 403)
        self.assertEqual(self.client.post('/auth/register', headers=self.headers, data=payload).status_code, 429)
        self.assertEqual(before, self.db.query(User).count())

    def test_store_failure_fails_closed_without_mail(self):
        with patch('app.auth_abuse.LOGIN_LIMIT_DB', self.path.parent), patch('app.main.deliver_reset_mail') as mail:
            response = self.client.post('/api/password/email', headers=self.headers, data={'email': self.user.email})
            self.assertEqual(response.status_code, 503)
            mail.assert_not_called()
            self.assertIsNone(self.db.get(PasswordReset, self.user.email))

    def test_oversized_fields_rejected_before_budget_mail_or_hash(self):
        with patch('app.main.deliver_reset_mail') as mail, patch('app.main.bcrypt.hashpw') as hashing:
            response = self.client.post('/api/auth/register', headers=self.headers, data={
                'name': 'Name', 'email': 'a' * 256, 'password': 'x' * 73, 'password_confirmation': 'x' * 73})
            self.assertEqual(response.status_code, 422)
            self.assertFalse(self.path.exists())
            mail.assert_not_called()
            hashing.assert_not_called()

    def test_streamed_and_declared_oversized_bodies_are_rejected_before_parsing(self):
        for content in (b'x' * 16385, iter([b'x' * 8192, b'x' * 8193])):
            response = self.client.post('/api/auth/login', headers=self.headers, content=content)
            self.assertEqual(response.status_code, 413)
        self.assertFalse(self.path.exists())

    def test_reset_consumption_aliases_share_budget_without_changing_password(self):
        before = self.user.password
        payload = {'email': self.user.email, 'token': 'invalid', 'password': 'secret123', 'password_confirmation': 'secret123'}
        for _ in range(10):
            self.assertEqual(self.client.post('/password/reset', headers=self.headers, data=payload).status_code, 422)
        self.assertEqual(self.client.post('/api/password/reset', headers=self.headers, data=payload).status_code, 429)
        self.db.refresh(self.user)
        self.assertEqual(before, self.user.password)

    def test_login_budget_cannot_be_bypassed_by_switching_alias(self):
        with patch('app.auth_abuse.POLICIES', {**POLICIES, 'login': (2, 100, 1000)}):
            for _ in range(2):
                self.assertEqual(self.client.post('/api/auth/login', headers=self.headers, data={'email': self.user.email, 'password': 'wrong'}).status_code, 422)
            self.assertEqual(self.client.post('/auth/login', headers=self.headers, data={'email': self.user.email, 'password': self.password}).status_code, 429)
            self.assertFalse(self.client.get('/api/session').json()['authenticated'])

    def test_enabled_registration_cannot_create_after_budget_exhaustion(self):
        payload = {'name': 'Pending', 'email': 'pending@example.test', 'password': 'secret123', 'password_confirmation': 'secret123'}
        for _ in range(3):
            self.assertTrue(reserve(self.path, 'register', payload['email'], 'setup'))
        before = self.db.query(User).count()
        with patch('app.main.PUBLIC_REGISTRATION_ENABLED', True), patch('app.main.bcrypt.hashpw') as hashing:
            response = self.client.post('/api/auth/register', headers=self.headers, data=payload)
            self.assertEqual(response.status_code, 429)
            hashing.assert_not_called()
        self.assertEqual(before, self.db.query(User).count())