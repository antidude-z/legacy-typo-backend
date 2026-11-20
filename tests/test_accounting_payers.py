import unittest
from tests import test_reference_dictionaries as fixtures
from app.models import Payer


class PayerTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def test_form_does_not_create_row_and_crud_preserves_inn(self):
        self.assertEqual(self.client.get('/api/accounting/payers/form').status_code, 200)
        self.assertEqual(self.db.query(Payer).count(), 0)
        payload = {'payer_title':'Company', 'payer_profit':5, 'payer_inn':'001234', 'payer_phone':'123', 'payer_address':'Address', 'payer_description':'Notes'}
        response = self.client.post('/api/accounting/payers', json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        identity = response.json()['id']; target = f'/api/accounting/payers/{identity}'
        self.assertEqual(self.client.get(target).json()['item']['inn'], '001234')
        self.assertEqual(self.client.patch(target, json={**payload,'payer_profit':10}).status_code, 200)
        self.assertEqual(self.db.get(Payer,identity).profit, 10)

    def test_validation_sorting_and_auth(self):
        for changes in ({'title':''}, {'profit':'bad'}, {'profit':'1.5'}, {'inn':'0'*13}):
            self.assertEqual(self.client.post('/api/accounting/payers', json={'title':'Company','profit':5,**changes}).status_code, 422)
        for title,profit in [('B',10),('A',5)]:
            self.client.post('/api/accounting/payers',json={'title':title,'profit':profit})
        result = self.client.get('/api/accounting/payers?sort=profit&order=asc&per_page=1').json()
        self.assertEqual(result['items'][0]['title'],'A')
        self.assertEqual(result['last_page'],2)
        self.auth_mock.return_value = None
        self.assertEqual(self.client.get('/api/accounting/payers').status_code,401)

    def test_soft_delete_visibility_restore_and_permanent_delete(self):
        identity = self.client.post('/api/accounting/payers',json={'title':'Company','profit':0}).json()['id']
        target = f'/api/accounting/payers/{identity}'
        self.client.delete(target)
        self.permission_mock.side_effect = lambda name: name == 'view_menu_accounting_payers'
        self.assertEqual(self.client.get(target).status_code,404)
        self.assertEqual(self.client.get('/api/accounting/payers').json()['items'],[])
        self.assertEqual(self.client.post(target+'/restore').status_code,403)
        self.assertEqual(self.client.delete(target).status_code,403)
        self.permission_mock.side_effect = None
        self.permission_mock.return_value = True
        self.assertEqual(self.client.post(target+'/restore').status_code,200)
        self.client.delete(target)
        self.assertEqual(self.client.delete(target).status_code,200)
        self.assertIsNone(self.db.get(Payer,identity))