import unittest
from tests import test_reference_dictionaries as fixtures
from app.models import Bill, Order, OrderStatus, Report, ReportParam
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
            ReportParam(id=1,alias='company',report_id='order_transcript',title='Company',value='Original'),
        ])
        self.db.commit()

    def test_catalog_settings_and_parameter_scope(self):
        self.seed()
        self.assertEqual(len(self.client.get('/api/report-settings').json()['items']),2)
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
        self.assertFalse(next(x for x in actions if x['id']=='order_passport')['available'])
        self.assertEqual(self.client.get('/reports/order_passport/item/1').status_code,501)
        report=self.db.get(Report,'order_transcript'); report.prohibitions='1'; self.db.commit()
        self.assertEqual(self.client.get('/reports/order_transcript/item/1').status_code,403)
        self.assertTrue(next(x for x in self.client.get('/api/reports/for/orders/1').json()['items'] if x['id']=='order_transcript')['blocked'])

    def test_corrupt_objects_and_unauthenticated_generation(self):
        self.seed()
        self.db.get(Order,1).calc_details='O:3:"Foo":0:{}'; self.db.commit()
        self.assertEqual(self.client.get('/reports/order_transcript/item/1').status_code,422)
        self.auth_mock.return_value=None
        self.assertEqual(self.client.get('/reports/order_transcript/item/1').status_code,401)