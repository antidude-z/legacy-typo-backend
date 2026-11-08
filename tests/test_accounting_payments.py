import unittest
from tests import test_reference_dictionaries as fixtures
from app.models import Bill, Payment


class PaymentTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def bills(self):
        self.db.add_all([Bill(id=1,number='A',amount=100),Bill(id=2,number='B',amount=200)])
        self.db.commit()
        return '/api/accounting/bills/1/payments'

    def test_create_update_sums_and_manual_paid_flag(self):
        base = self.bills()
        self.client.get(base+'/form')
        self.assertEqual(self.db.query(Payment).count(),0)
        response = self.client.post(base,json={'payment_amount':'25.50','payment_date':'03.01.2024'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['location'],'/accounting/bills/1/edit')
        identity = response.json()['id']; target = f'{base}/{identity}'
        self.assertEqual(self.client.get(target).json()['item']['payment_date'],'2024-01-03')
        self.assertEqual(self.db.get(Payment,identity).customer_id,0)
        result = self.client.get('/api/accounting/bills/1').json()['item']
        self.assertEqual(result['paid_sum'],'25.50'); self.assertFalse(result['paid'])
        self.assertEqual(self.client.patch(target,json={'amount':'40','payment_date':'2024-01-04'}).status_code,200)
        self.assertEqual(self.client.get('/api/accounting/bills/1').json()['item']['paid_sum'],'40.00')
        self.client.delete(target)
        self.assertEqual(self.client.get('/api/accounting/bills/1').json()['item']['paid_sum'],'0')
        self.assertEqual(self.client.post(target+'/restore').status_code,200)
        self.assertEqual(self.client.get('/api/accounting/bills/1').json()['item']['paid_sum'],'40.00')

    def test_parent_ownership_and_validation(self):
        base = self.bills()
        identity = self.client.post(base,json={'amount':10,'payment_date':'2024-01-01'}).json()['id']
        other = f'/api/accounting/bills/2/payments/{identity}'
        self.assertEqual(self.client.get(other).status_code,404)
        self.assertEqual(self.client.patch(other,json={'amount':20,'payment_date':'2024-01-01'}).status_code,404)
        self.assertEqual(self.client.delete(other).status_code,404)
        self.assertEqual(self.client.post(other+'/restore').status_code,404)
        for payload in ({'amount':'NaN','payment_date':'2024-01-01'},{'amount':'1.001','payment_date':'2024-01-01'},{'amount':1,'payment_date':'31.02.2024'}):
            self.assertEqual(self.client.post(base,json=payload).status_code,422)

    def test_permissions_deleted_bill_and_permanent_delete(self):
        base = self.bills()
        identity = self.client.post(base,json={'amount':10,'payment_date':'2024-01-01'}).json()['id']
        target = f'{base}/{identity}'
        self.permission_mock.side_effect = lambda p:p == 'view_accounting_bills'
        self.assertEqual(self.client.get(target).status_code,200)
        self.assertEqual(self.client.post(base,json={}).status_code,403)
        self.permission_mock.side_effect = None
        self.client.delete(target)
        self.permission_mock.side_effect = lambda p:p in {'view_accounting_bills','edit_accounting_bills'}
        self.assertEqual(self.client.get(target).status_code,404)
        self.assertEqual(self.client.post(target+'/restore').status_code,403)
        self.assertEqual(self.client.delete(target).status_code,403)
        self.permission_mock.side_effect = None
        self.assertEqual(self.client.delete(target).status_code,200)
        self.assertIsNone(self.db.get(Payment,identity))
        self.client.delete('/api/accounting/bills/1')
        self.assertEqual(self.client.post(base,json={'amount':10,'payment_date':'2024-01-01'}).status_code,404)
        self.auth_mock.return_value = None
        self.assertEqual(self.client.get(base+'/form').status_code,401)