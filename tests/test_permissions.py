import unittest
from unittest.mock import patch
from sqlalchemy import select

from app.models import Permission, Role, role_permissions
from app.permission_audit import AUTHORIZATION_MATRIX, DEDICATED_PERMISSION_IDS
from tests import test_reference_dictionaries as fixtures


class PermissionMatrixTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown
    def seed_matrix(self):
        self.db.add_all([
            Role(id=1, title="Администратор"),
            Role(id=2, title="Менеджер"),
            Permission(id="view_orders", title="Просмотр заказов", module="orders"),
            Permission(id="edit_bills", title="Редактирование счетов", module="accounting"),
        ])
        self.db.execute(role_permissions.insert(), [
            {"role_id": 1, "permission_id": "view_orders"},
            {"role_id": 2, "permission_id": "edit_bills"},
        ])
        self.db.commit()

    def test_matrix_is_grouped_and_reflects_assignments(self):
        self.seed_matrix()
        response = self.client.get("/api/options/permissions")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([role["title"] for role in data["roles"]], ["Администратор", "Менеджер"])
        orders = next(module for module in data["modules"] if module["id"] == "orders")
        permission = orders["permissions"][0]
        self.assertEqual(permission["roles"], {"1": True, "2": False})

    def test_update_replaces_matrix_and_rejects_unknown_ids(self):
        self.seed_matrix()
        response = self.client.post("/api/options/permissions", json={
            "permissions": {"view_orders": [2], "edit_bills": [1, 2]},
        })
        self.assertEqual(response.status_code, 200)
        assignments = set(self.db.execute(select(role_permissions.c.role_id, role_permissions.c.permission_id)).all())
        self.assertEqual(assignments, {(2, "view_orders"), (1, "edit_bills"), (2, "edit_bills")})
        self.assertEqual(self.client.post("/api/options/permissions", json={"permissions": {"missing": [1]}}).status_code, 422)
        self.assertEqual(self.client.post("/api/options/permissions", json={"permissions": {"view_orders": [999]}}).status_code, 422)

    def test_matrix_requires_authentication(self):
        self.seed_matrix()
        with patch("app.main.current_user", return_value=None):
            self.assertEqual(self.client.get("/api/options/permissions").status_code, 401)

    def test_audit_reports_catalog_completeness(self):
        self.seed_matrix()
        response = self.client.get('/api/options/permissions/audit')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('edit_price', payload['dedicated_permissions'])
        self.assertFalse(payload['catalog_complete'])
        self.assertIn('edit_price', payload['missing_catalog_permissions'])

    def test_authorization_matrix_is_complete_and_uses_known_contracts(self):
        self.assertGreaterEqual(len(AUTHORIZATION_MATRIX), 15)
        self.assertEqual(len({(row['method'], row['path']) for row in AUTHORIZATION_MATRIX}), len(AUTHORIZATION_MATRIX))
        self.assertTrue(all(row['unauthenticated'] == 401 for row in AUTHORIZATION_MATRIX))
        from app.s03_policy import policy_payload
        known = set(DEDICATED_PERMISSION_IDS) | {'restore_trashed'}
        for domain in policy_payload()['domains']:
            known.update(domain['read_any'])
            known.update((domain['edit'], domain['delete']))
        for row in AUTHORIZATION_MATRIX:
            contract = row['unauthorized']
            if contract in {'authenticated-only', 'domain read grant; see s03_policy.domains'}:
                continue
            self.assertTrue(set(contract.split(' AND ')) <= known, contract)

    def test_authorization_matrix_executes_unauthenticated_and_denied_requests(self):
        cases = [
            ('GET', '/api/orders', None, None),
            ('POST', '/api/orders/10/prepresses', {'prepress_id': 1}, None),
            ('POST', '/api/orders/10/restore', None, 'restore_trashed'),
            ('GET', '/api/prices/paper/1/records', None, None),
            ('POST', '/api/prices/paper/1/records', {'amount': '1', 'currency': 'RUB', 'actual_since': '2024-01-01', 'actual_from': 0}, 'edit_price'),
            ('GET', '/api/accounting/bills', None, 'view_accounting_bills'),
            ('POST', '/api/accounting/bills', {}, 'edit_accounting_bills'),
            ('POST', '/api/accounting/bills/1/payments', {}, 'edit_accounting_bills'),
            ('GET', '/api/accounting/payers', None, None),
            ('GET', '/api/references/materials', None, None),
            ('POST', '/api/employee-references', {}, 'user_create'),
            ('PATCH', '/api/employee-references/1', {}, 'user_edit'),
            ('GET', '/api/options/permissions', None, 'view_menu_options_permissions'),
            ('GET', '/api/reports/for/orders/1', None, None),
            ('PATCH', '/api/report-settings/missing', {}, 'view_menu_options_reports'),
            ('GET', '/api/reports/payrolls/1', None, 'view_menu_reports_payrolls'),
            ('POST', '/api/reports/payrolls', {}, 'edit_reports_payrolls'),
        ]

        for method, path, payload, permission in cases:
            with self.subTest(method=method, path=path):
                self.auth_mock.return_value = None
                response = self.client.request(method, path, json=payload)
                self.assertEqual(response.status_code, 401, response.text)

                self.auth_mock.return_value = self.user
                self.permission_mock.side_effect = lambda name, required=permission: required is None or name != required
                response = self.client.request(method, path, json=payload)
                if permission is None:
                    self.assertNotEqual(response.status_code, 401, response.text)
                else:
                    self.assertEqual(response.status_code, 403, response.text)

        self.permission_mock.side_effect = None
        self.permission_mock.return_value = True

    def test_matrix_requires_administration_permission(self):
        self.permission_mock.return_value = False
        self.assertEqual(self.client.get("/api/options/permissions").status_code, 403)
        self.assertEqual(self.client.post("/api/options/permissions", json={"permissions": {}}).status_code, 403)

    def test_partial_update_preserves_omitted_permissions_and_empty_roles_clear_row(self):
        self.seed_matrix()
        self.assertEqual(self.client.post("/api/options/permissions", json={"permissions": {"view_orders": []}}).status_code, 200)
        assignments = set(self.db.execute(select(role_permissions.c.role_id, role_permissions.c.permission_id)).all())
        self.assertEqual(assignments, {(2, "edit_bills")})
        for bad in [True, 1.5, {}, None]:
            self.assertEqual(self.client.post("/api/options/permissions", json={"permissions": {"edit_bills": [bad]}}).status_code, 422)
        self.assertEqual(set(self.db.execute(select(role_permissions.c.role_id, role_permissions.c.permission_id)).all()), assignments)


if __name__ == "__main__":
    unittest.main()