"""S03 paper/material action boundaries with real sessions on disposable data."""
from app.models import Material, Measure, Paper, PaperFormat, PaperType
from tests import test_review_employee_authorization as fixtures


class InventoryAuthorizationReviewTests(fixtures.EmployeeAuthorizationReviewTests):
    def test_inventory_action_matrix(self):
        self.db.add_all([PaperType(id=1, title='Type'),
                         PaperFormat(id=1, title='A4', width=210, height=297),
                         Measure(id=1, title='Unit', short='u')]); self.db.commit()
        for kind, model, values, create in (
            ('paper', Paper, {'type_id': 1, 'format_id': 1, 'weight': 80, 'markup': 10}, '/create'),
            ('materials', Material, {'title': 'Material', 'measure_id': 1, 'work_type': 'print'}, ''),
        ):
            with self.subTest(kind=kind):
                self.role.permissions.clear(); self.db.commit()
                self.grant('view_menu_orders', 'edit_orders')
                row = model(**({'title': 'Paper'} | values)); self.db.add(row); self.db.commit()
                base = f'/api/references/{kind}'
                path = f'{base}/{row.id}'
                before = self.snapshot()
                self.assertEqual(self.client.get(base).status_code, 403)
                self.assertEqual(self.client.get(path).status_code, 403)
                self.assertEqual(before, self.snapshot())
                self.grant(f'view_menu_references_{kind}')
                self.assertEqual(self.client.get(path).status_code, 200)
                self.assertFalse(self.client.get(path).json()['can_edit'])
                before = self.snapshot()
                for method, target in [('POST', base + create), ('PATCH', path),
                                       ('DELETE', path), ('POST', path + '/restore')]:
                    response = self.client.request(method, target, headers=self.headers, json=values)
                    self.assertEqual(response.status_code, 403, (kind, method, response.text))
                self.assertEqual(before, self.snapshot())
                if kind == 'materials':
                    self.assertEqual(self.client.post(base + '/filter', headers=self.headers,
                        json={'filter_text': 'Material'}).status_code, 200)
                self.grant(f'edit_reference_{kind}')
                self.assertTrue(self.client.get(base + '/form/options').json()['can_edit'])
                self.assertEqual(self.client.patch(path, headers=self.headers, json=values).status_code, 200)
                self.assertEqual(self.client.post(base + create, headers=self.headers, json=values).status_code, 200)
                self.grant('view_trashed', 'restore_trashed', 'delete_trashed')
                before = self.snapshot()
                self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 403)
                self.assertEqual(self.client.post(path + '/restore', headers=self.headers).status_code, 403)
                self.assertEqual(before, self.snapshot())
                self.grant(f'delete_reference_{kind}')
                self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
                self.assertEqual(self.client.post(path + '/restore', headers=self.headers).status_code, 200)
                self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
                self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
                self.assertIsNone(self.db.get(model, row.id))