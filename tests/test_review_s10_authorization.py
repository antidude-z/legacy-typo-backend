"""S10 residual policies: real cookies/grants, guarded disposable fixtures only."""
from datetime import date
import unittest
from unittest.mock import patch

from app.models import Bill, Order, OrderStatus, Paper, Payroll, Report, ReportParam
from tests import test_review_employee_authorization as employee


class S10AuthorizationTests(unittest.TestCase):
    mysql = False
    tearDown = employee.EmployeeAuthorizationReviewTests.tearDown
    grant = employee.EmployeeAuthorizationReviewTests.grant
    snapshot = employee.EmployeeAuthorizationReviewTests.snapshot

    def setUp(self):
        employee.EmployeeAuthorizationReviewTests.setUp(self)
        self.grant('view_menu_reports')
        self.db.add_all([
            Paper(id=301, title='S10 paper'),
            Payroll(id=301, user_id=self.target.id, salary=123, period=date(2026, 1, 1), status='calc'),
            Report(id='s10', title='S10 report', model='App\\Order', kind='html', format='A4', orientation='P'),
            ReportParam(id=301, report_id='s10', alias='test', title='Test', value='before'),
        ])
        self.db.commit()

    def denied(self, method, path, payload=None):
        before = self.snapshot()
        response = self.client.request(method, path, headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 403, (method, path, response.text))
        self.assertEqual(before, self.snapshot(), (method, path))

    def revoke(self, permission):
        self.role.permissions = [item for item in self.role.permissions if item.id != permission]
        self.db.commit()

    def test_pricing_individual_grants_revocation_and_capabilities(self):
        base = '/api/prices/paper/301'
        payload = {'amount': '12.50', 'currency': 'RUB', 'actual_from': 0, 'actual_since': '2026-01-01'}
        self.assertEqual(self.client.get('/api/pricing/catalog/paper').status_code, 200)
        self.assertFalse(self.client.get(base + '/records').json()['can_edit'])
        self.denied('POST', base + '/create')
        self.denied('POST', base + '/records', payload)
        self.grant('edit_price')
        self.assertTrue(self.client.get(base + '/records').json()['can_edit'])
        response = self.client.post(base + '/records', headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        detail = base + '/records/' + str(response.json()['id'])
        self.denied('DELETE', detail)
        self.assertEqual(self.client.patch(detail, headers=self.headers, json={**payload, 'amount': '13'}).status_code, 200)
        self.revoke('edit_price')
        self.denied('PATCH', detail, payload)
        self.grant('delete_price')
        self.assertTrue(self.client.get(detail).json()['can_delete'])
        self.assertEqual(self.client.delete(detail, headers=self.headers).status_code, 200)

    def test_settings_individual_grant_and_revocation(self):
        payload = {'title': 'Changed', 'format': 'A3', 'orientation': 'L'}
        calls = [('GET', '/api/report-settings', None),
                 ('GET', '/api/report-settings/s10', None),
                 ('PATCH', '/api/report-settings/s10', payload),
                 ('GET', '/api/report-settings/s10/params/301', None),
                 ('PATCH', '/api/report-settings/s10/params/301', {'title': 'Test', 'value': 'after'})]
        for method, path, body in calls:
            self.denied(method, path, body)
        self.grant('view_menu_options_reports')
        for method, path, body in calls:
            response = self.client.request(method, path, headers=self.headers, json=body)
            self.assertEqual(response.status_code, 200, (path, response.text))
        self.revoke('view_menu_options_reports')
        for method, path, body in calls:
            self.denied(method, path, body)

    def test_payroll_reader_cannot_mutate_and_revocation_is_immediate(self):
        base = '/api/reports/payrolls'
        payload = {'manager_id': self.target.id, 'year': 2026, 'month': 2}
        self.denied('GET', base + '/form')
        self.denied('GET', base + '/301')
        self.denied('GET', '/reports/payrolls/301/export')
        self.grant('view_menu_reports_payrolls')
        self.assertFalse(self.client.get(base + '/form').json()['can_edit'])
        self.assertFalse(self.client.get(base + '/301').json()['can_edit'])
        self.db.add_all([
            OrderStatus(id=301, title='S10 draft', sequence=1),
            Bill(id=301, number='S10 eligible', amount=100, paid=True, closed=True, filed=True),
            Order(id=301, title='S10 eligible', order_type='poly', status_id=301,
                  user_id=self.target.id, bill_id=301, printing=10, total=100),
        ])
        self.db.commit()
        before = self.snapshot()
        for path in (base + '/form', base + '/301', '/reports/payrolls/301/export'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, (path, response.text[:100]))
            self.assertEqual(before, self.snapshot(), path)
        self.denied('POST', base, payload)
        self.denied('PATCH', base + '/301', {'salary': 200, 'status': 'paid'})
        self.grant('edit_reports_payrolls')
        self.assertTrue(self.client.get(base + '/form').json()['can_edit'])
        self.assertEqual(len(self.client.get(base + '/301').json()['item']['orders']), 1)
        self.assertEqual(self.client.post(base, headers=self.headers, json=payload).status_code, 200)
        self.assertEqual(self.client.patch(base + '/301', headers=self.headers, json={'salary': 200, 'status': 'paid'}).status_code, 200)
        self.revoke('edit_reports_payrolls')
        self.denied('PATCH', base + '/301', {'status': 'calc'})
        self.revoke('view_menu_reports_payrolls')
        self.denied('GET', base + '/301')

    def test_main_options_and_production_diagnostics(self):
        self.denied('GET', '/api/options/main')
        self.grant('view_menu_options_main')
        self.assertEqual(self.client.get('/api/options/main').status_code, 200)
        self.revoke('view_menu_options_main')
        self.denied('GET', '/api/options/main')
        with patch('app.main.PRODUCTION', True):
            for path in ('/api/system/database', '/api/system/diagnostics'):
                self.denied('GET', path)
        # Do not run diagnostics against the configured working DB: permission
        # success for the DB-independent endpoint suffices for this grant check.
        self.grant('view_menu_options_permissions')
        with patch('app.main.PRODUCTION', True):
            self.assertEqual(self.client.get('/api/system/database').status_code, 200)

    def test_matrix_admin_grant_revocation_and_unchanged_denials(self):
        self.denied('GET', '/api/options/permissions')
        self.denied('GET', '/api/options/permissions/audit')
        self.denied('POST', '/api/options/permissions', {'permissions': {}})
        self.grant('view_menu_options_permissions')
        self.assertEqual(self.client.get('/api/options/permissions').status_code, 200)
        audit = self.client.get('/api/options/permissions/audit').json()
        self.assertFalse(audit['enforcement_verified'])
        self.assertTrue(audit['route_coverage']['complete'])
        self.assertEqual(self.client.post('/api/options/permissions', headers=self.headers, json={'permissions': {}}).status_code, 200)
        self.revoke('view_menu_options_permissions')
        self.denied('POST', '/api/options/permissions', {'permissions': {}})

    def test_first_employee_delete_and_revocation_follow_capabilities(self):
        self.grant('view_menu_references_users')
        self.assertFalse(self.client.get(self.path).json()['can_delete'])
        self.denied('DELETE', self.path)
        self.grant('user_delete')
        self.assertTrue(self.client.get(self.path).json()['can_delete'])
        self.revoke('user_delete')
        self.assertFalse(self.client.get(self.path).json()['can_delete'])
        self.denied('DELETE', self.path)
        self.grant('user_delete')
        self.assertEqual(self.client.delete(self.path, headers=self.headers).status_code, 200)
        self.assertIsNotNone(self.target.deleted_at)