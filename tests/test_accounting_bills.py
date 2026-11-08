import unittest
from datetime import date, datetime
from tests import test_reference_dictionaries as fixtures
from app.models import Bill, Order, Payer, Payment, User


class BillTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def seed(self):
        self.db.add_all([Payer(id=1,title='Company'), User(id=20,name='Ivan',surname='Ivanov',email='manager@test',password='unused')])
        self.db.commit()
        return {'bill_number':'001-A','bill_date':'02.01.2024','bill_manager':20,'bill_payer':1,'bill_amount':'123.45','bill_currency':'RUB','bill_paid':False}

    def test_bill_crud_and_payment_total_separate_from_status(self):
        payload = self.seed()
        response = self.client.post('/api/accounting/bills',json=payload)
        self.assertEqual(response.status_code,200,response.text)
        identity = response.json()['id']; target = f'/api/accounting/bills/{identity}'
        self.db.add_all([Payment(bill_id=identity,amount=10,payment_date=date(2024,1,3)),Payment(bill_id=identity,amount=50,payment_date=date(2024,1,3),deleted_at=datetime.now()),Order(title='Linked',order_type='poly',status_id=1,printing=0,total=5,bill_id=identity)])
        self.db.commit()
        result = self.client.get(target).json()
        self.assertEqual(result['item']['paid_sum'],'10.00')
        self.assertFalse(result['item']['paid'])
        self.assertEqual(result['orders'][0]['price'],'0')
        self.assertEqual(result['orders_total'],'5.00')
        self.assertEqual(self.client.patch(target,json={**payload,'bill_closed':True}).status_code,200)
        self.assertTrue(self.db.get(Bill,identity).closed)

    def test_filters_search_and_invalid_values(self):
        payload = self.seed()
        self.client.post('/api/accounting/bills',json=payload)
        for change in ({'bill_amount':'NaN'},{'bill_date':'wrong'},{'bill_payer':999},{'bill_number':''}):
            self.assertEqual(self.client.post('/api/accounting/bills',json={**payload,**change}).status_code,422)
        self.client.post('/api/accounting/bills/filter',json={'filter_text':'missing'})
        self.assertEqual(self.client.get('/api/accounting/bills').json()['items'],[])
        self.client.post('/api/accounting/bills/filter',json={'flush':True})
        self.assertEqual(len(self.client.get('/api/accounting/bills').json()['items']),1)
        result = self.client.get('/api/accounting/bills/search?search=001%20Company').json()
        self.assertEqual(len(result),2)
        self.assertIn('001-A',result[1]['text'])

    def test_permissions_restore_and_permanent_delete(self):
        identity = self.client.post('/api/accounting/bills',json=self.seed()).json()['id']
        target = f'/api/accounting/bills/{identity}'
        self.client.delete(target)
        self.permission_mock.side_effect = lambda permission: permission in {'view_accounting_bills','edit_accounting_bills'}
        self.assertEqual(self.client.get(target).status_code,404)
        self.assertEqual(self.client.post(target+'/restore').status_code,403)
        self.assertEqual(self.client.delete(target).status_code,403)
        self.permission_mock.side_effect = None
        self.assertEqual(self.client.post(target+'/restore').status_code,200)
        self.permission_mock.return_value = False
        self.assertEqual(self.client.patch(target,json=self.seed_payload()).status_code,403)

    def seed_payload(self):
        return {'number':'x','bill_date':'2024-01-01','amount':'1'}

    def test_invalid_filter_never_replaces_valid_session_filter(self):
        self.client.post('/api/accounting/bills',json=self.seed())
        self.client.post('/api/accounting/bills/filter',json={'filter_text':'001'})
        for changes in ({'filter_date_from':['invalid']}, {'filter_manager':-1},
                        {'filter_date_from':'2024-02-01','filter_date_to':'2024-01-01'}):
            self.assertEqual(self.client.post('/api/accounting/bills/filter',json=changes).status_code,422)
        self.assertEqual(self.client.get('/api/accounting/bills').json()['filter']['filter_text'],'001')

    def test_customer_payer_relationship_storage_without_invented_editor(self):
        from app.models import Customer
        payer = Payer(title='Company')
        customer = Customer(title='Client',payers=[payer])
        self.db.add(customer); self.db.commit(); self.db.expire_all()
        self.assertEqual(self.db.get(Customer,customer.id).payers[0].title,'Company')
        self.assertEqual(self.db.get(Payer,payer.id).customers[0].title,'Client')

    def test_existing_bill_upgrade_preserves_number(self):
        from unittest.mock import patch
        from sqlalchemy import create_engine, text
        from app.schema import upgrade_local_schema
        engine = create_engine('sqlite:///:memory:')
        try:
            with engine.begin() as connection:
                connection.execute(text('CREATE TABLE bills (id INTEGER PRIMARY KEY, number TEXT)'))
                connection.execute(text("INSERT INTO bills VALUES (1, '001-A')"))
            with patch('app.schema.engine',engine):
                upgrade_local_schema(); upgrade_local_schema()
            with engine.connect() as connection:
                self.assertEqual(tuple(connection.execute(text('SELECT number, amount, currency FROM bills')).one()),('001-A',0,'RUB'))
        finally:
            engine.dispose()