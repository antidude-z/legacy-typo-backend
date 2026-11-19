import unittest
from datetime import date, datetime

from tests import test_reference_dictionaries as fixtures
from app.models import Blank, BlankAfterprint, BlankImagesetter, Compile, Order, OrderCompile, OrderMarkup, Prepress, Redaction
from app.models import OtherWork, OrderOtherWork, Paper, Price


class OrderOperationTests(unittest.TestCase):
    def test_fractional_work_edit_copy_and_calculation(self):
        from decimal import Decimal
        from app.models import OrderPrepress, OrderRedaction
        for operation, field, model, kind in [('prepresses', 'prepress_id', OrderPrepress, 'Prepress'),
                                              ('redactions', 'redaction_id', OrderRedaction, 'Redaction')]:
            created = self.client.post(f'/api/orders/10/{operation}', json={field: 10, 'quantity': '1.25'})
            self.assertEqual(created.status_code, 200, created.text)
            identity = created.json()['id']
            self.assertEqual(self.client.patch(f'/api/orders/10/{operation}/{identity}', json={'quantity':'2.75'}).status_code, 200)
            self.assertEqual(self.client.patch(f'/api/orders/10/{operation}/{identity}', json={'quantity':'1.001'}).status_code, 422)
            self.db.add(Price(priceable_type=f'App\\{kind}', priceable_id=10, amount=4,
                              currency='RUB', actual_since=date(2020,1,1), actual_from=0))
        self.db.commit()
        from app.orders import calculate_order
        result = calculate_order(self.db, self.db.get(Order,10))
        self.assertEqual(Decimal(result['components']['design']), Decimal('11'))
        copied = self.client.post('/api/orders/10/copy', json={}).json()['id']
        for model in (OrderPrepress, OrderRedaction):
            self.assertEqual(self.db.query(model).filter_by(order_id=copied).one().quantity, Decimal('2.75'))

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
        self.assertEqual(payload['operations']['prepresses'][0]['quantity'], '2.00')

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

    def test_all_order_types_create_and_copy_without_deleted_children(self):
        for kind in ('book', 'poly', 'wide', 'souvenir'):
            with self.subTest(kind=kind):
                response = self.client.post(f'/api/orders/add/{kind}', data={'order_title': kind, 'order_printing': 12, 'order_volume': '32'})
                self.assertEqual(response.status_code, 200)
                identity = response.json()['id']
                source = self.db.get(Order, identity)
                self.assertEqual(source.order_type, kind)
                self.assertEqual(source.printing, 12)
                if kind == 'book':
                    self.assertEqual(source.volume, '32')
                self.db.add(Blank(order_id=identity, title='Deleted', printer_id=0, deleted_at=datetime(2020, 1, 1)))
                self.db.commit()
                copied = self.client.post(f'/api/orders/{identity}/copy', json={'title': 'Copy'})
                self.assertEqual(copied.status_code, 200)
                clone = self.db.get(Order, copied.json()['id'])
                self.assertEqual(clone.order_type, kind)
                self.assertEqual(clone.status_id, 1)
                self.assertIsNone(clone.bill_id)
                self.assertEqual(self.db.query(Blank).filter_by(order_id=clone.id).count(), 0)

    def test_copy_refreshes_paper_price_and_isolates_other_work(self):
        self.db.add_all([
            Paper(id=40, title='Paper', weight=80),
            Price(id=40, priceable_type='App\\Paper', priceable_id=40, amount=7, currency='RUB', actual_from=0, actual_since=date(2020, 1, 1)),
            Blank(order_id=10, title='Cover', printer_id=0, paper_id=40, paper_price=1),
            OtherWork(id=40, title='Delivery'),
            Price(id=41, priceable_type='App\\OtherWork', priceable_id=40, amount=15, currency='RUB', actual_from=0, actual_since=date(2020, 1, 1)),
            Price(id=42, priceable_type='App\\OtherWork', priceable_id=40, amount=999, currency='RUB', actual_from=0, actual_since=date(2099, 1, 1)),
            OrderOtherWork(order_id=10, other_work_id=40, quantity=2, price_id=41),
        ])
        self.db.commit()
        response = self.client.post('/api/orders/10/copy', json={})
        self.assertEqual(response.status_code, 200)
        identity = response.json()['id']
        self.assertEqual(self.db.query(Blank).filter_by(order_id=identity).one().paper_price, 7)
        work = self.db.query(OrderOtherWork).filter_by(order_id=identity).one()
        self.assertNotEqual(work.other_work_id, 40)
        self.assertNotEqual(work.price_id, 41)
        self.assertEqual(self.db.get(Price, work.price_id).amount, 15)


if __name__ == '__main__':
    unittest.main()