import unittest
from tests import test_reference_dictionaries as fixtures
from app.models import Compile, CompileStage, Material


class CompileReferenceTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def create(self):
        result = self.client.post('/api/references/compiles', json={'title':'Binding', 'fitting':5, 'production_poly':True})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()['id']

    def test_definition_create_update_and_lifecycle(self):
        identity = self.create()
        base = f'/api/references/compiles/{identity}'
        self.assertEqual(self.client.get(base).json()['item']['fitting'], 5)
        self.assertEqual(self.client.patch(base, json={'title':'Binding updated', 'fitting':10, 'production_book':True}).status_code, 200)
        self.assertEqual(self.client.patch(base, json={'title':'', 'fitting':0}).status_code, 422)
        self.client.delete(base)
        self.permission_mock.return_value = False
        self.assertEqual(self.client.get(base).status_code, 404)
        self.assertEqual(self.client.post(base + '/restore').status_code, 403)
        self.assertEqual(self.client.delete(base).status_code, 403)
        self.permission_mock.return_value = True
        self.assertEqual(self.client.post(base + '/restore').status_code, 200)
        self.client.delete(base)
        self.assertEqual(self.client.delete(base).status_code, 200)
        self.assertIsNone(self.db.get(Compile, identity))

    def test_stage_defaults_order_scope_and_material_precision(self):
        identity = self.create()
        other = self.create()
        base = f'/api/references/compiles/{identity}/stages'
        self.client.get(base + '/form')
        self.assertEqual(self.db.query(CompileStage).count(), 0)
        values = {'title':'Stage', 'together':10, 'waste':0, 'fitting':True}
        first = self.client.post(base, json=values)
        self.assertEqual(first.status_code, 200, first.text)
        stage_id = first.json()['id']
        self.client.post(base, json=values)
        detail = self.client.get(f'/api/references/compiles/{identity}').json()
        self.assertEqual([x['weight'] for x in detail['stages']], [0, 1])
        self.assertNotIn('min_paper_weight', detail['stages'][0])
        self.assertEqual(self.client.get(f'/api/references/compiles/{other}/stages/{stage_id}').status_code, 404)
        self.db.add_all([Material(id=1, title='Glue', production_poly=True), Material(id=2, title='Vinyl', production_wide=True)])
        self.db.commit()
        collection = f'{base}/{stage_id}/materials'
        self.assertEqual([x['id'] for x in self.client.get(collection + '/form').json()['choices']], [1])
        self.assertEqual(self.client.post(collection, json={'material_id':2, 'quantity':'1'}).status_code, 422)
        result = self.client.post(collection, json={'material_id':1, 'quantity':'0.1250'})
        self.assertEqual(result.status_code, 200, result.text)
        item_id = result.json()['id']
        self.assertEqual(self.client.get(f'{collection}/{item_id}').json()['item']['quantity'], '0.1250')
        self.assertEqual(self.client.patch(f'{collection}/{item_id}', json={'material_id':1, 'quantity':'0.25'}).status_code, 200)
        self.client.delete(f'{collection}/{item_id}')
        self.assertEqual(self.client.post(f'{collection}/{item_id}/restore').status_code, 200)

    def test_authentication_and_flag_validation(self):
        self.assertEqual(self.client.post('/api/references/compiles', json={'title':'Work', 'fitting':-1}).status_code, 422)
        self.assertEqual(self.client.post('/api/references/compiles', json={'title':'Work', 'fitting':0, 'production_poly':'invalid'}).status_code, 422)
        self.auth_mock.return_value = None
        self.assertEqual(self.client.get('/api/references/compiles').status_code, 401)