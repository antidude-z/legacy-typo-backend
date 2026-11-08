import unittest
from tests import test_reference_dictionaries as fixtures
from app.models import Afterprint, AfterprintParameter, AfterprintParameterValue, AfterprintStage, AfterprintStageMaterial, Material


class AfterprintReferenceTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def seed(self):
        self.db.add_all([
            Afterprint(id=1, title='Finish', production_poly=True), Afterprint(id=2, title='Other'),
            AfterprintParameter(id=1, afterprint_id=1, title='Count', value='1', parameter_type='select'),
            AfterprintParameterValue(afterprint_parameter_id=1, value='One', weight=1),
            Material(id=1, title='Glue', production_poly=True), Material(id=2, title='Vinyl', production_wide=True),
        ])
        self.db.commit()
        return '/api/references/afterprints/1'

    def test_definition_edit_and_read_only_parameters(self):
        base = self.seed()
        self.assertEqual(self.client.patch(base, json={'title':'Finish updated', 'tooltip':'Help'}).status_code, 200)
        detail = self.client.get(base).json()
        self.assertEqual(detail['parameters'][0]['values'][0]['value'], 'One')
        self.assertEqual(detail['item']['tooltip'], 'Help')
        self.assertEqual(self.client.patch(base, json={'title':''}).status_code, 422)

    def test_stage_creation_order_validation_and_scope(self):
        base = self.seed()
        values = {'title':'Setup', 'together':100, 'waste':2, 'min_paper_weight':80, 'max_paper_weight':'', 'fitting':True}
        self.client.get(base + '/stages/form')
        self.assertEqual(self.db.query(AfterprintStage).count(), 0)
        first = self.client.post(base + '/stages', json=values)
        self.assertEqual(first.status_code, 200, first.text)
        identity = first.json()['id']
        self.client.post(base + '/stages', json={**values, 'title':'Finish'})
        self.assertEqual([x['weight'] for x in self.client.get(base).json()['stages']], [0, 1])
        self.assertIsNone(self.db.get(AfterprintStage, identity).max_paper_weight)
        self.assertEqual(self.client.patch(f'/api/references/afterprints/2/stages/{identity}', json=values).status_code, 404)
        self.assertEqual(self.client.post(base + '/stages', json={**values, 'max_paper_weight':40}).status_code, 422)

    def test_material_choices_precision_and_lifecycle_permissions(self):
        base = self.seed()
        stage = self.client.post(base + '/stages', json={'title':'Stage', 'together':1, 'waste':0}).json()['id']
        collection = f'{base}/stages/{stage}/materials'
        self.assertEqual([row['id'] for row in self.client.get(collection + '/form').json()['choices']], [1])
        self.assertEqual(self.client.post(collection, json={'material_id':2, 'quantity':'1'}).status_code, 422)
        result = self.client.post(collection, json={'material_id':1, 'quantity':'0.1250'})
        self.assertEqual(result.status_code, 200, result.text)
        identity = result.json()['id']
        self.assertEqual(self.client.get(f'{collection}/{identity}').json()['item']['quantity'], '0.1250')
        self.client.delete(f'{collection}/{identity}')
        self.permission_mock.return_value = False
        self.assertEqual(self.client.get(f'{collection}/{identity}').status_code, 404)
        self.assertEqual(self.client.post(f'{collection}/{identity}/restore').status_code, 403)
        self.permission_mock.return_value = True
        self.assertEqual(self.client.post(f'{collection}/{identity}/restore').status_code, 200)
        self.client.delete(f'{collection}/{identity}')
        self.assertEqual(self.client.delete(f'{collection}/{identity}').status_code, 200)
        self.assertIsNone(self.db.get(AfterprintStageMaterial, identity))

    def test_afterprint_schema_upgrade_preserves_rows(self):
        from unittest.mock import patch
        from sqlalchemy import create_engine, text
        from app.schema import upgrade_local_schema
        engine = create_engine('sqlite:///:memory:')
        try:
            with engine.begin() as connection:
                connection.execute(text('CREATE TABLE afterprints (id INTEGER PRIMARY KEY, title TEXT)'))
                connection.execute(text("INSERT INTO afterprints VALUES (1, 'Existing')"))
            with patch('app.schema.engine', engine):
                upgrade_local_schema(); upgrade_local_schema()
            with engine.connect() as connection:
                self.assertEqual(tuple(connection.execute(text('SELECT title, weight, production_poly FROM afterprints')).one()), ('Existing', 0, 0))
        finally:
            engine.dispose()