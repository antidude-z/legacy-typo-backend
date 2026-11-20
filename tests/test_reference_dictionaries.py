import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from tests.staff_fixture import admit_mock_staff
from app.models import Measure, Order, PaperFormat, PaperType, User


class ReferenceDictionaryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([PaperType(id=1, title='Офсет'), PaperFormat(id=1, title='A4', width=210, height=297), Measure(id=1, title='Штука', short='шт')])
        self.db.commit()
        def database():
            yield self.db
        app.dependency_overrides[get_db] = database
        self.user = User(id=1, name='Test', email='test', password='unused')
        admit_mock_staff(self.user)
        self.auth = patch('app.main.current_user', return_value=self.user)
        self.auth_mock = self.auth.start()
        self.permission = patch.object(User, 'has_permission', return_value=True)
        self.permission_mock = self.permission.start()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.permission.stop()
        self.auth.stop()
        self.db.close()
        self.engine.dispose()

    def test_dictionary_crud_and_soft_delete_restore(self):
        response = self.client.get('/api/options/paper-type')
        self.assertEqual(response.json()['items'][0]['title'], 'Офсет')
        created = self.client.post('/api/options/paper-type/create').json()
        identity = created['item']['id']
        self.assertEqual(self.client.patch(f'/api/options/paper-type/{identity}', json={'paper_type_title': 'Мелованная'}).status_code, 200)
        self.assertEqual(self.client.delete(f'/api/options/paper-type/{identity}').status_code, 200)
        self.permission_mock.side_effect = lambda name: name.startswith("view_menu_")
        self.assertEqual(len(self.client.get('/api/options/paper-type').json()['items']), 1)
        self.permission_mock.side_effect = None
        self.permission_mock.return_value = True
        self.assertEqual(self.client.post(f'/api/options/paper-type/{identity}/restore').status_code, 200)
        self.assertEqual(len(self.client.get('/api/options/paper-type').json()['items']), 2)

    def test_format_and_measure_validation(self):
        self.assertEqual(self.client.patch('/api/options/paper-format/1', json={'paper_format_title': 'A4', 'paper_format_width': '210', 'paper_format_height': '297'}).status_code, 200)
        self.assertEqual(self.client.patch('/api/options/paper-format/1', json={'paper_format_title': '', 'paper_format_width': 'x', 'paper_format_height': '297'}).status_code, 422)
        self.assertEqual(self.client.post('/api/options/measures', json={'measure_title': 'Метр', 'measure_short': 'м'}).status_code, 200)

    def test_permissions_are_enforced(self):
        self.permission_mock.side_effect = lambda name: name.startswith("view_menu_")
        self.assertEqual(self.client.post('/api/options/paper-type/1/restore').status_code, 403)
        self.permission_mock.side_effect = None
        self.permission_mock.return_value = True
        self.auth_mock.return_value = None
        self.assertEqual(self.client.get('/api/options/paper-type').status_code, 401)

    def test_permanent_delete_requires_permission(self):
        self.client.delete('/api/options/measures/1')
        self.permission_mock.side_effect = lambda name: name.startswith("view_menu_")
        self.assertEqual(self.client.delete('/api/options/measures/1').status_code, 403)
        self.assertEqual(self.client.get('/api/options/measures/1').status_code, 404)
        self.permission_mock.side_effect = None
        self.permission_mock.return_value = True
        self.assertEqual(self.client.delete('/api/options/measures/1').status_code, 200)
        self.assertIsNone(self.db.get(Measure, 1))

    def test_measure_create_has_no_draft_and_sorting_uses_short(self):
        self.client.post('/api/options/measures/create')
        self.assertEqual(self.db.query(Measure).count(), 1)
        self.client.post('/api/options/measures', json={'measure_title': 'Метр', 'measure_short': 'м'})
        response = self.client.get('/api/options/measures?sort=short&order=asc&per_page=1').json()
        self.assertEqual(response['last_page'], 2)
        self.assertEqual(response['sort'], 'short')

    def test_order_format_lookup_combines_paper_and_existing_order_formats(self):
        self.db.add_all([
            PaperFormat(id=2, title='A3', width=297, height=420),
            PaperFormat(id=3, title='A4 landscape', width=297, height=210),
            Order(id=10, title='Existing', order_type='poly', status_id=1, format='A4 custom', printing=1),
            Order(id=11, title='Other', order_type='poly', status_id=1, format='A4 custom', printing=1),
        ])
        self.db.commit()
        response = self.client.get('/api/orders/formats/poly/A4')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ['A4', 'A4 custom', 'A4 landscape'])
        self.assertEqual(self.client.get('/api/orders/formats/wide/A4').json(), [])

    def test_order_format_lookup_requires_authentication(self):
        self.auth_mock.return_value = None
        self.assertEqual(self.client.get('/api/orders/formats/poly/A').status_code, 401)


if __name__ == '__main__':
    unittest.main()