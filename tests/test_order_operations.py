import unittest

from tests import test_reference_dictionaries as fixtures
from app.models import Blank, BlankAfterprint, BlankImagesetter, Compile, Order, OrderCompile, OrderMarkup, Prepress, Redaction


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

    def test_operation_delete_restore_and_trash_visibility(self):
        created = self.client.post('/api/orders/10/prepresses', json={'prepress_id': 10, 'quantity': 1})
        item_id = created.json()['id']
        self.assertEqual(self.client.delete(f'/api/orders/10/prepresses/{item_id}').status_code, 200)
        self.permission_mock.return_value = False
        self.assertEqual(self.client.get('/api/orders/10/operations').json()['operations']['prepresses'], [])

        self.permission_mock.return_value = True
        visible = self.client.get('/api/orders/10/operations').json()
        self.assertEqual(visible['operations']['prepresses'][0]['deleted'], True)
        self.assertTrue(visible['permissions']['restore'])
        self.assertEqual(self.client.post(f'/api/orders/10/prepresses/{item_id}/restore').status_code, 200)
        self.assertFalse(self.client.get('/api/orders/10/operations').json()['operations']['prepresses'][0]['deleted'])

    def test_order_copy_preserves_active_operations_blanks_and_markups(self):
        self.db.add_all([
            OrderMarkup(order_id=10, markup_type='design', value=17, active=True),
            OrderCompile(order_id=10, compile_id=10, quantity=3, fitting=True),
            Blank(id=20, order_id=10, title='Cover', printer_id=0, details_per_blank=1),
        ])
        self.db.commit()
        self.db.add(BlankImagesetter(blank_id=20, plates=2, fix=False))
        self.db.add(BlankAfterprint(blank_id=20, afterprint_id=1, active=True, parameters='a:0:{}'))
        self.db.commit()
        copied = self.client.post('/api/orders/10/copy', json={'title': 'Copy'})
        self.assertEqual(copied.status_code, 200)
        new_id = copied.json()['id']
        self.assertEqual(self.db.query(OrderCompile).filter_by(order_id=new_id).count(), 1)
        copied_blank = self.db.query(Blank).filter_by(order_id=new_id).one()
        self.assertEqual(copied_blank.title, 'Cover')
        self.assertEqual(self.db.query(BlankImagesetter).filter_by(blank_id=copied_blank.id).one().plates, 2)
        self.assertTrue(self.db.query(BlankAfterprint).filter_by(blank_id=copied_blank.id).one().active)
        self.assertEqual(self.db.query(OrderMarkup).filter_by(order_id=new_id, markup_type='design').one().value, 17)


if __name__ == '__main__':
    unittest.main()