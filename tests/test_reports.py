import unittest
import xlrd
from pypdf import PdfReader
from tests import test_reference_dictionaries as fixtures
from app.models import Bill, Blank, Order, OrderMarkup, OrderStatus, Report, ReportParam, User
from app.php_serialization import dumps


class ReportTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def seed(self):
        self.db.add_all([
            OrderStatus(id=1,title='Draft',sequence=1),
            Order(id=1,title='Order',status_id=1,order_type='poly',printing=10,
                  calc_details=dumps({'printing':10,'title':'<script>bad</script>','paper':{'cost':12}})),
            Report(id='order_transcript',program='ipc',kind='html',title='Расшифровка расчета',model='App\\Order',model_title='Заказ'),
            Report(id='order_passport',program='ipc',kind='pdf',title='Passport',model='App\\Order',model_title='Заказ'),
            Report(id='order_economy',program='ipc',kind='xls',title='Экономика',model='App\\Order',model_title='Заказ'),
            Report(id='order_design',program='ipc',kind='xls',title='Наряд-заказ дизайна',model='App\\Order',model_title='Заказ'),
            Report(id='order_payment',program='ipc',kind='xls',form=True,title='Заявка на оплату',model='App\\Bill',model_title='Счет'),
            ReportParam(id=1,alias='company',report_id='order_transcript',title='Company',value='Original'),
        ])
        self.db.commit()

    def test_catalog_settings_and_parameter_scope(self):
        self.seed()
        self.assertEqual(len(self.client.get('/api/report-settings').json()['items']),5)
        self.assertEqual(self.client.patch('/api/report-settings/order_transcript',json={
            'title':'Updated','format':'A3','orientation':'L','download':True,'prohibitions':['1']
        }).status_code,200)
        self.assertEqual(self.client.get('/api/report-settings/order_transcript').json()['item']['prohibitions'],['1'])
        self.assertEqual(self.client.patch('/api/report-settings/order_transcript/params/1',json={'title':'Company','value':'Changed'}).status_code,200)
        self.assertEqual(self.db.get(ReportParam,1).value,'Changed')
        self.assertEqual(self.client.get('/api/report-settings/order_passport/params/1').status_code,404)
        self.permission_mock.return_value=False
        self.assertEqual(self.client.get('/api/report-settings').status_code,403)

    def test_transcript_safe_html_and_download(self):
        self.seed()
        response=self.client.get('/reports/order_transcript/item/1')
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('text/html',response.headers['content-type'])
        self.assertIn('&lt;script&gt;bad&lt;/script&gt;',response.text)
        self.assertNotIn('<script>',response.text)
        self.assertIn('[printing] =&gt; 10',response.text)
        self.db.get(Report,'order_transcript').download=True; self.db.commit()
        self.assertIn('attachment',self.client.get('/reports/order_transcript/item/1').headers['content-disposition'])

    def test_status_blocking_and_unported_formats_explicit(self):
        self.seed()
        actions=self.client.get('/api/reports/for/orders/1').json()['items']
        self.assertTrue(next(x for x in actions if x['id']=='order_passport')['available'])
        passport = self.client.get('/reports/order_passport/item/1')
        self.assertEqual(passport.status_code,200,passport.text)
        self.assertEqual(passport.headers['content-type'],'application/pdf')
        report=self.db.get(Report,'order_transcript'); report.prohibitions='1'; self.db.commit()
        self.assertEqual(self.client.get('/reports/order_transcript/item/1').status_code,403)
        self.assertTrue(next(x for x in self.client.get('/api/reports/for/orders/1').json()['items'] if x['id']=='order_transcript')['blocked'])

    def test_passport_pdf_contains_core_order_data(self):
        self.seed()
        report = self.db.get(Report, 'order_passport')
        report.download = True
        self.db.add(Blank(id=1, order_id=1, title='Обложка', colors_front=4, colors_back=0, cost=12))
        self.db.commit()
        self.db.get(Order, 1).calc_details = dumps({'blanks': {'1': {'cost': 12, 'details': {'paper': {'print_list_count': 3}}}}})
        self.db.commit()
        response = self.client.get('/reports/order_passport/item/1')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-type'], 'application/pdf')
        self.assertIn('attachment', response.headers['content-disposition'])
        reader = PdfReader(__import__('io').BytesIO(response.content))
        self.assertEqual(len(reader.pages), 1)
        text = reader.pages[0].extract_text()
        self.assertIn('Паспорт заказа', text)
        self.assertIn('Обложка', text)

    def test_economy_workbook_contains_sections_and_totals(self):
        self.seed()
        self.db.get(Order, 1).calc_details = dumps({
            'blanks': {'1': {'cost': 12, 'details': {'title': 'Лист', 'paper': {'paper_list_count': 3}, 'print': {'colors_front': 4, 'colors_back': 0}}}},
            'design': [{'title': 'Макет', 'quantity': 1, 'cost': 5}],
            'other_works': [{'title': 'Упаковка', 'quantity': 2, 'cost': 4}],
        })
        self.db.commit()
        response = self.client.get('/reports/order_economy/item/1')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-type'], 'application/vnd.ms-excel')
        workbook = xlrd.open_workbook(file_contents=response.content)
        sheet = workbook.sheet_by_name('Экономика')
        values = sheet._cell_values
        values = [cell for row in values for cell in row]
        self.assertIn('Заготовки и печать', values)
        self.assertIn('Работы', values)
        self.assertIn('ИТОГО рассчитанная стоимость', values)
        self.assertIn('Макет', values)

    def test_bill_order_report_collection_preserves_order_and_status(self):
        self.seed()
        self.db.add_all([
            Order(id=2, title='Second', status_id=2, order_type='book', printing=5, calc_details=dumps({'blanks': {}})),
            Report(id='blocked_report', program='ipc', kind='pdf', title='Blocked', model='App\\Order', model_title='Заказ', prohibitions='2'),
        ])
        self.db.get(Order, 1).bill_id = 10
        self.db.get(Order, 2).bill_id = 10
        self.db.add(Bill(id=10, number='B-10', amount=100))
        self.db.add(OrderStatus(id=2, title='Ready', sequence=2))
        self.db.commit()
        result = self.client.get('/api/reports/bills/10/orders')
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual([item['id'] for item in result.json()['items']], [1, 2])
        reports = result.json()['items'][1]['reports']
        self.assertEqual({item['id'] for item in reports}, {'order_economy', 'order_passport'})
        self.assertTrue(all(item['available'] for item in reports))

    def test_wide_economy_report_adds_wide_section(self):
        self.seed()
        self.db.get(Order, 1).order_type = 'wide'
        self.db.get(Order, 1).calc_details = dumps({
            'blanks': {'1': {'cost': 18, 'details': {'title': 'Панель', 'width': 1000, 'height': 500, 'paper': {'material_count': 2}, 'print': {'steps_count': 1}}}},
        })
        self.db.commit()
        response = self.client.get('/reports/order_economy/item/1')
        self.assertEqual(response.status_code, 200, response.text)
        sheet = xlrd.open_workbook(file_contents=response.content).sheet_by_name('Экономика')
        values = [cell for row in sheet._cell_values for cell in row]
        self.assertIn('Широкоформатная печать', values)
        self.assertIn('Панель', values)

    def test_wide_passport_pdf_adds_wide_section(self):
        self.seed()
        self.db.get(Order, 1).order_type = 'wide'
        self.db.add(Blank(id=1, order_id=1, title='Панель', width=1000, height=500, colors_front=1, colors_back=0))
        self.db.commit()
        self.db.get(Order, 1).calc_details = dumps({
            'blanks': {'1': {'cost': 18, 'details': {'width': 1000, 'height': 500, 'paper': {'material_count': 2}, 'print': {'steps_count': 1}}}},
        })
        self.db.commit()
        response = self.client.get('/reports/order_passport/item/1')
        self.assertEqual(response.status_code, 200, response.text)
        text = PdfReader(__import__('io').BytesIO(response.content)).pages[0].extract_text()
        self.assertIn('Широкоформатное производство', text)
        self.assertIn('Панель', text)

    def test_design_xls_applies_legacy_half_cost_and_exposes_order_data(self):
        self.seed()
        self.db.add(Blank(id=1, order_id=1, title='Обложка', colors_front=4, colors_back=0))
        self.db.add(OrderMarkup(order_id=1, markup_type='design', value=10, active=False))
        self.db.commit()
        self.db.get(Order, 1).calc_details = dumps({
            'design': [{'title': 'Макет', 'cost': 100}],
            'markups': {'design': {'markup': 90}},
        })
        self.db.commit()
        response = self.client.get('/reports/order_design/item/1')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-type'], 'application/vnd.ms-excel')
        sheet = xlrd.open_workbook(file_contents=response.content).sheet_by_name('Наряд-заказ')
        values = [cell for row in sheet._cell_values for cell in row]
        self.assertIn('Наряд-заказ', values)
        self.assertIn('Обложка', values)
        self.assertIn('Стоимость наряд-заказа', values)
        total_row = next(index for index in range(sheet.nrows) if sheet.cell_value(index, 0) == 'Стоимость наряд-заказа')
        self.assertAlmostEqual(sheet.cell_value(total_row, 7), 55)
        self.assertIn('Проверка макета', values)
        self.assertIn('Пожелания / Проблема', values)

    def test_payment_xls_uses_bill_orders_and_report_parameters(self):
        self.seed()
        bill = Bill(id=20, number='INV-20', bill_date=__import__('datetime').date(2024, 2, 3), amount=150)
        order = Order(id=21, title='Printed forms', status_id=1, printing=3, total=150, bill_id=20)
        manager = User(id=22, name='Manager', surname='Test', email='manager', password='unused', phone='123')
        self.db.add_all([bill, order, manager, ReportParam(id=2, alias='prorector', report_id='order_payment', title='Prorector', value='A'), ReportParam(id=3, alias='zam_prorectora', report_id='order_payment', title='Deputy', value='B'), ReportParam(id=4, alias='boss', report_id='order_payment', title='Boss', value='C'), ReportParam(id=5, alias='buh', report_id='order_payment', title='Accountant', value='D'), ReportParam(id=6, alias='pfu', report_id='order_payment', title='PFU', value='E')])
        self.db.commit()
        self.auth_mock.return_value = manager
        response = self.client.get('/reports/order_payment/item/20')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-type'], 'application/vnd.ms-excel')
        sheet = xlrd.open_workbook(file_contents=response.content).sheet_by_name('Заявка на оплату')
        values = [cell for row in sheet._cell_values for cell in row]
        self.assertIn('Заявка на оплату работ №INV-20', values)
        self.assertIn('Заказ № 21 от УрФУ: Printed forms', values)
        self.assertIn('ИТОГО', values)
        posted = self.client.post('/reports/order_payment/item/20', data={'vars[institute]': 'Институт', 'vars[customer]': 'Заказчик'})
        self.assertEqual(posted.status_code, 200, posted.text)
        posted_sheet = xlrd.open_workbook(file_contents=posted.content).sheet_by_name('Заявка на оплату')
        self.assertTrue(any('Институт' in str(cell) for row in posted_sheet._cell_values for cell in row))

    def test_shipping_pdf_uses_bill_orders_and_signatory_parameters(self):
        self.seed()
        bill = Bill(id=30, number='INV-30', bill_date=__import__('datetime').date(2024, 3, 4), amount=275)
        manager = User(id=31, name='Manager', surname='Shipping', email='shipping', password='unused', phone='123')
        orders = [
            Order(id=32, title='Shipment one', status_id=1, printing=5, total=125, bill_id=30, user_id=31),
            Order(id=33, title='Shipment two', status_id=1, printing=10, total=150, bill_id=30, user_id=31),
        ]
        shipping = Report(id='order_shipping', program='ipc', kind='pdf', title='Документ на отгрузку', model='App\\Bill', model_title='Счет', format='A4', orientation='P', download=True)
        params = [
            ReportParam(id=10, alias='boss', report_id='order_shipping', title='Директор', value='Director'),
            ReportParam(id=11, alias='pto', report_id='order_shipping', title='Начальник производства', value='Production'),
            ReportParam(id=12, alias='buh', report_id='order_shipping', title='Бухгалтер', value='Accountant'),
        ]
        self.db.add_all([bill, manager, *orders, shipping, *params])
        self.db.commit()
        response = self.client.get('/reports/order_shipping/item/30')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-type'], 'application/pdf')
        self.assertIn('attachment', response.headers['content-disposition'])
        text = PdfReader(__import__('io').BytesIO(response.content)).pages[0].extract_text()
        self.assertIn('ТРЕБОВАНИЕ-НАКЛАДНАЯ', text)
        self.assertIn('Shipment one', text)
        self.assertIn('Shipment two', text)
        self.assertIn('275.00', text)
        self.assertIn('Production', text)
        self.assertIn('Accountant', text)

        actions = self.client.get('/api/reports/for/bills/30').json()['items']
        self.assertTrue(next(item for item in actions if item['id'] == 'order_shipping')['available'])
        form = self.client.get('/api/reports/form/order_shipping/30')
        self.assertEqual(form.status_code, 200)
        self.assertEqual(form.json()['fields'][0]['name'], 'vars[buh]')
        self.assertEqual(form.json()['fields'][0]['options'], ['Accountant'])
        custom = self.client.post('/reports/order_shipping/item/30', data={'vars[buh]': 'Custom accountant'})
        self.assertEqual(custom.status_code, 200, custom.text)
        custom_text = PdfReader(__import__('io').BytesIO(custom.content)).pages[0].extract_text()
        self.assertIn('Custom accountant', custom_text)

    def test_corrupt_objects_and_unauthenticated_generation(self):
        self.seed()
        self.db.get(Order,1).calc_details='O:3:"Foo":0:{}'; self.db.commit()
        self.assertEqual(self.client.get('/reports/order_transcript/item/1').status_code,422)
        self.auth_mock.return_value=None
        self.assertEqual(self.client.get('/reports/order_transcript/item/1').status_code,401)