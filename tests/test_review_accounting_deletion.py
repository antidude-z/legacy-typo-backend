"""S06 real-session lifecycle regressions on disposable SQLite."""
from datetime import date, datetime
import unittest

from app.models import Bill, Payment
from tests import test_review_employee_authorization as fixtures


class AccountingDeletionTests(unittest.TestCase):
    mysql = False
    tearDown = fixtures.EmployeeAuthorizationReviewTests.tearDown
    grant = fixtures.EmployeeAuthorizationReviewTests.grant
    snapshot = fixtures.EmployeeAuthorizationReviewTests.snapshot

    def setUp(self):
        fixtures.EmployeeAuthorizationReviewTests.setUp(self)
        self.grant('view_accounting_bills')
        self.db.add_all([Bill(id=1, number='Synthetic', amount=10),
                         Bill(id=2, number='Other', amount=10),
                         Payment(id=1, bill_id=1, amount=5, payment_date=date(2026,1,1))])
        self.db.commit()
        self.paths = ['/api/accounting/bills/1', '/api/accounting/bills/1/payments/1']

    def denied(self, method, path, status=403):
        before = self.snapshot()
        for _ in range(2):
            response = self.client.request(method, path, headers=self.headers)
            self.assertEqual(response.status_code, status, response.text)
            self.assertEqual(self.snapshot(), before)

    def test_editor_saves_but_cannot_delete_or_restore(self):
        self.grant('edit_accounting_bills', 'restore_trashed', 'delete_trashed')
        for path, payload in zip(self.paths, [
                {'number':'Changed','bill_date':'2026-01-01','amount':'10'},
                {'payment_date':'2026-01-01','amount':'7'}]):
            self.assertEqual(self.client.patch(path, json=payload, headers=self.headers).status_code,200)
            self.denied('DELETE',path)
            self.denied('POST',path+'/restore')
            data=self.client.get(path).json()
            self.assertTrue(data['can_edit'])
            self.assertFalse(data['can_delete'])
            self.assertFalse(data['can_restore'])
            self.assertFalse(data['can_delete_trashed'])

    def test_domain_delete_and_lifecycle_conjunction_without_edit(self):
        self.grant('delete_accounting_bills')
        for path in self.paths:
            self.role.permissions=[p for p in self.role.permissions if p.id != 'restore_trashed']
            self.db.commit()
            self.assertTrue(self.client.get(path).json()['can_delete'])
            self.assertEqual(self.client.delete(path,headers=self.headers).status_code,200)
            self.denied('DELETE',path)
            self.denied('POST',path+'/restore')
            self.grant('restore_trashed') if not self.actor.has_permission('restore_trashed') else None
            self.assertEqual(self.client.post(path+'/restore',headers=self.headers).status_code,200)
        self.grant('delete_trashed')
        # Delete child first, preserving parent scope until the child is removed.
        for path in reversed(self.paths):
            self.assertEqual(self.client.delete(path,headers=self.headers).status_code,200)
            self.assertEqual(self.client.delete(path,headers=self.headers).status_code,200)
        self.assertIsNone(self.db.get(Payment,1))
        self.assertIsNone(self.db.get(Bill,1))

    def test_trash_grants_and_delete_without_read_are_insufficient(self):
        self.grant('restore_trashed','delete_trashed')
        for path in self.paths:
            self.denied('DELETE',path)
            self.denied('POST',path+'/restore')
        self.role.permissions.clear(); self.db.commit()
        self.grant('delete_accounting_bills','restore_trashed','delete_trashed')
        for path in self.paths:
            self.denied('DELETE',path)
            self.denied('POST',path+'/restore')

    def test_payment_parent_ownership_deleted_parent_and_revocation(self):
        self.grant('delete_accounting_bills','view_trashed','restore_trashed','delete_trashed')
        self.denied('DELETE','/api/accounting/bills/2/payments/1',404)
        self.denied('POST','/api/accounting/bills/2/payments/1/restore',404)
        self.db.get(Bill,1).deleted_at=datetime(2026,1,1); self.db.commit()
        self.denied('DELETE',self.paths[1],404)
        self.denied('POST',self.paths[1]+'/restore',404)
        self.db.get(Bill,1).deleted_at=None
        self.role.permissions=[p for p in self.role.permissions if p.id != 'delete_accounting_bills']
        self.db.commit()
        for path in self.paths:
            self.denied('DELETE',path)