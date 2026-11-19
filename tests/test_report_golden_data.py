"""PHP-free expected-value document tests; not pixel or binary snapshots."""
from datetime import date, datetime
from io import BytesIO
import unittest

from pypdf import PdfReader
import xlrd

from app.models import Bill, Order, Report, ReportParam
from app.php_serialization import dumps
from tests import test_reference_dictionaries as fixtures


class ReportGoldenDataTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def seed_bill(self):
        self.db.add(Bill(id=20, number='GOLD-20', bill_date=date(2024, 2, 3), amount=999))
        self.db.add_all([
            Order(id=21, status_id=1, title='First golden product', bill_id=20, printing=3, total='10.01'),
            Order(id=22, status_id=1, title='Zero quantity product', bill_id=20, printing=0, total='2.02'),
            Order(id=23, status_id=1, title='Deleted product', bill_id=20, printing=1, total=700,
                  deleted_at=datetime(2024, 1, 1)),
            Report(id='order_payment', program='ipc', kind='xls', form=True, download=True,
                   title='Payment', model='App\\Bill', model_title='Bill'),
            Report(id='order_shipping', program='ipc', kind='pdf', form=True, download=True,
                   title='Shipping', model='App\\Bill', model_title='Bill', format='A4', orientation='P'),
        ])
        for report, aliases in [('order_payment', ['prorector', 'zam_prorectora', 'boss', 'buh', 'pfu']),
                                ('order_shipping', ['pto', 'buh'])]:
            for alias in aliases:
                self.db.add(ReportParam(report_id=report, alias=alias, title=alias, value=f'Golden-{alias}'))
        self.db.commit()

    def sheet(self, response):
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.assertEqual(response.headers['content-type'], 'application/vnd.ms-excel')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
        return xlrd.open_workbook(file_contents=response.content, formatting_info=True).sheet_by_index(0)

    def test_payment_multi_order_rounding_signatures_and_form(self):
        self.seed_bill()
        response = self.client.post('/reports/order_payment/item/20', data={
            'vars[institute]': 'Golden institute', 'vars[customer]': 'Golden customer'})
        sheet = self.sheet(response)
        self.assertIn('payment-request-20.xls', response.headers['content-disposition'])
        self.assertEqual(sheet.cell_value(11, 2), 3)
        self.assertAlmostEqual(sheet.cell_value(11, 4), 10.01 / 3)
        self.assertEqual(sheet.cell_value(12, 4), 0)
        self.assertAlmostEqual(sheet.cell_value(13, 7), 12.03)
        values = [str(cell) for row in sheet._cell_values for cell in row]
        for alias in ['prorector', 'zam_prorectora', 'boss', 'buh', 'pfu']:
            self.assertTrue(any(f'Golden-{alias}' in cell for cell in values))
        self.assertIn('Golden customer', values)
        self.assertTrue(any('Golden institute' in cell for cell in values))
        self.assertFalse(any('Deleted product' in cell for cell in values))
        self.assertTrue(sheet.merged_cells)

    def test_shipping_totals_signatures_and_empty_bill(self):
        self.seed_bill()
        response = self.client.post('/reports/order_shipping/item/20', data={'vars[buh]': 'Chosen accountant'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'application/pdf')
        self.assertIn('order-shipping-20.pdf', response.headers['content-disposition'])
        reader = PdfReader(BytesIO(response.content))
        text = '\n'.join(page.extract_text() for page in reader.pages)
        for expected in ['First golden product', 'Zero quantity product', '12.03', '3.34',
                         'Golden-pto', 'Chosen accountant', 'GOLD-20']:
            self.assertIn(expected, text)
        self.assertNotIn('Deleted product', text)
        self.assertAlmostEqual(float(reader.pages[0].mediabox.width), 595.28, places=1)
        self.db.add(Bill(id=30, number='EMPTY', amount=999)); self.db.commit()
        empty = self.client.get('/reports/order_payment/item/30')
        self.assertEqual(self.sheet(empty).cell_value(11, 7), 0)
        self.db.get(Bill, 30).deleted_at = datetime(2024, 1, 1); self.db.commit()
        for name in ['order_shipping', 'order_payment']:
            self.assertEqual(self.client.get(f'/reports/{name}/item/30').status_code, 404)

    def test_wide_economy_summary_does_not_count_same_blank_twice(self):
        self.db.add_all([
            Order(id=40, status_id=1, title='Golden wide', order_type='wide', printing=4, total=999,
                  calc_details=dumps({'blanks': {'1': {'cost': 10, 'details': {'title': 'Panel',
                    'width': 1000, 'height': 500, 'paper': {'material_count': 2}}}},
                    'design': [{'title': 'Layout', 'cost': 5}],
                    'markups': {'print': {'active': True, 'markup': 10}}})),
            Report(id='order_economy', program='ipc', kind='xls', title='Economy',
                   model='App\\Order', model_title='Order'),
        ]); self.db.commit()
        sheet = self.sheet(self.client.get('/reports/order_economy/item/40'))
        def amount(label):
            return next(sheet.cell_value(row, 7) for row in range(sheet.nrows)
                        if sheet.cell_value(row, 0) == label)
        self.assertAlmostEqual(amount('ИТОГО рассчитанная стоимость'), 16)
        self.assertAlmostEqual(amount('Стоимость за 1 шт.'), 4)
        self.assertEqual(self.db.get(Order, 40).total, 999)
        self.db.get(Order, 40).calc_details = ''; self.db.commit()
        self.assertEqual(self.client.get('/reports/order_economy/item/40').status_code, 422)