"""S03 customer action matrix: real sessions and disposable SQLite only."""
from datetime import datetime
from app.models import Customer
from tests import test_review_employee_authorization as fixtures


class CustomerAuthorizationReviewTests(fixtures.EmployeeAuthorizationReviewTests):
    def test_customer_reader_writer_and_lifecycle(self):
        self.grant('view_menu_references_customers')
        active = Customer(title='Protected')
        deleted = Customer(title='Deleted', deleted_at=datetime(2020, 1, 1))
        self.db.add_all([active, deleted]); self.db.commit()
        base = '/api/customer-references'
        path, trash = f'{base}/{active.id}', f'{base}/{deleted.id}'
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertFalse(self.client.get(path).json()['can_edit'])
        before = self.snapshot()
        for method, target in [('GET', base + '/form'), ('POST', base),
                               ('PATCH', path), ('DELETE', path),
                               ('DELETE', trash), ('POST', trash + '/restore')]:
            response = self.client.request(method, target, headers=self.headers,
                                           json={'title': 'Forbidden'})
            self.assertEqual(response.status_code, 403, (method, target, response.text))
        self.assertEqual(before, self.snapshot())
        self.grant('edit_reference_customers')
        self.assertEqual(self.client.get(base + '/form').status_code, 200)
        self.assertEqual(self.client.post(base, headers=self.headers,
            json={'title': 'Created'}).status_code, 200)
        self.assertEqual(self.client.patch(path, headers=self.headers,
            json={'title': 'Edited'}).status_code, 200)
        self.assertEqual(self.db.get(Customer, active.id).title, 'Edited')
        self.grant('restore_trashed', 'delete_trashed', 'view_trashed')
        before = self.snapshot()
        self.assertEqual(self.client.delete(trash, headers=self.headers).status_code, 403)
        self.assertEqual(self.client.post(trash + '/restore', headers=self.headers).status_code, 403)
        self.assertEqual(before, self.snapshot())
        self.grant('delete_reference_customers')
        self.assertTrue(self.client.get(path).json()['can_restore'])
        self.assertEqual(self.client.post(trash + '/restore', headers=self.headers).status_code, 200)
        self.assertEqual(self.client.delete(trash, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.delete(trash, headers=self.headers).status_code, 200)
        self.assertIsNone(self.db.get(Customer, deleted.id))

    def test_orders_selector_does_not_grant_customer_administration(self):
        self.grant('view_menu_orders', 'edit_orders', 'delete_reference_customers',
                   'restore_trashed', 'delete_trashed')
        row = Customer(title='Selectable')
        self.db.add(row); self.db.commit()
        # The existing order-scoped metadata remains usable, not the full catalog.
        self.assertEqual(self.client.get('/api/orders/add/poly').status_code, 200)
        before = self.snapshot()
        base = '/api/customer-references'
        for method, target in [('GET', base), ('GET', f'{base}/{row.id}'),
                               ('GET', base + '/form'), ('POST', base),
                               ('PATCH', f'{base}/{row.id}'),
                               ('DELETE', f'{base}/{row.id}'),
                               ('POST', f'{base}/{row.id}/restore')]:
            response = self.client.request(method, target, headers=self.headers, json={'title': 'Denied'})
            self.assertEqual(response.status_code, 403, (method, target))
        self.assertEqual(before, self.snapshot())