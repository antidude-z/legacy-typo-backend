import unittest
from unittest.mock import patch
from sqlalchemy import select

from app.models import Permission, Role, role_permissions
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