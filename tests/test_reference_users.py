import unittest
import bcrypt
from tests import test_reference_dictionaries as fixtures
from app.models import Role, User


class EmployeeReferenceTests(unittest.TestCase):
    def setUp(self):
        fixtures.ReferenceDictionaryTests.setUp(self)
        self.user.id = -1  # The mocked actor is not the employee created by these tests.
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def payload(self):
        self.db.add(Role(id=1,title='Manager')); self.db.commit()
        return {'name':'Ivan','surname':'Ivanov','phone':'123','email':'ivan@example.test','post':'Manager',
                'role_id':1,'password':'secret123','password_confirmation':'secret123'}

    def test_create_hash_update_and_password_opt_in(self):
        payload = self.payload()
        created = self.client.post('/api/employee-references',json=payload)
        self.assertEqual(created.status_code,200,created.text)
        identity = created.json()['id']; row = self.db.get(User,identity)
        original = row.password
        self.assertTrue(bcrypt.checkpw(b'secret123',original.encode()))
        target = f'/api/employee-references/{identity}'
        self.assertNotIn('password',self.client.get(target).json()['item'])
        self.assertEqual(self.client.patch(target,json={**payload,'post':'Director','password':'ignored','password_confirmation':'ignored'}).status_code,200)
        self.assertEqual(row.password,original)
        self.assertEqual(self.client.patch(target,json={**payload,'change_password':True,'password':'newsecret','password_confirmation':'newsecret','fired':True}).status_code,200)
        self.assertTrue(bcrypt.checkpw(b'newsecret',row.password.encode()))
        self.assertEqual(row.fired,1)

    def test_validation_permissions_and_lifecycle(self):
        payload = self.payload()
        self.assertEqual(self.client.post('/api/employee-references',json={**payload,'password_confirmation':'wrong'}).status_code,422)
        identity = self.client.post('/api/employee-references',json=payload).json()['id']
        self.assertEqual(self.client.post('/api/employee-references',json=payload).status_code,422)
        target = f'/api/employee-references/{identity}'
        self.permission_mock.return_value = False
        self.assertEqual(self.client.patch(target,json=payload).status_code,403)
        self.assertEqual(self.client.get('/api/employee-references/form').status_code,403)
        self.permission_mock.return_value = True
        self.client.delete(target)
        self.permission_mock.return_value = False
        self.assertEqual(self.client.get(target).status_code,403)
        self.assertEqual(self.client.delete(target).status_code,403)
        self.assertEqual(self.client.post(target+'/restore').status_code,403)
        self.permission_mock.return_value = True
        self.assertEqual(self.client.post(target+'/restore').status_code,200)

    def test_deleted_account_cannot_login(self):
        payload = self.payload()
        identity = self.client.post('/api/employee-references',json=payload).json()['id']
        self.client.delete(f'/api/employee-references/{identity}')
        response = self.client.post('/api/auth/login',data={'email':payload['email'],'password':payload['password']},follow_redirects=False)
        self.assertEqual(response.status_code,422)

    def test_roles_hidden_without_edit_permission_and_secret_fields_never_returned(self):
        payload = self.payload()
        identity = self.client.post('/api/employee-references',json=payload).json()['id']
        self.permission_mock.return_value = False
        self.permission_mock.side_effect = lambda permission: permission == 'view_menu_references_users'
        response = self.client.get(f'/api/employee-references/{identity}').json()
        self.assertEqual(response['roles'], [])
        self.assertFalse(response['can_edit'])
        self.assertNotIn('password', response['item'])
        self.assertNotIn('password', self.client.get('/api/employee-references').json()['items'][0])

    def test_employee_upgrade_preserves_password_hash(self):
        from unittest.mock import patch
        from sqlalchemy import create_engine, text
        from app.schema import upgrade_local_schema
        engine = create_engine('sqlite:///:memory:')
        try:
            with engine.begin() as connection:
                connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, password TEXT)'))
                connection.execute(text("INSERT INTO users VALUES (1, 'Existing', 'existing-hash')"))
            with patch('app.schema.engine',engine):
                upgrade_local_schema(); upgrade_local_schema()
            with engine.connect() as connection:
                self.assertEqual(tuple(connection.execute(text('SELECT name, password, deleted_at FROM users')).one()), ('Existing','existing-hash',None))
        finally:
            engine.dispose()