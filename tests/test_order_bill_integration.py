import unittest
from datetime import date
from tests import test_reference_dictionaries as fixtures
from app.models import Bill, Order, OrderStatus, User


class OrderBillIntegrationTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def test_selected_bill_and_manager_persist_and_clear(self):
        self.db.add_all([
            User(id=20, name='Manager', surname='Test', email='manager@test', password='unused'),
            OrderStatus(id=1, title='Draft', sequence=1),
            Bill(id=1, number='B-1', bill_date=date(2024, 1, 2)),
            Order(id=1, title='Order', order_type='poly', status_id=1, printing=10, total=100),
        ])
        self.db.commit()
        response = self.client.put('/api/orders/1', json={'bill_id':1,'user_id':20})
        self.assertEqual(response.status_code,200,response.text)
        detail = self.client.get('/api/orders/1').json()['order']
        self.assertEqual(detail['bill_id'],1)
        self.assertEqual(detail['manager_id'],20)
        self.assertEqual(detail['bill']['number'],'B-1')
        self.assertEqual(self.client.get('/api/accounting/bills/1').json()['orders'][0]['id'],1)
        self.assertEqual(self.client.get('/api/accounting/bills/1').json()['orders'][0]['url'], '/orders/1')
        self.assertEqual(self.client.put('/api/orders/1',json={'bill_id':None}).status_code,200)
        self.assertIsNone(self.db.get(Order,1).bill_id)