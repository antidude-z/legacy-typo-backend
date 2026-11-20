import unittest
from unittest.mock import patch

from tests import test_reference_dictionaries as fixtures
from app.permission_audit import ROUTE_PERMISSION_AUDIT


class PermissionAuditTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def test_manifest_covers_each_migrated_route_family(self):
        families = {item["family"] for item in ROUTE_PERMISSION_AUDIT}
        self.assertEqual(families, {
            "orders", "pricing", "accounting bills", "accounting payers",
            "references", "user administration", "permissions administration",
            "reports", "payroll", "authentication",
        })
        for item in ROUTE_PERMISSION_AUDIT:
            self.assertTrue(item["paths"])
            self.assertIsNotNone(item["read"])
            self.assertIsNotNone(item["write"])
            self.assertIsInstance(item["lifecycle"], list)

    def test_audit_endpoint_requires_permission_administration(self):
        response = self.client.get('/api/options/permissions/audit')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['families']), len(ROUTE_PERMISSION_AUDIT))
        self.assertFalse(response.json()['enforcement_verified'])
        self.assertEqual(len(response.json()['s03_policy']['domains']), 14)
        self.permission_mock.return_value = False
        self.assertEqual(self.client.get('/api/options/permissions/audit').status_code, 403)
        self.auth_mock.return_value = None
        self.assertEqual(self.client.get('/api/options/permissions/audit').status_code, 401)


if __name__ == '__main__':
    unittest.main()