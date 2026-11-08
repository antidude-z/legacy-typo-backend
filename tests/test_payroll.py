import unittest
from datetime import date
import xlrd

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

    def test_payroll_xls_export_contains_statement_rows_and_totals(self):
        self.seed()
        identity = self.client.post('/api/reports/payrolls', json={'manager_id':20, 'year':2024, 'month':1}).json()['id']
        response = self.client.get(f'/reports/payrolls/{identity}/export')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-type'], 'application/vnd.ms-excel')
        self.assertIn('attachment', response.headers['content-disposition'])
        sheet = xlrd.open_workbook(file_contents=response.content).sheet_by_name('Зарплата')
        values = [cell for row in sheet._cell_values for cell in row]
        self.assertIn('Paid order', values)
        self.assertIn('Итого', values)
        self.assertIn('Всего за месяц', values)
        self.assertEqual(sheet.cell_value(4, 7), 100)
        self.assertEqual(sheet.cell_value(4, 9), 10)
        self.assertAlmostEqual(sheet.cell_value(4, 12), 2.70)
        self.assertAlmostEqual(sheet.cell_value(6, 12), 2.70)

    def test_export_paid_snapshot_and_access_checks(self):
        self.seed()
        payroll = Payroll(user_id=20, period=date(2024, 1, 1), salary=100, status='paid')
        self.db.add(payroll); self.db.flush()
        self.db.add(PayrollOrder(payroll_id=payroll.id, order_id=40, title='Snapshot', total=80,
                                 materials=10, works=5, contractors=2, salary=4, percent=5))
        self.db.commit()
        target = f'/reports/payrolls/{payroll.id}/export'
        response = self.client.get(target)
        self.assertEqual(response.status_code, 200)
        sheet = xlrd.open_workbook(file_contents=response.content).sheet_by_name('Зарплата')
        self.assertEqual(sheet.cell_value(3, 1), 'Snapshot')
        self.assertEqual(sheet.cell_value(6, 12), 104)
        self.assertEqual(self.client.get('/reports/payrolls/999/export').status_code, 404)
        self.permission_mock.return_value = False
        self.assertEqual(self.client.get(target).status_code, 403)
        self.auth_mock.return_value = None
        self.assertEqual(self.client.get(target).status_code, 401)