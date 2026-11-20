import unittest
from tests import test_reference_dictionaries as fixtures
from app.models import Customer, CustomerGroup


class CustomerReferenceTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def test_group_draft_and_customer_submission(self):
        group = self.client.post('/api/options/customer-group/create').json()['item']['id']
        self.assertEqual(self.db.get(CustomerGroup, group).title, '')
        self.assertEqual(self.client.patch(f'/api/options/customer-group/{group}', json={'customer_group_title':'Regular'}).status_code, 200)
        self.client.get('/api/customer-references/form')
        self.assertEqual(self.db.query(Customer).count(), 0)
        values = {'customer_title':'Client', 'customer_group':group, 'customer_phone':'123', 'customer_inn':'00123', 'customer_address':'Address', 'customer_description':'Notes'}
        created = self.client.post('/api/customer-references', json=values)
        self.assertEqual(created.status_code, 200, created.text)
        identity = created.json()['id']
        detail = self.client.get(f'/api/customer-references/{identity}').json()['item']
        self.assertEqual(detail['inn'], '00123')
        self.assertEqual(detail['group_title'], 'Regular')
        self.assertEqual(self.client.patch(f'/api/customer-references/{identity}', json={**values, 'customer_title':'Updated'}).status_code, 200)

    def test_customer_validation_visibility_restore_and_delete(self):
        self.assertEqual(self.client.post('/api/customer-references', json={'title':''}).status_code, 422)
        self.assertEqual(self.client.post('/api/customer-references', json={'title':'Client','customer_group_id':999}).status_code, 422)
        identity = self.client.post('/api/customer-references', json={'title':'Client'}).json()['id']
        target = f'/api/customer-references/{identity}'
        self.client.delete(target)
        self.permission_mock.side_effect = lambda name: name == 'view_menu_references_customers'
        self.assertEqual(self.client.get(target).status_code, 404)
        self.assertEqual(self.client.get('/api/customer-references').json()['items'], [])
        self.assertEqual(self.client.post(target + '/restore').status_code, 403)
        self.assertEqual(self.client.delete(target).status_code, 403)
        self.permission_mock.side_effect = None
        self.permission_mock.return_value = True
        self.assertEqual(self.client.post(target + '/restore').status_code, 200)
        self.client.delete(target)
        self.assertEqual(self.client.delete(target).status_code, 200)

    def test_customer_authentication_and_pagination(self):
        for title in ['B', 'A']:
            self.client.post('/api/customer-references', json={'title':title})
        response = self.client.get('/api/customer-references?sort=title&order=asc&per_page=1').json()
        self.assertEqual(response['items'][0]['title'], 'A')
        self.assertEqual(response['last_page'], 2)
        self.auth_mock.return_value = None
        self.assertEqual(self.client.get('/api/customer-references').status_code, 401)

    def test_customer_upgrade_preserves_existing_rows(self):
        from unittest.mock import patch
        from sqlalchemy import create_engine, text
        from app.schema import upgrade_local_schema
        engine = create_engine('sqlite:///:memory:')
        try:
            with engine.begin() as connection:
                connection.execute(text('CREATE TABLE customers (id INTEGER PRIMARY KEY, title TEXT)'))
                connection.execute(text("INSERT INTO customers VALUES (1, 'Existing')"))
            with patch('app.schema.engine', engine):
                upgrade_local_schema(); upgrade_local_schema()
            with engine.connect() as connection:
                self.assertEqual(tuple(connection.execute(text('SELECT title, profit, customer_group_id FROM customers')).one()), ('Existing', 0, None))
        finally:
            engine.dispose()