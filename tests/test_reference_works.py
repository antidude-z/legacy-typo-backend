import unittest
from tests import test_reference_dictionaries as fixtures
from app.models import Prepress, Redaction


class ReferenceWorksTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def test_prepress_and_redaction_crud_lifecycle(self):
        for kind, model, field in [('prepresses', Prepress, 'prepress_title'), ('redactions', Redaction, 'redaction_title')]:
            base = f'/api/reference-works/{kind}'
            created = self.client.post(base, json={field:'Название'}).json()['id']
            self.assertEqual(self.client.get(base).json()['items'][0]['title'], 'Название')
            self.assertEqual(self.client.patch(f'{base}/{created}', json={field:'Обновлено'}).status_code, 200)
            self.assertEqual(self.client.patch(f'{base}/{created}', json={field:''}).status_code, 422)
            self.assertEqual(self.client.delete(f'{base}/{created}').status_code, 200)
            self.permission_mock.return_value = False
            self.assertEqual(self.client.get(f'{base}/{created}').status_code, 403)
            self.assertEqual(self.client.post(f'{base}/{created}/restore').status_code, 403)
            self.permission_mock.return_value = True
            self.assertEqual(self.client.post(f'{base}/{created}/restore').status_code, 200)
            self.assertIsNone(self.db.get(model, created).deleted_at)

    def test_sorting_pagination_and_authentication(self):
        self.client.post('/api/reference-works/prepresses', json={'prepress_title':'A'})
        self.client.post('/api/reference-works/prepresses', json={'prepress_title':'B'})
        result = self.client.get('/api/reference-works/prepresses?sort=title&order=asc&per_page=1').json()
        self.assertEqual(result['items'][0]['title'], 'A')
        self.assertEqual(result['last_page'], 2)
        self.auth_mock.return_value = None
        self.assertEqual(self.client.get('/api/reference-works/prepresses').status_code, 401)

    def test_permanent_delete_requires_permission_and_preserves_other_directory(self):
        identity = self.client.post('/api/reference-works/prepresses', json={'prepress_title':'Work'}).json()['id']
        other = self.client.post('/api/reference-works/redactions', json={'redaction_title':'Editing'}).json()['id']
        target = f'/api/reference-works/prepresses/{identity}'
        self.client.delete(target)
        self.permission_mock.return_value = False
        self.assertEqual(self.client.delete(target).status_code, 403)
        self.permission_mock.return_value = True
        self.assertEqual(self.client.delete(target).status_code, 200)
        self.assertIsNone(self.db.get(Prepress, identity))
        self.assertIsNotNone(self.db.get(Redaction, other))