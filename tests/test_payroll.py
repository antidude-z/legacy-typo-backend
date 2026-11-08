import unittest
from datetime import date

from tests import test_reference_dictionaries as fixtures
from app.models import Bill, Order, Payroll, PayrollOrder, User


class PayrollTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def seed(self):
        manager = User(id=20, name='Ivan', surname='Ivanov', email='manager', password='unused')
        bill = Bill(id=30, number='B-30', bill_date=date(2024, 1, 5), amount=100, paid=True, closed=True, filed=True)
        order = Order(id=40, title='Paid order', status_id=1, order_type='poly', printing=10, total=100,
                      user_id=20, bill_id=30, calc_details='a:2:{s:6:"design";a:1:{i:0;a:2:{s:5:"title";s:6:"Layout";s:4:"cost";d:10;}}s:6:"blanks";a:0:{}}')
        self.db.add_all([manager, bill, order])
        self.db.commit()

    def test_create_refreshes_eligible_orders_and_updates_percent(self):
        self.seed()
        response = self.client.post('/api/reports/payrolls', json={'manager_id':20, 'year':2024, 'month':1})
        self.assertEqual(response.status_code, 200, response.text)
        identity = response.json()['id']
        result = self.client.get(f'/api/reports/payrolls/{identity}')
        self.assertEqual(result.status_code, 200, result.text)
        item = result.json()['item']
        self.assertEqual(len(item['orders']), 1)
        self.assertEqual(item['orders'][0]['works'], '10.00')
        self.assertEqual(item['orders'][0]['salary'], '2.70')
        self.assertEqual(self.client.patch(f'/api/reports/payrolls/{identity}', json={'salary':'1000','status':'calc','markups':{str(item['orders'][0]['id']):5}}).status_code, 200)
        self.assertEqual(self.db.scalar(__import__('sqlalchemy').select(PayrollOrder).where(PayrollOrder.payroll_id == identity)).percent, 5)

    def test_paid_statement_is_immutable(self):
        self.seed()
        payroll = Payroll(user_id=20, period=date(2024, 1, 1), salary=100, status='paid')
        self.db.add(payroll); self.db.commit()
        response = self.client.patch(f'/api/reports/payrolls/{payroll.id}', json={'salary':'999','status':'paid','markups':{}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.get(Payroll, payroll.id).salary, 100)