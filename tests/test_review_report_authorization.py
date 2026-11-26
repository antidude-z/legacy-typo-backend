"""S05 real sessions and guarded disposable fixtures, never working DB writes."""
from datetime import datetime
import unittest

from app.models import Bill, Order, OrderStatus, Report, ReportParam
from tests import test_review_employee_authorization as employee


class ReportAuthorizationReviewTests(unittest.TestCase):
    mysql = False
    tearDown = employee.EmployeeAuthorizationReviewTests.tearDown
    grant = employee.EmployeeAuthorizationReviewTests.grant
    snapshot = employee.EmployeeAuthorizationReviewTests.snapshot

    def setUp(self):
        employee.EmployeeAuthorizationReviewTests.setUp(self)
        self.grant('view_menu_orders')
        self.db.add_all([
            Bill(id=51, number='Protected bill', amount=100),
            OrderStatus(id=1, title='Draft', sequence=1),
            Order(id=61, title='Protected order', order_type='poly', printing=10,
                  bill_id=51, status_id=1, calc_details='{"printing":10,"blanks":{}}'),
            Report(id='order_payment', title='Payment', model='App\\Bill', kind='xls', form=True),
            Report(id='order_shipping', title='Shipping', model='App\\Bill', kind='pdf'),
            Report(id='order_transcript', title='Transcript', model='App\\Order', kind='html'),
            Report(id='unknown_model', title='Unknown', model='App\\Unknown', kind='html'),
            ReportParam(report_id='order_payment', alias='boss', title='Confidential', value='Hidden signatory'),
        ])
        for identity, kind in (('order_passport','pdf'), ('order_passport_wide','pdf'),
                               ('order_economy','xls'), ('order_economy_wide','xls'),
                               ('order_design','xls')):
            self.db.add(Report(id=identity,title=identity,model='App\\Order',kind=kind))
        self.db.commit()

    def calls(self, domain):
        if domain == 'bills':
            return [('GET','/api/reports/for/bills/51'),
                    ('GET','/api/reports/form/order_payment/51'),
                    ('GET','/api/reports/form/order_shipping/51')] + [
                        (method,f'/reports/{report}/item/51')
                        for method in ('GET','POST') for report in ('order_payment','order_shipping')]
        return [('GET','/api/reports/for/orders/61')] + [
            (method,f'/reports/{report}/item/61') for method in ('GET','POST')
            for report in ('order_transcript','order_passport','order_passport_wide',
                           'order_economy','order_economy_wide','order_design')]

    def check_denied(self, calls, status):
        before = self.snapshot()
        for method,path in calls:
            for _ in range(2):
                response = self.client.request(method,path,headers=self.headers)
                self.assertEqual(response.status_code,status,(method,path,response.text))
                self.assertNotIn('Hidden signatory',response.text)
                self.assertNotIn('Protected order',response.text)
                self.assertNotIn('content-disposition',response.headers)
                self.assertEqual(self.snapshot(),before)

    def test_orders_only_cannot_read_bill_reports(self):
        self.check_denied(self.calls('bills') + [('GET','/api/reports/bills/51/orders')],403)
        self.assertEqual(self.client.get('/reports/order_transcript/item/61').status_code,200)

    def test_bill_reader_cannot_read_order_reports_or_collection(self):
        self.role.permissions.clear(); self.db.commit()
        self.grant('view_accounting_bills')
        self.check_denied(self.calls('orders') + [('GET','/api/reports/bills/51/orders')],403)
        for method,path in self.calls('bills'):
            response=self.client.request(method,path,headers=self.headers)
            self.assertEqual(response.status_code,200,(path,response.text[:100]))

    def test_guest_roleless_and_unrelated_staff_denied(self):
        self.role.permissions.clear(); self.db.commit()
        self.grant('view_menu_options_reports')
        self.check_denied(self.calls('orders')+self.calls('bills'),403)
        self.actor.role=None; self.db.commit()
        self.check_denied(self.calls('orders')+self.calls('bills'),403)
        self.client.cookies.clear()
        self.headers={'X-CSRF-Token':self.client.get('/api/csrf-token').json()['token']}
        self.check_denied(self.calls('orders')+self.calls('bills'),401)

    def test_readers_success_revocation_and_active_parent_scope(self):
        self.grant('view_accounting_bills','view_trashed')
        for method,path in self.calls('orders')+self.calls('bills')+[('GET','/api/reports/bills/51/orders')]:
            response=self.client.request(method,path,headers=self.headers)
            self.assertEqual(response.status_code,200,(path,response.text[:100]))
        self.db.get(Bill,51).deleted_at=datetime(2026,1,1)
        self.db.get(Order,61).deleted_at=datetime(2026,1,1)
        self.db.commit()
        self.check_denied(self.calls('orders')+self.calls('bills')+[('GET','/api/reports/bills/51/orders')],404)

    def test_report_and_parent_ids_resolved_independently(self):
        self.grant('view_accounting_bills')
        self.check_denied([('GET','/api/reports/form/order_payment/61'),
                           ('GET','/reports/order_payment/item/61'),
                           ('POST','/reports/order_transcript/item/51'),
                           ('GET','/reports/missing/item/51'),
                           ('GET','/reports/unknown_model/item/61'),
                           ('GET','/api/reports/for/unknown/51')],404)
        self.db.get(Report,'order_payment').deleted_at=datetime(2026,1,1); self.db.commit()
        self.check_denied([('GET','/api/reports/form/order_payment/51'),
                           ('GET','/reports/order_payment/item/51')],404)

    def test_read_grant_revocation_applies_next_request(self):
        self.grant('view_accounting_bills')
        self.assertEqual(self.client.get('/api/reports/form/order_payment/51').status_code,200)
        self.role.permissions=[p for p in self.role.permissions if p.id != 'view_accounting_bills']
        self.db.commit()
        self.check_denied(self.calls('bills'),403)