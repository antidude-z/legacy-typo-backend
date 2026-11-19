"""Historical references remain unchanged unless explicitly replaced."""
from datetime import date
import unittest

from app.models import Bill, Blank, Customer, Order
from tests import test_reference_dictionaries as fixtures


class OrphanPreservationTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def test_order_and_blank_reads_and_unrelated_edit_preserve_ids(self):
        self.db.add_all([
            Order(id=50, status_id=9001, user_id=9002, customer_id=9003,
                  bill_id=9004, title='Historical', printing=10, order_type='poly'),
            Blank(id=51, order_id=50, printer_id=9005, printer_process_id=9006,
                  paper_id=9007, title='Historical blank'),
        ]); self.db.commit()
        for path in ['/api/orders/50', '/api/orders/50/blanks', '/api/orders/50/operations']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, response.text)
        response = self.client.post('/api/orders/50', json={'title': 'Edited'})
        self.assertEqual(response.status_code, 200, response.text)
        self.db.expire_all()
        order = self.db.get(Order, 50)
        self.assertEqual((order.status_id, order.user_id, order.customer_id, order.bill_id),
                         (9001, 9002, 9003, 9004))
        blank = self.db.get(Blank, 51)
        self.assertEqual((blank.printer_id, blank.printer_process_id, blank.paper_id), (9005, 9006, 9007))

    def test_bill_preserves_old_missing_parents_but_rejects_new_orphans(self):
        self.db.add(Bill(id=60, number='Historical', bill_date=date(2024, 1, 1),
                         user_id=9010, payer_id=9011, amount=10, currency='RUB'))
        self.db.commit()
        response = self.client.get('/api/accounting/bills/60')
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()['item']
        payload['number'] = 'Edited'
        response = self.client.patch('/api/accounting/bills/60', json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.db.expire_all()
        self.assertEqual(self.db.get(Bill, 60).payer_id, 9011)
        payload['payer_id'] = 99999
        self.assertEqual(self.client.patch('/api/accounting/bills/60', json=payload).status_code, 422)
        self.assertEqual(self.client.post('/api/accounting/bills', json=payload).status_code, 422)

    def test_customer_preserves_missing_group_without_accepting_new_orphans(self):
        self.db.add(Customer(id=70, title='Historical', customer_group_id=9020))
        self.db.commit()
        response = self.client.get('/api/customer-references/70')
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()['item']
        payload.update(title='Edited', phone='', inn='', address='', description='')
        response = self.client.patch('/api/customer-references/70', json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.db.expire_all()
        self.assertEqual(self.db.get(Customer, 70).customer_group_id, 9020)
        payload['customer_group_id'] = 99999
        self.assertEqual(self.client.patch('/api/customer-references/70', json=payload).status_code, 422)