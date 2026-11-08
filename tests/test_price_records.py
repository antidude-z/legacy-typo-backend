import unittest
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Paper, Price, User


class PriceRecordsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(Paper(id=1, title='Paper'))
        self.db.commit()
        def database():
            yield self.db
        app.dependency_overrides[get_db] = database
        self.user = User(id=1, name='Test', email='test', password='unused')
        self.auth = patch('app.main.current_user', return_value=self.user)
        self.auth_mock = self.auth.start()
        self.permission = patch.object(User, 'has_permission', return_value=True)
        self.permission_mock = self.permission.start()
        self.client = TestClient(app)
        self.url = '/api/prices/paper/1/records'
        self.payload = {'amount': '12.50', 'currency': 'RUB', 'actual_since': '2020-01-01', 'actual_from': 0}

    def tearDown(self):
        app.dependency_overrides.clear()
        self.permission.stop()
        self.auth.stop()
        self.db.close()
        self.engine.dispose()

    def test_crud_and_hard_delete(self):
        response = self.client.post(self.url, json=self.payload)
        self.assertEqual(response.status_code, 200, response.text)
        identity = response.json()['id']
        self.assertEqual(len(self.client.get(self.url).json()['items']), 1)
        self.assertEqual(self.client.patch(f'{self.url}/{identity}', json={**self.payload, 'amount': '20'}).status_code, 200)
        self.assertEqual(self.client.delete(f'{self.url}/{identity}').status_code, 200)
        self.assertIsNone(self.db.get(Price, identity))

    def test_invalid_values_and_ownership(self):
        for changes in ({'amount': 'NaN'}, {'amount': 'wrong'}, {'currency': 'GBP'}, {'actual_since': 'invalid'}, {'actual_from': '1.5'}):
            self.assertEqual(self.client.post(self.url, json={**self.payload, **changes}).status_code, 422)
        identity = self.client.post(self.url, json=self.payload).json()['id']
        self.assertEqual(self.client.patch(f'/api/prices/paper/2/records/{identity}', json=self.payload).status_code, 404)

    def test_permissions_and_catalog(self):
        self.assertEqual(self.client.get('/api/pricing/catalog/paper').json()['items'][0]['title'], 'Paper')
        self.permission_mock.return_value = False
        self.assertEqual(self.client.post(self.url, json=self.payload).status_code, 403)
        self.auth_mock.return_value = None
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_default_creation_detail_and_current_catalog_price(self):
        created = self.client.post('/api/prices/paper/1/create')
        self.assertEqual(created.status_code, 200)
        row = created.json()
        self.assertEqual(row['amount'], '0.00')
        self.assertEqual(row['actual_since'], date.today().isoformat())
        self.assertEqual(self.client.get(f"{self.url}/{row['id']}").json()['title'], 'Paper')
        response = self.client.patch(f"{self.url}/{row['id']}", json={**self.payload, 'actual_since': '01.01.2020'})
        self.assertEqual(response.status_code, 200)
        catalog = self.client.get('/api/pricing/catalog/paper').json()
        self.assertEqual(catalog['items'][0]['current_price'], '12.50')


if __name__ == '__main__':
    unittest.main()