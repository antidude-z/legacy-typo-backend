import unittest
from tests import test_reference_dictionaries as fixtures
from app.models import Material, Paper


class ReferenceInventoryTests(unittest.TestCase):
    def setUp(self):
        fixtures.ReferenceDictionaryTests.setUp(self)
        token = self.client.get('/api/csrf-token').json()['token']
        self.client.headers['X-CSRF-Token'] = token
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def test_existing_inventory_schema_upgrade_preserves_data(self):
        from unittest.mock import patch
        from sqlalchemy import create_engine, text
        from app.schema import upgrade_local_schema

        engine = create_engine('sqlite:///:memory:')
        try:
            with engine.begin() as connection:
                connection.execute(text('CREATE TABLE papers (id INTEGER PRIMARY KEY, title TEXT)'))
                connection.execute(text("INSERT INTO papers VALUES (1, 'Existing paper')"))
                connection.execute(text('CREATE TABLE materials (id INTEGER PRIMARY KEY, title TEXT)'))
                connection.execute(text("INSERT INTO materials VALUES (1, 'Existing material')"))
            with patch('app.schema.engine', engine):
                upgrade_local_schema()
                upgrade_local_schema()
            with engine.connect() as connection:
                self.assertEqual(tuple(connection.execute(text('SELECT title, markup FROM papers')).one()), ('Existing paper', 10))
                self.assertEqual(tuple(connection.execute(text('SELECT title, work_type, production_wide FROM materials')).one()), ('Existing material', 'print', 0))
        finally:
            engine.dispose()
    def test_paper_draft_update_and_restore(self):
        response = self.client.post('/api/references/paper/create')
        self.assertEqual(response.status_code, 200, response.text)
        identity = response.json()['id']
        payload = {'type_id': 1, 'format_id': 1, 'weight': 120, 'markup': 15}
        self.assertEqual(self.client.patch(f'/api/references/paper/{identity}', json=payload).status_code, 200)
        self.assertEqual(self.db.get(Paper, identity).title, 'Офсет 120 A4')
        self.assertEqual(self.client.delete(f'/api/references/paper/{identity}').status_code, 200)
        self.assertEqual(self.client.post(f'/api/references/paper/{identity}/restore').status_code, 200)

    def test_material_validation_flags_and_filter(self):
        payload = {'title': 'Vinyl', 'measure_id': 1, 'work_type': 'print', 'production_wide': True}
        result = self.client.post('/api/references/materials', json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        identity = result.json()['id']
        self.assertTrue(self.db.get(Material, identity).production_wide)
        self.assertEqual(self.client.post('/api/references/materials', json={**payload, 'measure_id': 'bad'}).status_code, 422)
        self.assertEqual(self.client.patch(f'/api/references/materials/{identity}', json={**payload, 'title': ''}).status_code, 422)
        self.assertEqual(len(self.client.get('/api/references/materials?filter_text=Vin&filter_type=print').json()['items']), 1)
        self.assertEqual(self.client.delete(f'/api/references/materials/{identity}').status_code, 200)
        self.assertEqual(self.client.post(f'/api/references/materials/{identity}/restore').status_code, 200)

    def test_material_filters_persist_and_reset(self):
        self.client.post('/api/references/materials', json={'title': 'Vinyl', 'measure_id': 1, 'work_type': 'print'})
        self.client.post('/api/references/materials/filter', json={'filter_text': 'missing'})
        self.assertEqual(self.client.get('/api/references/materials').json()['items'], [])
        self.client.post('/api/references/materials/filter', json={'flush': True})
        self.assertEqual(len(self.client.get('/api/references/materials').json()['items']), 1)