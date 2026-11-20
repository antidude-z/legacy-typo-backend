import unittest
from tests import test_reference_dictionaries as fixtures
from app.models import Printer, PrinterField, PrinterProcess, PrinterProcessStage


class PrinterChildrenTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def seed_printers(self):
        self.db.add_all([Printer(id=1, title='Press'), Printer(id=2, title='Other')])
        self.db.commit()

    def test_process_stage_defaults_order_and_lifecycle(self):
        self.seed_printers()
        base = '/api/references/printers/1/processes'
        response = self.client.post(base + '/create')
        self.assertEqual(response.status_code, 200, response.text)
        process = response.json()['item']
        self.assertEqual((process['colors_front'], process['colors_back']), (1, 0))
        process_id = process['id']
        payload = {'title':'4+4', 'colors_front':4, 'colors_back':4, 'rejection':2, 'resolution':720}
        self.assertEqual(self.client.patch(f'{base}/{process_id}', json=payload).status_code, 200)
        stages = f'{base}/{process_id}/stages'
        first = self.client.post(stages + '/create').json()['item']
        second = self.client.post(stages + '/create').json()['item']
        self.assertEqual((first['weight'], second['weight']), (0, 1))
        stage_id = first['id']
        values = {'title':'Setup', 'together':1000, 'colors':1, 'waste':20}
        self.assertEqual(self.client.patch(f'{stages}/{stage_id}', json=values).status_code, 200)
        self.assertEqual(self.client.get(stages + '/items').json()['items'][0]['title'], 'Setup')
        self.assertEqual(self.client.delete(f'{stages}/{stage_id}').status_code, 200)
        self.permission_mock.side_effect = lambda name: name == 'view_menu_references_printers'
        self.assertEqual(self.client.get(f'{stages}/{stage_id}').status_code, 404)
        self.assertEqual(self.client.post(f'{stages}/{stage_id}/restore').status_code, 403)
        self.assertEqual(self.client.delete(f'{stages}/{stage_id}').status_code, 403)
        self.permission_mock.side_effect = None
        self.permission_mock.return_value = True
        self.assertEqual(self.client.post(f'{stages}/{stage_id}/restore').status_code, 200)
        self.client.delete(f'{stages}/{stage_id}')
        self.assertEqual(self.client.delete(f'{stages}/{stage_id}').status_code, 200)
        self.assertIsNone(self.db.get(PrinterProcessStage, stage_id))

    def test_fields_no_draft_validation_and_scope(self):
        self.seed_printers()
        base = '/api/references/printers/1/fields'
        self.assertEqual(self.client.post(base + '/create').status_code, 200)
        self.assertEqual(self.db.query(PrinterField).count(), 0)
        payload = {'paper_format_id':1, 'pieces':2, 'width':200, 'height':280, 'paper_width':210, 'paper_height':297}
        response = self.client.post(base, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        identity = response.json()['id']
        self.assertEqual(self.client.get(f'{base}/{identity}').json()['item']['format_title'], 'A4')
        for method in ('get', 'delete'):
            self.assertEqual(getattr(self.client, method)(f'/api/references/printers/2/fields/{identity}').status_code, 404)
        self.assertEqual(self.client.post(base, json={**payload, 'pieces':0}).status_code, 422)
        self.assertEqual(self.client.patch(f'{base}/{identity}', json={**payload, 'width':'bad'}).status_code, 422)

    def test_stage_parent_scope_and_authentication(self):
        self.seed_printers()
        process = PrinterProcess(id=1, printer_id=1, title='Process')
        self.db.add(process); self.db.commit()
        self.assertEqual(self.client.post('/api/references/printers/2/processes/1/stages/create').status_code, 404)
        self.auth_mock.return_value = None
        self.assertEqual(self.client.get('/api/references/printers/1/fields/form').status_code, 401)