"""S03 payer capability combinations with real sessions and valid resources."""
from datetime import datetime
from app.models import Payer
from tests import test_review_employee_authorization as fixtures


class PayerAuthorizationReviewTests(fixtures.EmployeeAuthorizationReviewTests):
    def test_reader_writer_and_lifecycle_combinations(self):
        self.grant('view_menu_accounting_payers')
        row = Payer(title='Protected', profit=0)
        deleted = Payer(title='Deleted', profit=0, deleted_at=datetime(2020, 1, 1))
        self.db.add_all([row, deleted]); self.db.commit()
        path = f'/api/accounting/payers/{row.id}'
        trash = f'/api/accounting/payers/{deleted.id}'
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertFalse(self.client.get(path).json()['can_edit'])
        before = self.snapshot()
        for method, target, payload in (
            ('GET', '/api/accounting/payers/form', None),
            ('POST', '/api/accounting/payers', {'title': 'Forbidden', 'profit': 0}),
            ('PATCH', path, {'title': 'Forbidden', 'profit': 0}),
            ('DELETE', path, None), ('DELETE', trash, None),
            ('POST', trash + '/restore', None),
        ):
            response = self.client.request(method, target, json=payload, headers=self.headers)
            self.assertEqual(response.status_code, 403, (method, target, response.text))
        self.assertEqual(before, self.snapshot())
        self.grant('edit_accounting_payers')
        self.assertEqual(self.client.patch(path, headers=self.headers,
            json={'title': 'Allowed', 'profit': 0}).status_code, 200)
        self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 403)
        self.grant('restore_trashed', 'delete_trashed', 'view_trashed')
        before = self.snapshot()
        self.assertEqual(self.client.delete(trash, headers=self.headers).status_code, 403)
        self.assertEqual(self.client.post(trash + '/restore', headers=self.headers).status_code, 403)
        self.assertEqual(before, self.snapshot())
        self.grant('delete_accounting_payers')
        self.assertEqual(self.client.post(trash + '/restore', headers=self.headers).status_code, 200)
        self.assertEqual(self.client.delete(trash, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.delete(trash, headers=self.headers).status_code, 200)
        self.assertIsNone(self.db.get(Payer, deleted.id))

    def test_unrelated_staff_and_delete_only_cannot_access_payers(self):
        self.grant('view_menu_orders', 'delete_accounting_payers', 'restore_trashed', 'delete_trashed')
        row = Payer(title='Protected', profit=0)
        self.db.add(row); self.db.commit()
        before = self.snapshot()
        for method, path in (
            ('GET', '/api/accounting/payers'),
            ('GET', f'/api/accounting/payers/{row.id}'),
            ('DELETE', f'/api/accounting/payers/{row.id}'),
            ('POST', f'/api/accounting/payers/{row.id}/restore'),
        ):
            self.assertEqual(self.client.request(method, path, headers=self.headers).status_code, 403)
        self.assertEqual(before, self.snapshot())