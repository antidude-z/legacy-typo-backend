"""S03 printer hierarchy: real sessions, ownership and deleted-parent checks."""
from datetime import datetime
from app.models import Printer, PrinterField, PrinterProcess, PrinterProcessStage, PaperFormat
from tests import test_review_employee_authorization as fixtures


class PrinterAuthorizationReviewTests(fixtures.EmployeeAuthorizationReviewTests):
    def hierarchy(self):
        self.db.add_all([Printer(id=1, title='Press'), Printer(id=2, title='Other'),
                         PaperFormat(id=1, title='A4', width=210, height=297),
                         PrinterProcess(id=1, printer_id=1, title='Process'),
                         PrinterProcess(id=2, printer_id=2, title='Other process'),
                         PrinterField(id=1, printer_id=1, paper_format_id=1, pieces=1, width=210, height=297),
                         PrinterProcessStage(id=1, printer_process_id=1, title='Stage', together=1, colors=1, waste=0, weight=0)])
        self.db.commit()
        base = '/api/references/printers/1'
        return [(base, {'title': 'Edited press'}, '/api/references/printers/create'),
                (base + '/fields/1', {'paper_format_id': 1, 'pieces': 1, 'width': 210, 'height': 297}, base + '/fields'),
                (base + '/processes/1', {'title': 'Edited process', 'rejection': 0, 'colors_front': 1, 'colors_back': 0, 'resolution': 0}, base + '/processes/create'),
                (base + '/processes/1/stages/1', {'title': 'Edited stage', 'together': 1, 'colors': 1, 'waste': 0}, base + '/processes/1/stages/create')]

    def test_hierarchy_read_write_and_lifecycle_permissions(self):
        cases = self.hierarchy()
        self.grant('view_menu_references_printers')
        before = self.snapshot()
        for path, payload, create in cases:
            self.assertEqual(self.client.get(path).status_code, 200)
            self.assertFalse(self.client.get(path).json()['can_edit'])
            for method, target in [('PATCH', path), ('POST', create), ('DELETE', path), ('POST', path + '/restore')]:
                result = self.client.request(method, target, json=payload, headers=self.headers)
                self.assertEqual(result.status_code, 403, (method, target, result.text))
        self.assertEqual(before, self.snapshot())
        self.grant('edit_reference_printers')
        for path, payload, create in cases:
            result = self.client.patch(path, json=payload, headers=self.headers)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(self.client.post(create, json=payload, headers=self.headers).status_code, 200)
        self.grant('restore_trashed', 'delete_trashed', 'view_trashed')
        before = self.snapshot()
        for path, _, _ in cases:
            self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 403)
            self.assertEqual(self.client.post(path + '/restore', headers=self.headers).status_code, 403)
        self.assertEqual(before, self.snapshot())
        self.grant('delete_reference_printers')
        # Children first: parent deletion must not be used to bypass child scope.
        for path, _, _ in reversed(cases):
            self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
            self.assertEqual(self.client.post(path + '/restore', headers=self.headers).status_code, 200)

    def test_domain_deleter_requires_generic_lifecycle_and_can_permanently_delete(self):
        cases = self.hierarchy()
        self.grant('view_menu_references_printers', 'delete_reference_printers', 'view_trashed')
        # A domain deletion grant is sufficient only for initial soft deletion.
        for path, _, _ in reversed(cases):
            self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
            before = self.snapshot()
            self.assertEqual(self.client.post(path + '/restore', headers=self.headers).status_code, 403)
            self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 403)
            self.assertEqual(before, self.snapshot())
            # Restore for the next child/parent check without changing authority.
            model, identity = ((PrinterProcessStage, 1) if '/stages/' in path else
                               (PrinterProcess, 1) if '/processes/' in path else
                               (PrinterField, 1) if '/fields/' in path else (Printer, 1))
            self.db.get(model, identity).deleted_at = None; self.db.commit()
        self.grant('delete_trashed', 'restore_trashed')
        for path, _, _ in reversed(cases):
            self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
            self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)

    def test_wrong_or_deleted_parents_and_unrelated_staff_preserve_data(self):
        cases = self.hierarchy()
        self.grant('view_menu_orders', 'edit_reference_printers', 'delete_reference_printers')
        before = self.snapshot()
        for path, payload, _ in cases:
            self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.client.patch(path, json=payload, headers=self.headers).status_code, 403)
        self.assertEqual(before, self.snapshot())
        self.grant('view_menu_references_printers', 'restore_trashed', 'delete_trashed', 'view_trashed')
        invalid = ['/api/references/printers/2/fields/1',
                   '/api/references/printers/2/processes/1',
                   '/api/references/printers/2/processes/2/stages/1',
                   '/api/references/printers/2/processes/1/stages/1']
        before = self.snapshot()
        for path in invalid:
            for method in ('GET', 'PATCH', 'DELETE'):
                self.assertEqual(self.client.request(method, path, json={}, headers=self.headers).status_code, 404)
            self.assertEqual(self.client.post(path + '/restore', headers=self.headers).status_code, 404)
        self.assertEqual(before, self.snapshot())
        self.db.get(PrinterProcess, 1).deleted_at = datetime(2020, 1, 1); self.db.commit()
        before = self.snapshot()
        stage_path = cases[-1][0]
        for method in ('GET', 'PATCH', 'DELETE'):
            self.assertEqual(self.client.request(method, stage_path, json={}, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.post(stage_path + '/restore', headers=self.headers).status_code, 404)
        self.assertEqual(before, self.snapshot())
        self.db.get(PrinterProcess, 1).deleted_at = None; self.db.commit()
        self.db.get(Printer, 1).deleted_at = datetime(2020, 1, 1); self.db.commit()
        before = self.snapshot()
        for path, payload, create in cases[1:]:
            for method in ('GET', 'PATCH', 'DELETE'):
                self.assertEqual(self.client.request(method, path, json=payload, headers=self.headers).status_code, 404)
            self.assertEqual(self.client.post(create, json=payload, headers=self.headers).status_code, 404)
            self.assertEqual(self.client.post(path + '/restore', headers=self.headers).status_code, 404)
        self.assertEqual(before, self.snapshot())