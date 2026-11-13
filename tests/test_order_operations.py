import unittest

from tests import test_reference_dictionaries as fixtures
from app.models import Compile, Order, Prepress, Redaction


class OrderOperationTests(unittest.TestCase):
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def setUp(self):
        fixtures.ReferenceDictionaryTests.setUp(self)
        self.db.add_all([
            Order(id=10, title='Order', order_type='poly', status_id=1, printing=100),
            Prepress(id=10, title='Layout'),
            Redaction(id=10, title='Editing'),
            Compile(id=10, title='Binding', production_poly=True),
            Compile(id=11, title='Book only', production_book=True),
        ])
        self.db.commit()

    def test_operation_payload_filters_compile_choices_and_lists_rows(self):
        result = self.client.get('/api/orders/10/operations')
        self.assertEqual(result.status_code, 200)
        self.assertEqual([item['id'] for item in result.json()['choices']['compiles']], [10])
        self.assertEqual(result.json()['operations']['prepresses'], [])

        created = self.client.post('/api/orders/10/prepresses', json={'prepress_id': 10, 'quantity': 2})
        self.assertEqual(created.status_code, 200)
        payload = self.client.get('/api/orders/10/operations').json()
        self.assertEqual(payload['operations']['prepresses'][0]['reference_id'], 10)
        self.assertEqual(payload['operations']['prepresses'][0]['quantity'], '2')

    def test_operation_create_rejects_wrong_production_reference_and_quantity(self):
        self.assertEqual(self.client.post('/api/orders/10/compiles', json={'compile_id': 11}).status_code, 422)
        self.assertEqual(self.client.post('/api/orders/10/prepresses', json={'prepress_id': 10, 'quantity': -1}).status_code, 422)
        self.assertEqual(self.client.get('/api/orders/10/operations').status_code, 200)


if __name__ == '__main__':
    unittest.main()