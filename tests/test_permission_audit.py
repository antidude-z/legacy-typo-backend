import unittest
import json
from pathlib import Path
from unittest.mock import patch

from tests import test_reference_dictionaries as fixtures
from app.main import app
from app.permission_audit import ROUTE_PERMISSION_AUDIT, route_coverage


class PermissionAuditTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def test_manifest_covers_each_migrated_route_family(self):
        families = {item["family"] for item in ROUTE_PERMISSION_AUDIT}
        self.assertEqual(families, {
            "orders", "pricing", "accounting bills", "accounting payers",
            "references", "user administration", "permissions administration",
            "reports", "payroll", "authentication", "system and main settings",
        })
        for item in ROUTE_PERMISSION_AUDIT:
            self.assertTrue(item["paths"])
            self.assertIsNotNone(item["read"])
            self.assertIsNotNone(item["write"])
            self.assertIsInstance(item["lifecycle"], list)

    def test_registered_business_route_inventory_is_reviewed(self):
        expected = json.loads((Path(__file__).parents[1] / 'app' / 'reviewed_routes.json').read_text(encoding='utf-8'))
        coverage = route_coverage(app)
        self.assertTrue(coverage['complete'], coverage['unmatched'])
        self.assertEqual(coverage['registered'], [{key: row[key] for key in ('method', 'path', 'module')} for row in expected],
                         'Route changed: update the reviewed S10 inventory and real-session coverage')
        from app.route_policies import POLICIES
        import importlib.util
        self.assertEqual(coverage['invalid_policies'], [])
        self.assertEqual(len(expected), len({(row['method'], row['path']) for row in expected}))
        for policy in POLICIES.values():
            self.assertTrue(policy['conditions'])
            for module in policy['evidence']:
                self.assertIsNotNone(importlib.util.find_spec(module), module)

    def test_new_auth_route_cannot_inherit_public_exemption(self):
        from fastapi import FastAPI
        candidate = FastAPI()
        candidate.router.routes.extend(app.routes)
        candidate.add_api_route('/api/auth/new-admin-action', lambda: {}, methods=['DELETE'])
        coverage = route_coverage(candidate)
        self.assertFalse(coverage['complete'])
        self.assertTrue(any(row['path'] == '/api/auth/new-admin-action' for row in coverage['unreviewed']))

    def test_new_route_or_method_inside_existing_family_is_not_reviewed(self):
        from fastapi import FastAPI
        candidate = FastAPI()
        candidate.router.routes.extend(app.routes)
        candidate.add_api_route('/api/orders/unreviewed-action', lambda: {}, methods=['DELETE'])
        candidate.add_api_route('/api/orders', lambda: {}, methods=['PATCH'])
        coverage = route_coverage(candidate)
        self.assertFalse(coverage['complete'])
        self.assertEqual({(row['method'], row['path']) for row in coverage['unreviewed']},
                         {('DELETE', '/api/orders/unreviewed-action'), ('PATCH', '/api/orders')})

    def test_removed_route_is_reported(self):
        from fastapi import FastAPI
        candidate = FastAPI()
        candidate.router.routes.extend(route for route in app.routes if route.path != '/api/employee-references')
        coverage = route_coverage(candidate)
        self.assertFalse(coverage['complete'])
        self.assertTrue(any(row['path'] == '/api/employee-references' for row in coverage['missing']))

    def test_removing_admission_from_reviewed_route_fails_coverage(self):
        from copy import copy
        from fastapi import FastAPI
        candidate = FastAPI()
        for route in app.routes:
            if route.path == '/api/employee-references':
                route = copy(route)
                route.dependant = copy(route.dependant)
                route.dependant.dependencies = []
            candidate.router.routes.append(route)
        coverage = route_coverage(candidate)
        self.assertFalse(coverage['complete'])
        self.assertTrue(any(row['path'] == '/api/employee-references' for row in coverage['missing_admission']))

    def test_audit_endpoint_requires_permission_administration(self):
        response = self.client.get('/api/options/permissions/audit')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['families']), len(ROUTE_PERMISSION_AUDIT))
        self.assertFalse(response.json()['enforcement_verified'])
        self.assertEqual(len(response.json()['s03_policy']['domains']), 14)
        self.assertTrue(response.json()['route_coverage']['complete'])
        self.assertEqual(response.json()['route_coverage']['unmatched'], [])
        self.permission_mock.return_value = False
        self.assertEqual(self.client.get('/api/options/permissions/audit').status_code, 403)
        self.auth_mock.return_value = None
        self.assertEqual(self.client.get('/api/options/permissions/audit').status_code, 401)


if __name__ == '__main__':
    unittest.main()