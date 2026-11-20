"""S03 compile hierarchy, real sessions and disposable SQLite only."""
from datetime import datetime
from app.models import Compile, CompileStage, CompileStageMaterial, Material
from tests import test_review_employee_authorization as fixtures


class CompileAuthorizationReviewTests(fixtures.EmployeeAuthorizationReviewTests):
    def test_domain_delete_does_not_replace_generic_lifecycle_grants(self):
        _, _, material = self.seed_hierarchy()
        self.grant('view_menu_references_compiles', 'delete_reference_compiles', 'view_trashed')
        self.assertEqual(self.client.delete(material, headers=self.headers).status_code, 200)
        before = self.snapshot()
        self.assertEqual(self.client.delete(material, headers=self.headers).status_code, 403)
        self.assertEqual(self.client.post(material + '/restore', headers=self.headers).status_code, 403)
        self.assertEqual(before, self.snapshot())

    def seed_hierarchy(self):
        self.db.add_all([Compile(id=1, title='Finish', production_poly=True),
                         Compile(id=2, title='Other', production_poly=True),
                         CompileStage(id=1, compile_id=1, title='Stage', together=1, waste=0, weight=0),
                         CompileStage(id=2, compile_id=2, title='Other stage', together=1, waste=0, weight=0),
                         Material(id=1, title='Glue', production_poly=True),
                         CompileStageMaterial(id=1, compile_stage_id=1, material_id=1, quantity=1)])
        self.db.commit()
        base = '/api/references/compiles/1'
        return base, base + '/stages/1', base + '/stages/1/materials/1'

    def test_reader_writer_lifecycle_and_unrelated_staff(self):
        base, stage, material = self.seed_hierarchy()
        self.grant('view_menu_orders', 'edit_reference_compiles', 'delete_reference_compiles')
        before = self.snapshot()
        for path in (base, stage, material):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(before, self.snapshot())
        self.role.permissions.clear(); self.db.commit()
        self.grant('view_menu_references_compiles')
        mutations = [('PATCH', base, {'title': 'Updated', 'production_poly': True}),
                     ('POST', base + '/stages', {'title': 'New', 'together': 1}),
                     ('PATCH', stage, {'title': 'Updated', 'together': 1}),
                     ('POST', stage + '/materials', {'material_id': 1, 'quantity': '0.5'}),
                     ('PATCH', material, {'material_id': 1, 'quantity': '0.5'}),
                     ('DELETE', stage, {}), ('DELETE', material, {}),
                     ('POST', stage + '/restore', {}), ('POST', material + '/restore', {})]
        for path in (base, stage, material):
            self.assertEqual(self.client.get(path).status_code, 200)
        before = self.snapshot()
        for method, path, payload in mutations:
            self.assertEqual(self.client.request(method, path, headers=self.headers, json=payload).status_code, 403)
        self.assertEqual(before, self.snapshot())
        self.grant('edit_reference_compiles')
        for method, path, payload in mutations[:5]:
            response = self.client.request(method, path, headers=self.headers, json=payload)
            self.assertEqual(response.status_code, 200, response.text)
        self.grant('restore_trashed', 'delete_trashed', 'view_trashed')
        before = self.snapshot()
        for method, path, payload in mutations[5:]:
            self.assertEqual(self.client.request(method, path, headers=self.headers, json=payload).status_code, 403)
        self.assertEqual(before, self.snapshot())
        self.grant('delete_reference_compiles')
        for path in (material, stage):
            self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
            self.assertEqual(self.client.post(path + '/restore', headers=self.headers).status_code, 200)
            self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)
            self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 200)

    def test_cross_parent_and_deleted_parent_reject_without_mutation(self):
        base, stage, material = self.seed_hierarchy()
        self.grant('view_menu_references_compiles', 'edit_reference_compiles',
                   'delete_reference_compiles', 'restore_trashed', 'delete_trashed', 'view_trashed')
        wrong = ['/api/references/compiles/2/stages/1',
                 '/api/references/compiles/2/stages/2/materials/1']
        for paths in (wrong, [material]):
            if paths == [material]:
                self.db.get(CompileStage, 1).deleted_at = datetime(2020, 1, 1); self.db.commit()
            before = self.snapshot()
            for path in paths:
                for method in ('GET', 'PATCH', 'DELETE'):
                    self.assertEqual(self.client.request(method, path, json={}, headers=self.headers).status_code, 404)
                self.assertEqual(self.client.post(path + '/restore', headers=self.headers).status_code, 404)
            self.assertEqual(before, self.snapshot())
        self.db.get(CompileStage, 1).deleted_at = None
        self.db.get(Compile, 1).deleted_at = datetime(2020, 1, 1); self.db.commit()
        before = self.snapshot()
        for method, path in [('POST', base + '/stages'), ('PATCH', stage), ('DELETE', stage),
                             ('POST', stage + '/restore'), ('POST', stage + '/materials'),
                             ('PATCH', material), ('DELETE', material), ('POST', material + '/restore')]:
            self.assertEqual(self.client.request(method, path, headers=self.headers, json={}).status_code, 404)
        self.assertEqual(before, self.snapshot())