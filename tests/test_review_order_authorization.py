"""S03 real-session, valid-resource denial tests on disposable SQLite."""
from datetime import date, datetime
from app.models import Blank, Order, OrderPrepress, OrderRedaction, OrderCompile, OrderOtherWork
from tests import test_review_employee_authorization


class OrderAuthorizationReviewTests(test_review_employee_authorization.EmployeeAuthorizationReviewTests):
    def seed_children(self):
        self.db.add_all([Order(id=10, title='Parent', order_type='poly', status_id=1, printing=10),
                         Order(id=11, title='Other', order_type='poly', status_id=1, printing=10),
                         Blank(id=20, order_id=10, title='Blank', printer_id=0)])
        for model, key in ((OrderPrepress, 'prepress_id'), (OrderRedaction, 'redaction_id'),
                           (OrderCompile, 'compile_id'), (OrderOtherWork, 'other_work_id')):
            self.db.add(model(id=20, order_id=10, **{key: 1}, quantity=1))
        self.db.commit()

    def reject_unchanged(self, method, path, status=404, payload=None):
        before = self.snapshot()
        response = self.client.request(method, path, json=payload, headers=self.headers)
        self.assertEqual(response.status_code, status, (method, path, response.text))
        self.assertEqual(before, self.snapshot())

    def all_order_grants(self):
        self.grant('view_menu_orders', 'edit_orders', 'delete_orders', 'view_trashed',
                   'restore_trashed', 'delete_trashed')

    def test_deleted_parent_blocks_children_and_non_lifecycle_mutations(self):
        self.seed_children(); self.all_order_grants()
        self.db.get(Order, 10).deleted_at = datetime(2020, 1, 1); self.db.commit()
        base = '/api/orders/10'
        self.assertEqual(self.client.get(base).status_code, 200)
        for method, suffix in [('PUT', ''), ('POST', ''), ('POST', '/copy'),
                               ('POST', '/recalculate'), ('GET', '/operations'), ('GET', '/blanks')]:
            self.reject_unchanged(method, base + suffix, payload={})
        for kind in ('blanks', 'prepresses', 'redactions', 'compiles', 'others'):
            self.reject_unchanged('POST', base + '/' + kind, payload={})
            for method, suffix in [('PATCH', ''), ('DELETE', ''), ('POST', '/restore')]:
                self.reject_unchanged(method, f'{base}/{kind}/20{suffix}', payload={})
        for method, suffix in [('GET', ''), ('POST', '/copy'), ('POST', '/recalculate'),
                               ('DELETE', '/permanent')]:
            self.reject_unchanged(method, base + '/blanks/20' + suffix, payload={})
        self.assertEqual(self.client.post(base + '/restore', headers=self.headers).status_code, 200)
        self.assertEqual(self.client.patch(base + '/blanks/20', headers=self.headers,
                                          json={'title': 'Restored parent'}).status_code, 200)

    def test_cross_parent_and_missing_parent_children_reject_every_method(self):
        self.seed_children(); self.all_order_grants()
        for parent in (11, 999):
            for kind in ('blanks', 'prepresses', 'redactions', 'compiles', 'others'):
                path = f'/api/orders/{parent}/{kind}/20'
                for method, suffix in [('PATCH', ''), ('DELETE', ''), ('POST', '/restore')]:
                    self.reject_unchanged(method, path + suffix, payload={})
            for method, suffix in [('GET', ''), ('POST', '/copy'), ('POST', '/recalculate'),
                                   ('DELETE', '/permanent')]:
                self.reject_unchanged(method, f'/api/orders/{parent}/blanks/20{suffix}', payload={})

    def test_deleted_children_are_not_editable_or_copyable(self):
        self.seed_children(); self.all_order_grants()
        for model in (Blank, OrderPrepress, OrderRedaction, OrderCompile, OrderOtherWork):
            self.db.get(model, 20).deleted_at = datetime(2020, 1, 1)
        self.db.commit()
        for kind in ('blanks', 'prepresses', 'redactions', 'compiles', 'others'):
            self.reject_unchanged('PATCH', f'/api/orders/10/{kind}/20', payload={'quantity': 2})
        for suffix in ('/copy', '/recalculate'):
            self.reject_unchanged('POST', '/api/orders/10/blanks/20' + suffix)
        self.assertEqual(self.client.get('/api/orders/10/blanks/20').status_code, 200)
        self.role.permissions[:] = [p for p in self.role.permissions if p.id != 'view_trashed']
        self.db.commit()
        self.reject_unchanged('GET', '/api/orders/10/blanks/20')

    def test_repeated_delete_requires_generic_permission_without_timestamp_changes(self):
        self.seed_children()
        self.grant('view_menu_orders', 'delete_orders')
        for path in ('/api/orders/10/blanks/20', '/api/orders/10/prepresses/20', '/api/orders/10/redactions/20',
                     '/api/orders/10/compiles/20', '/api/orders/10/others/20', '/api/orders/10'):
            self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
            self.reject_unchanged('DELETE', path, status=403)

    def test_blank_permanent_delete_rejects_active_row(self):
        self.seed_children(); self.all_order_grants()
        self.reject_unchanged('DELETE', '/api/orders/10/blanks/20/permanent', status=409)
        self.assertEqual(self.client.delete('/api/orders/10/blanks/20', headers=self.headers).status_code, 200)
        self.assertEqual(self.client.delete('/api/orders/10/blanks/20/permanent', headers=self.headers).status_code, 200)

    def test_orphan_children_and_deleted_history_are_hidden(self):
        self.seed_children(); self.all_order_grants()
        self.db.get(Blank, 20).order_id = 999
        self.db.get(OrderPrepress, 20).order_id = 999
        self.db.get(Order, 10).deleted_at = datetime(2020, 1, 1)
        self.role.permissions[:] = [p for p in self.role.permissions if p.id != 'view_trashed']
        self.db.commit()
        for path in ('/api/orders/10', '/api/orders/10/history', '/api/orders/999/blanks/20'):
            self.reject_unchanged('GET', path)
        for kind in ('blanks', 'prepresses'):
            for method, suffix in [('PATCH', ''), ('DELETE', ''), ('POST', '/restore')]:
                self.reject_unchanged(method, f'/api/orders/999/{kind}/20{suffix}', payload={})

    def test_composed_capabilities_and_generic_only_lifecycle_denials(self):
        self.seed_children()
        self.grant('view_menu_orders', 'restore_trashed', 'delete_trashed')
        for path in ('/api/orders', '/api/orders/10', '/api/orders/10/operations'):
            permissions = self.client.get(path).json()['permissions']
            self.assertEqual(permissions, dict.fromkeys(('edit', 'delete', 'restore', 'permanent_delete'), False))
        for kind in ('blanks', 'prepresses', 'redactions', 'compiles', 'others'):
            path = f'/api/orders/10/{kind}/20'
            self.reject_unchanged('DELETE', path, status=403)
            self.reject_unchanged('POST', path + '/restore', status=403)
        self.grant('delete_orders')
        for kind in ('blanks', 'prepresses', 'redactions', 'compiles', 'others'):
            path = f'/api/orders/10/{kind}/20'
            for method, suffix in [('DELETE', ''), ('POST', '/restore'), ('DELETE', ''), ('DELETE', '')]:
                response = self.client.request(method, path + suffix, headers=self.headers)
                self.assertEqual(response.status_code, 200, response.text)
        self.grant('edit_orders')
        self.assertIs(self.client.get('/api/orders/00010').json()['permissions']['edit'], True)
        self.reject_unchanged('GET', '/api/orders/not-an-id', status=422)

    def test_revoked_edit_and_child_read_only_access(self):
        self.seed_children()
        self.grant('view_menu_orders', 'edit_orders')
        path = '/api/orders/10/blanks/20'
        self.assertEqual(self.client.patch(path, headers=self.headers, json={'title': 'Allowed'}).status_code, 200)
        self.role.permissions[:] = [p for p in self.role.permissions if p.id != 'edit_orders']
        self.db.commit()
        self.reject_unchanged('PATCH', path, status=403, payload={'title': 'Denied'})
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get('/api/orders/10/operations').status_code, 200)
        self.reject_unchanged('GET', '/api/orders/add/poly', status=403)
        self.db.get(Blank, 20).deleted_at = datetime(2020, 1, 1); self.db.commit()
        self.assertEqual(self.client.get('/api/orders/10/blanks').json()['items'], [])
        self.grant('view_trashed')
        listing = self.client.get('/api/orders/10/blanks').json()
        self.assertEqual([item['id'] for item in listing['items']], [20])
        self.assertTrue(listing['items'][0]['deleted'])
        self.assertFalse(listing['permissions']['restore'])
        for kind in ('blanks', 'prepresses', 'redactions', 'compiles', 'others'):
            self.reject_unchanged('POST', f'/api/orders/10/{kind}', status=403, payload={})
            self.reject_unchanged('PATCH', f'/api/orders/10/{kind}/20', status=403, payload={})

    def test_order_reader_cannot_write_or_delete_existing_resources(self):
        self.grant('view_menu_orders')
        item = Order(title='Protected', order_type='poly', status_id=1, printing=10, order_date=date.today())
        self.db.add(item); self.db.commit()
        self.assertEqual(self.client.get(f'/api/orders/{item.id}').status_code, 200)
        before = self.snapshot()
        for method, path, payload in (
            ('PUT', f'/api/orders/{item.id}', {'title': 'Changed'}),
            ('POST', f'/api/orders/{item.id}', {'title': 'Changed'}),
            ('DELETE', f'/api/orders/{item.id}', {}),
            ('POST', f'/api/orders/{item.id}/copy', {}),
            ('POST', f'/api/orders/{item.id}/blanks', {}),
            ('POST', f'/api/orders/{item.id}/recalculate', {}),
            ('POST', '/api/orders/add/poly', {'title': 'New'}),
        ):
            response = self.client.request(method, path, json=payload, headers=self.headers)
            self.assertEqual(response.status_code, 403, (method, path, response.text))
        self.assertEqual(before, self.snapshot())
        self.grant('edit_orders')
        response = self.client.put(f'/api/orders/{item.id}', json={'title': 'Allowed'}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.db.get(Order, item.id).title, 'Allowed')
        self.assertEqual(self.client.delete(f'/api/orders/{item.id}', headers=self.headers).status_code, 403)

    def test_unrelated_staff_cannot_read_orders_or_use_alias(self):
        self.grant('view_menu_references_users')
        before = self.snapshot()
        for path in ('/api/orders', '/orders', '/api/orders/add/poly', '/orders/formats/book'):
            self.assertEqual(self.client.get(path).status_code, 403, path)
        self.assertEqual(before, self.snapshot())