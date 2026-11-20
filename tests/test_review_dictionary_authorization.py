"""S03 per-dictionary real-session capability matrix on disposable data."""
from tests import test_review_employee_authorization as fixtures
from app.reference_dictionaries import DICTIONARIES


class DictionaryAuthorizationReviewTests(fixtures.EmployeeAuthorizationReviewTests):
    def test_dictionary_action_matrix(self):
        for kind, config in DICTIONARIES.items():
            with self.subTest(kind=kind):
                self.role.permissions.clear(); self.db.commit()
                self.grant('view_menu_orders')
                row = config['model'](**{key: 10 if field_type == 'number' else 'Protected'
                                        for key, _, field_type in config['fields']})
                self.db.add(row); self.db.commit()
                base = f'/api/options/{kind}'
                path = f'{base}/{row.id}'
                before = self.snapshot()
                self.assertEqual(self.client.get(base).status_code, 403)
                self.assertEqual(self.client.get(path).status_code, 403)
                self.assertEqual(before, self.snapshot())
                self.grant('view_menu_options_' + kind.replace('-', '_'))
                self.assertEqual(self.client.get(path).status_code, 200)
                payload = {key: 20 if field_type == 'number' else 'Changed'
                           for key, _, field_type in config['fields']}
                before = self.snapshot()
                for method, target in [('POST', base), ('POST', base + '/create'),
                                       ('PATCH', path), ('DELETE', path),
                                       ('POST', path + '/restore')]:
                    response = self.client.request(method, target, json=payload, headers=self.headers)
                    self.assertEqual(response.status_code, 403, (kind, method, response.text))
                self.assertEqual(before, self.snapshot())
                suffix = kind.replace('-', '_')
                self.grant(f'edit_dictionary_{suffix}')
                self.assertEqual(self.client.patch(path, json=payload, headers=self.headers).status_code, 200)
                self.grant('restore_trashed', 'delete_trashed', 'view_trashed')
                before = self.snapshot()
                self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 403)
                self.assertEqual(self.client.post(path + '/restore', headers=self.headers).status_code, 403)
                self.assertEqual(before, self.snapshot())
                self.grant(f'delete_dictionary_{suffix}')
                self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
                self.assertEqual(self.client.post(path + '/restore', headers=self.headers).status_code, 200)
                self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
                self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
                self.assertIsNone(self.db.get(config['model'], row.id))

    def test_dictionary_writer_does_not_gain_another_dictionary(self):
        self.grant('view_menu_options_paper_type', 'edit_dictionary_paper_type',
                   'delete_dictionary_paper_type', 'restore_trashed', 'delete_trashed')
        before = self.snapshot()
        for kind in ('paper-format', 'measures', 'customer-group'):
            self.assertEqual(self.client.get(f'/api/options/{kind}').status_code, 403)
            self.assertEqual(self.client.post(f'/api/options/{kind}/create', headers=self.headers).status_code, 403)
        self.assertEqual(before, self.snapshot())