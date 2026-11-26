"""S07 real cookies and sessions; all writes are in disposable fixtures."""
import unittest

import bcrypt
from fastapi.testclient import TestClient

from app.main import app
from app.models import Role, PasswordReset
from app.clock import utc_now
from app.config import SESSION_COOKIE, SESSION_SECRET
from itsdangerous import TimestampSigner
import base64
import json
from sqlalchemy import create_engine, text, inspect
from app.schema import migration_2026_11_26_01
from tests import test_review_employee_authorization as fixtures


class CredentialRevocationTests(unittest.TestCase):
    mysql = False
    setUp = fixtures.EmployeeAuthorizationReviewTests.setUp
    tearDown = fixtures.EmployeeAuthorizationReviewTests.tearDown
    grant = fixtures.EmployeeAuthorizationReviewTests.grant

    def test_existing_user_table_upgrade_preserves_all_old_columns(self):
        self.db.rollback()
        with self.engine.begin() as connection:
            if connection.dialect.name == 'mysql':
                mode=connection.scalar(text('SELECT @@SESSION.sql_mode'))
                connection.execute(text("SET SESSION sql_mode='NO_AUTO_VALUE_ON_ZERO'"))
                connection.execute(text("ALTER TABLE users ADD COLUMN created_at TIMESTAMP NOT NULL DEFAULT '0000-00-00 00:00:00'"))
                connection.execute(text('SET SESSION sql_mode=:mode'),{'mode':mode})
            old_columns=[c['name'] for c in inspect(connection).get_columns('users') if c['name'] != 'security_stamp']
            columns=','.join(old_columns)
            before=[tuple(r) for r in connection.execute(text('SELECT '+columns+' FROM users ORDER BY id'))]
            if connection.dialect.name == 'mysql':
                connection.execute(text("SET SESSION sql_mode='NO_AUTO_VALUE_ON_ZERO'"))
            connection.execute(text('ALTER TABLE users DROP COLUMN security_stamp'))
            if connection.dialect.name == 'mysql':
                connection.execute(text('SET SESSION sql_mode=:mode'),{'mode':mode})
            migration_2026_11_26_01(connection)
            migration_2026_11_26_01(connection)
            if connection.dialect.name == 'mysql':
                self.assertEqual(connection.scalar(text('SELECT @@SESSION.sql_mode')),mode)
            self.assertEqual(before,[tuple(r) for r in connection.execute(text('SELECT '+columns+' FROM users ORDER BY id'))])
            self.assertEqual(connection.scalar(text('SELECT COUNT(*) FROM users WHERE security_stamp IS NOT NULL')),0)
        self.db.expire_all()

    def test_missing_password_fingerprint_is_rejected(self):
        cookie=self.client.cookies.get(SESSION_COOKIE)
        signer=TimestampSigner(SESSION_SECRET)
        data=json.loads(base64.b64decode(signer.unsign(cookie)))
        data.pop('password_version',None)
        modified=signer.sign(base64.b64encode(json.dumps(data).encode())).decode()
        self.client.cookies.clear(); self.client.cookies.set(SESSION_COOKIE,modified)
        self.assertFalse(self.client.get('/api/session').json()['authenticated'])

    def test_remembered_login_replaces_previous_token_but_not_other_sessions(self):
        first=self.client
        second=TestClient(app,follow_redirects=False)
        self.addCleanup(second.close)
        headers={'X-CSRF-Token':first.get('/api/csrf-token').json()['token']}
        self.assertEqual(first.post('/api/auth/login',headers=headers,data={
            'email':self.actor.email,'password':'test-secret','remember':'true'}).status_code,303)
        old=first.cookies.get('typography_remember')
        headers={'X-CSRF-Token':second.get('/api/csrf-token').json()['token']}
        self.assertEqual(second.post('/auth/login',headers=headers,data={
            'email':self.actor.email,'password':'test-secret','remember':'true'}).status_code,303)
        self.assertTrue(first.get('/api/session').json()['authenticated'])
        first.cookies.clear(); first.cookies.set('typography_remember',old)
        self.assertFalse(first.get('/api/session').json()['authenticated'])

    def test_security_stamp_migration_preserves_legacy_credentials_and_is_repeatable(self):
        engine=create_engine('sqlite://')
        try:
            with engine.begin() as connection:
                connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, password VARCHAR(60), remember_token VARCHAR(100))'))
                connection.execute(text("INSERT INTO users VALUES (1,'historical-hash','historical-digest')"))
                migration_2026_11_26_01(connection)
                migration_2026_11_26_01(connection)
                self.assertIn('security_stamp',{c['name'] for c in inspect(connection).get_columns('users')})
                self.assertEqual(tuple(connection.execute(text('SELECT password,remember_token,security_stamp FROM users')).one()),
                                 ('historical-hash','historical-digest',None))
        finally:
            engine.dispose()

    def test_lifecycle_and_identity_changes_never_revive_old_cookies(self):
        self.grant('user_edit','user_reset_credentials','user_delete','restore_trashed',
                   'user_assign_role','view_menu_options_permissions')
        target_role=Role(title='Synthetic reader')
        other_role=Role(title='Synthetic alternate reader')
        self.db.add_all([target_role,other_role]); self.db.commit()
        self.target.role=target_role
        self.target.password=bcrypt.hashpw(b'old-password',bcrypt.gensalt()).decode()
        self.db.commit()
        target=TestClient(app,follow_redirects=False)
        self.addCleanup(target.close)
        payload={'name':'Target','surname':'Staff','phone':'123','post':'Staff',
                 'email':self.target.email,'role_id':target_role.id,'fired':False}
        for change in ('email','role_id','fired','deleted'):
            with self.subTest(change=change):
                target.cookies.clear()
                headers={'X-CSRF-Token':target.get('/api/csrf-token').json()['token']}
                self.assertEqual(target.post('/api/auth/login',headers=headers,data={
                    'email':payload['email'],'password':'old-password','remember':'true'}).status_code,303)
                cookies=dict(target.cookies)
                remembered=target.cookies.get('typography_remember')
                # Ordinary profile edits must not revoke this session.
                payload['phone'] += '1'
                self.assertEqual(self.client.patch(self.path,headers=self.headers,json=payload).status_code,200)
                self.assertTrue(target.get('/api/session').json()['authenticated'])
                if change == 'deleted':
                    self.assertEqual(self.client.delete(self.path,headers=self.headers).status_code,200)
                    self.assertEqual(self.client.post(self.path+'/restore',headers=self.headers).status_code,200)
                else:
                    payload[change]={'email':'changed@example.test','role_id':other_role.id,'fired':True}[change]
                    self.assertEqual(self.client.patch(self.path,headers=self.headers,json=payload).status_code,200)
                    if change == 'fired':
                        payload['fired']=False
                        self.assertEqual(self.client.patch(self.path,headers=self.headers,json=payload).status_code,200)
                self.assertIsNone(self.target.remember_token)
                target.cookies.clear(); target.cookies.update(cookies)
                self.assertFalse(target.get('/api/session').json()['authenticated'])
                target.cookies.clear(); target.cookies.set('typography_remember',remembered)
                self.assertFalse(target.get('/api/session').json()['authenticated'])
                self.assertTrue(self.client.get('/api/session').json()['authenticated'])

    def test_employee_password_reset_rejects_old_password_session_and_remember(self):
        self.grant('user_edit','user_reset_credentials')
        self.target.password=bcrypt.hashpw(b'old-password',bcrypt.gensalt()).decode()
        self.db.commit()
        target=TestClient(app,follow_redirects=False)
        self.addCleanup(target.close)
        token={'X-CSRF-Token':target.get('/api/csrf-token').json()['token']}
        self.assertEqual(target.post('/api/auth/login',headers=token,data={
            'email':self.target.email,'password':'old-password','remember':'true'}).status_code,303)
        old_cookies=dict(target.cookies)
        old_remember=target.cookies.get('typography_remember')
        payload={'name':'Target','surname':'Staff','phone':'123','post':'Staff',
                 'email':self.target.email,'role_id':self.role.id,'fired':False,
                 'change_password':True,'password':'new-password','password_confirmation':'new-password'}
        self.target.role=self.role; self.db.commit()
        self.db.add(PasswordReset(email=self.target.email,token='obsolete-recovery',created_at=utc_now()))
        self.db.commit()
        self.assertEqual(self.client.patch(self.path,headers=self.headers,json=payload).status_code,200)
        self.assertIsNone(self.db.get(PasswordReset,self.target.email))
        self.assertIsNone(self.target.remember_token)
        target.cookies.clear(); target.cookies.update(old_cookies)
        self.assertFalse(target.get('/api/session').json()['authenticated'])
        target.cookies.clear(); target.cookies.set('typography_remember',old_remember)
        self.assertFalse(target.get('/api/session').json()['authenticated'])
        token={'X-CSRF-Token':target.get('/api/csrf-token').json()['token']}
        self.assertEqual(target.post('/api/auth/login',headers=token,data={
            'email':self.target.email,'password':'old-password'}).status_code,422)
        self.assertEqual(target.post('/api/auth/login',headers=token,data={
            'email':self.target.email,'password':'new-password'}).status_code,303)
        self.assertTrue(self.client.get('/api/session').json()['authenticated'])