import unittest
from tests.test_reference_dictionaries import ReferenceDictionaryTests
from app.models import Printer


class ReferencePrinterTests(ReferenceDictionaryTests):
    def test_printer_lifecycle_and_flags(self):
        created = self.client.post('/api/references/printers/create')
        self.assertEqual(created.status_code, 200)
        identity = created.json()['id']
        payload = {'title': 'RICOH', 'need_imagesetter': True, 'production_poly': True, 'production_wide': False}
        self.assertEqual(self.client.patch(f'/api/references/printers/{identity}', json=payload).status_code, 200)
        detail = self.client.get(f'/api/references/printers/{identity}').json()['item']
        self.assertTrue(detail['need_imagesetter'] and detail['production_poly'])
        self.assertEqual(self.client.delete(f'/api/references/printers/{identity}').status_code, 200)
        self.assertEqual(self.client.post(f'/api/references/printers/{identity}/restore').status_code, 200)

    def test_printer_validation_and_permissions(self):
        created = self.client.post('/api/references/printers/create').json()['id']
        self.assertEqual(self.client.patch(f'/api/references/printers/{created}', json={'title': ''}).status_code, 422)
        self.permission_mock.return_value = False
        self.assertEqual(self.client.post(f'/api/references/printers/{created}/restore').status_code, 403)


if __name__ == '__main__':
    unittest.main()