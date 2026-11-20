"""S03 work catalogs: real sessions and guarded disposable SQLite fixtures."""
from app.models import Prepress, Redaction
from tests import test_review_employee_authorization as fixtures


class WorkAuthorizationReviewTests(fixtures.EmployeeAuthorizationReviewTests):
    def seed_works(self):
        self.db.add_all([Prepress(id=1, title='Design'), Redaction(id=1, title='Editing')])
        self.db.commit()

    def denied(self, method, path, status=403, payload=None):
        before = self.snapshot()
        response = self.client.request(method, path, headers=self.headers, json=payload)
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(before, self.snapshot())

    def test_unrelated_staff_and_cross_catalog_grants_do_not_allow_access(self):
        self.seed_works()
        self.grant('view_menu_orders', 'edit_reference_prepresses', 'delete_reference_prepresses')
        for kind in ('prepresses', 'redactions'):
            base = f'/api/reference-works/{kind}'
            for method, path in [('GET', base), ('GET', base + '/1'),
                                 ('POST', base), ('PATCH', base + '/1'),
                                 ('DELETE', base + '/1'), ('POST', base + '/1/restore')]:
                self.denied(method, path, payload={'title': 'Changed'})
        self.grant('view_menu_references_prepresses')
        self.assertEqual(self.client.get('/api/reference-works/prepresses/1').status_code, 200)
        self.denied('GET', '/api/reference-works/redactions/1')
        self.grant('view_menu_references_redactions')
        self.denied('PATCH', '/api/reference-works/redactions/1', payload={'title': 'Changed'})
        self.denied('DELETE', '/api/reference-works/redactions/1')

    def test_readers_writers_lifecycle_and_capabilities(self):
        self.seed_works()
        self.grant('view_menu_references_prepresses', 'view_menu_references_redactions')
        for kind in ('prepresses', 'redactions'):
            base = f'/api/reference-works/{kind}'
            path = base + '/1'
            for url in (base, path):
                data = self.client.get(url).json()
                for capability in ('can_edit', 'can_delete', 'can_restore', 'can_delete_trashed'):
                    self.assertIs(data.get(capability), False)
            self.denied('GET', base + '/form-options')
            self.denied('POST', base, payload={'title': 'New'})
            self.denied('PATCH', path, payload={'title': 'Changed'})
            self.denied('DELETE', path)
            self.denied('POST', path + '/restore')
        self.grant('edit_reference_prepresses', 'edit_reference_redactions')
        for kind in ('prepresses', 'redactions'):
            base = f'/api/reference-works/{kind}'
            self.assertIs(self.client.get(base + '/form-options').json()['can_edit'], True)
            created = self.client.post(base, headers=self.headers, json={'title': 'New'})
            self.assertEqual(created.status_code, 200, created.text)
            self.assertEqual(self.client.patch(base + '/1', headers=self.headers,
                                              json={'title': 'Changed'}).status_code, 200)
        self.grant('restore_trashed', 'delete_trashed', 'view_trashed')
        for kind in ('prepresses', 'redactions'):
            path = f'/api/reference-works/{kind}/1'
            self.denied('DELETE', path)
            self.denied('POST', path + '/restore')
        self.grant('delete_reference_prepresses', 'delete_reference_redactions')
        for kind in ('prepresses', 'redactions'):
            path = f'/api/reference-works/{kind}/1'
            for method, url in [('DELETE', path), ('POST', path + '/restore'),
                                ('POST', path + '/restore'), ('DELETE', path), ('DELETE', path)]:
                self.assertEqual(self.client.request(method, url, headers=self.headers).status_code, 200)
            self.denied('PATCH', path, status=404, payload={'title': 'Missing'})
            self.denied('DELETE', path, status=404)
            self.denied('POST', path + '/restore', status=404)

    def test_domain_delete_requires_additional_lifecycle_grants(self):
        self.seed_works()
        self.grant('view_menu_references_prepresses', 'view_menu_references_redactions',
                   'delete_reference_prepresses', 'delete_reference_redactions')
        for kind in ('prepresses', 'redactions'):
            path = f'/api/reference-works/{kind}/1'
            self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
            self.denied('DELETE', path)
            self.denied('POST', path + '/restore')
            self.denied('GET', path, status=404)
            self.assertEqual(self.client.get(f'/api/reference-works/{kind}').json()['items'], [])

    def test_revoked_writer_and_deleted_rows_reject_updates(self):
        self.seed_works()
        self.grant('view_menu_references_prepresses', 'edit_reference_prepresses',
                   'delete_reference_prepresses', 'view_trashed')
        path = '/api/reference-works/prepresses/1'
        self.denied('PATCH', path, status=422, payload={'title': ''})
        self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
        self.denied('PATCH', path, status=404, payload={'title': 'Deleted'})
        self.role.permissions[:] = [p for p in self.role.permissions if p.id != 'edit_reference_prepresses']
        self.db.commit()
        self.denied('POST', '/api/reference-works/prepresses', payload={'title': 'New'})
        self.denied('GET', '/api/reference-works/prepresses/form-options')