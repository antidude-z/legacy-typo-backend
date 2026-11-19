"""Real endpoint authentication and authorization on isolated SQLite/MySQL data."""
import os
import tempfile
import unittest
from datetime import date
from email import policy
from email.parser import BytesParser
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import bcrypt
from itsdangerous import TimestampSigner
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Bill, Payment, Permission, Role, User
from app.mysql_test_guard import verify_test_database
from app.config import SESSION_COOKIE, SESSION_SECRET, SESSION_MINUTES


class SessionSecurityScenarios:
    def setUp(self):
        if self.mysql:
            url = os.environ['MYSQL_TEST_URL']
            verify_test_database(url, os.getenv('DATABASE_URL'))
            self.engine = create_engine(url)
        else:
            self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
            Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.previous = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = lambda: self.db
        self.role = Role(title='QA ' + uuid4().hex[:12])
        self.user = User(name='QA sessions', surname='Isolated', phone='', post='',
                         email=f'{uuid4().hex}@example.test', role=self.role,
                         password=bcrypt.hashpw(b'qa-secret-123', bcrypt.gensalt()).decode())
        self.db.add(self.user)
        self.db.commit()
        # Do not enter TestClient's lifespan: startup would use the app's global DB.
        self.client = TestClient(app, follow_redirects=False)
        self.headers = {'X-CSRF-Token': self.client.get('/api/csrf-token').json()['token']}
        self.bills = []
        self.payments = []

    def tearDown(self):
        self.client.close()
        self.db.rollback()
        for row in self.payments:
            existing = self.db.get(Payment, row.id)
            if existing: self.db.delete(existing)
        self.db.flush()
        for row in self.bills:
            self.db.delete(row)
        self.role.permissions.clear()
        self.db.delete(self.user)
        self.db.flush()
        self.db.delete(self.role)
        self.db.commit()
        self.db.close()
        self.engine.dispose()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.previous)

    def grant(self, *names):
        for name in names:
            permission = self.db.get(Permission, name)
            if permission is None:
                permission = Permission(id=name, title=name, module='QA')
                self.db.add(permission)
            if permission not in self.role.permissions:
                self.role.permissions.append(permission)
        self.db.commit()

    def login(self, remember=False):
        response = self.client.post('/api/auth/login', headers=self.headers,
                                    data={'email': self.user.email, 'password': 'qa-secret-123', 'remember': str(remember).lower()})
        self.assertEqual(response.status_code, 303, response.text)
        self.assertTrue(self.client.get('/api/session').json()['authenticated'])
        return response

    def test_real_roles_lifecycle_and_cross_parent_payment_ownership(self):
        self.assertEqual(self.client.get('/api/accounting/bills').status_code, 401)
        self.login()
        self.assertEqual(self.client.get('/api/accounting/bills').status_code, 403)
        self.grant('view_accounting_bills')
        self.assertEqual(self.client.get('/api/accounting/bills').status_code, 200)
        self.assertEqual(self.client.post('/api/accounting/bills', headers=self.headers, json={}).status_code, 403)
        self.grant('edit_accounting_bills')
        self.bills = [Bill(number='QA session A', amount=10, currency='RUB'), Bill(number='QA session B', amount=20, currency='RUB')]
        self.db.add_all(self.bills); self.db.commit()
        first, other = self.bills
        response = self.client.post(f'/api/accounting/bills/{first.id}/payments', headers=self.headers,
                                    json={'payment_date': date.today().isoformat(), 'payment_amount': '1.25'})
        self.assertEqual(response.status_code, 200, response.text)
        payment = self.db.get(Payment, response.json()['id']); self.payments.append(payment)
        path = f'/api/accounting/bills/{first.id}/payments/{payment.id}'
        wrong = f'/api/accounting/bills/{other.id}/payments/{payment.id}'
        for method, suffix, payload in [('GET', '', None), ('PATCH', '', {'payment_amount': '2', 'payment_date': '2024-01-01'}), ('DELETE', '', None)]:
            response = self.client.request(method, wrong + suffix, headers=self.headers, json=payload)
            self.assertEqual(response.status_code, 404, (method, response.text))
        self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.grant('view_trashed')
        self.assertTrue(self.client.get(path).json()['item']['deleted'])
        self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 403)
        self.assertEqual(self.client.post(path + '/restore', headers=self.headers).status_code, 403)
        self.grant('restore_trashed')
        self.assertEqual(self.client.post(wrong + '/restore', headers=self.headers).status_code, 404)
        self.assertEqual(self.client.post(path + '/restore', headers=self.headers).status_code, 200)
        self.assertFalse(self.client.get(path).json()['item']['deleted'])
        self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
        self.grant('delete_trashed')
        self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_real_csrf_remember_cookie_and_logout_revocation(self):
        response = self.login(remember=True)
        for header in response.headers.get_list('set-cookie'):
            if header.startswith(('typography_remember=', 'laravel_session=')):
                self.assertIn('httponly', header.lower())
                self.assertIn('samesite=lax', header.lower())
        remembered = self.client.cookies.get('typography_remember')
        self.assertEqual(self.client.post('/api/auth/logout').status_code, 419)
        self.assertEqual(self.client.post('/api/auth/logout', headers={'X-CSRF-Token': 'invalid'}).status_code, 419)
        self.client.cookies.clear()
        self.client.cookies.set('typography_remember', remembered)
        self.assertTrue(self.client.get('/api/session').json()['authenticated'])
        self.headers = {'X-CSRF-Token': self.client.get('/api/csrf-token').json()['token']}
        self.assertEqual(self.client.post('/api/auth/logout', headers=self.headers).status_code, 303)
        self.client.cookies.clear()
        self.client.cookies.set('typography_remember', remembered)
        self.assertFalse(self.client.get('/api/session').json()['authenticated'])

    def test_expired_tampered_sessions_and_fired_account_are_rejected(self):
        self.login()
        cookie = self.client.cookies.get(SESSION_COOKIE)
        signer = TimestampSigner(SESSION_SECRET)
        payload = signer.unsign(cookie)
        old_time = signer.get_timestamp() - SESSION_MINUTES * 60 - 10
        with patch.object(TimestampSigner, 'get_timestamp', return_value=old_time):
            expired = signer.sign(payload).decode()
        self.client.cookies.clear(); self.client.cookies.set(SESSION_COOKIE, expired)
        self.assertFalse(self.client.get('/api/session').json()['authenticated'])
        self.client.cookies.clear(); self.client.cookies.set(SESSION_COOKIE, cookie + 'tampered')
        self.assertFalse(self.client.get('/api/session').json()['authenticated'])
        self.client.cookies.clear(); self.client.cookies.set(SESSION_COOKIE, cookie)
        self.user.fired = 1; self.db.commit()
        self.assertFalse(self.client.get('/api/session').json()['authenticated'])

    def test_real_reset_mail_invalidates_existing_session_and_remember_token(self):
        self.login(remember=True)
        remembered = self.client.cookies.get('typography_remember')
        requester = TestClient(app, follow_redirects=False)
        self.addCleanup(requester.close)
        with tempfile.TemporaryDirectory() as directory:
            token_header = {'X-CSRF-Token': requester.get('/api/csrf-token').json()['token']}
            # Only delivery configuration is overridden; authentication is real.
            with patch('app.main.RESET_MAIL_MODE', 'file'), patch('app.main.RESET_MAIL_DIR', Path(directory)):
                response = requester.post('/api/password/email', headers=token_header, data={'email': self.user.email})
            self.assertEqual(response.status_code, 200, response.text)
            mail = BytesParser(policy=policy.default).parsebytes(next(Path(directory).iterdir()).read_bytes())
            token = mail.get_content().split('/password/reset/', 1)[1].strip()
            payload = {'email': self.user.email, 'token': token, 'password': 'new-qa-secret', 'password_confirmation': 'new-qa-secret'}
            self.assertEqual(requester.post('/api/password/reset', headers=token_header, data=payload).status_code, 303)
            self.assertEqual(requester.post('/api/password/reset', headers=token_header, data=payload).status_code, 422)
        self.assertFalse(self.client.get('/api/session').json()['authenticated'])
        self.client.cookies.clear(); self.client.cookies.set('typography_remember', remembered)
        self.assertFalse(self.client.get('/api/session').json()['authenticated'])


class SQLiteSessionSecurityTests(SessionSecurityScenarios, unittest.TestCase):
    mysql = False


@unittest.skipUnless(os.getenv('MYSQL_TEST_URL'), 'MYSQL_TEST_URL not configured')
class MySQLSessionSecurityTests(SessionSecurityScenarios, unittest.TestCase):
    mysql = True