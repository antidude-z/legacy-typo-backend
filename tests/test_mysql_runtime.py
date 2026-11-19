"""Opt-in real MySQL CRUD checks. Never point at a business database."""
import os
import unittest
from contextlib import contextmanager
from io import BytesIO
from uuid import uuid4
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app
from app.models import Bill, Order, OrderStatus, Payer, Role, User, Payment, Payroll, PayrollOrder, Report
from app.orders import legacy_date
from app.schema import apply_migrations
from app.mysql_test_guard import validate_test_url


class LegacyDateTests(unittest.TestCase):
    def test_mysql_zero_dates_and_valid_dates(self):
        self.assertIsNone(legacy_date('0000-00-00'))
        self.assertIsNone(legacy_date(None))
        self.assertEqual(legacy_date(date(2024, 1, 2)), '2024-01-02')
        from app.reports import _date
        self.assertEqual(_date('0000-00-00'), '')
        self.assertEqual(_date('2024-01-02'), '02.01.2024')


@unittest.skipUnless(os.getenv('MYSQL_TEST_URL'), 'MYSQL_TEST_URL not configured')
class MySQLRuntimeTests(unittest.TestCase):
    @contextmanager
    def historical_client(self):
        url = os.environ['MYSQL_TEST_URL']
        validate_test_url(url, os.getenv('DATABASE_URL'))
        if make_url(url).database != 'typography_fullclone_test':
            self.skipTest('Requires full historical clone')
        engine = create_engine(url)
        apply_migrations(engine)
        try:
            with Session(engine) as db:
                actor = db.scalars(select(User).where(User.deleted_at.is_(None))).first()
                self.assertIsNotNone(actor, 'Historical users are required')
                def database():
                    yield db
                previous = app.dependency_overrides.copy()
                app.dependency_overrides[get_db] = database
                try:
                    with patch('app.main.current_user', return_value=actor), patch.object(User, 'has_permission', return_value=True), TestClient(app, raise_server_exceptions=False) as client:
                        yield db, client
                finally:
                    app.dependency_overrides.clear()
                    app.dependency_overrides.update(previous)
        finally:
            engine.dispose()

    def assert_artifact(self, response, kind, download=True):
        self.assertEqual(response.status_code, 200, response.text[:200] if response.status_code != 200 else '')
        if kind == 'pdf':
            from pypdf import PdfReader
            document = PdfReader(BytesIO(response.content))
            self.assertGreater(len(document.pages), 0)
            self.assertTrue(any(page.extract_text().strip() for page in document.pages))
            self.assertIn('application/pdf', response.headers['content-type'])
        elif kind == 'xls':
            import xlrd
            workbook = xlrd.open_workbook(file_contents=response.content)
            self.assertGreater(workbook.nsheets, 0)
            self.assertGreater(workbook.sheet_by_index(0).nrows, 0)
            self.assertIn('application/vnd.ms-excel', response.headers['content-type'])
        else:
            self.assertEqual(kind, 'html')
            self.assertIn('text/html', response.headers['content-type'])
        if kind != 'html' and download:
            self.assertIn('filename=', response.headers.get('content-disposition', ''))

    def test_historical_bill_payment_totals(self):
        with self.historical_client() as (db, client):
            bills = db.scalars(select(Bill).where(Bill.deleted_at.is_(None)).order_by(Bill.id.desc()).limit(10)).all()
            paid_bill = db.scalar(select(Bill).join(Payment, Payment.bill_id == Bill.id).where(Bill.deleted_at.is_(None), Payment.deleted_at.is_(None)).order_by(Bill.id).limit(1))
            self.assertIsNotNone(paid_bill, 'Require a historical bill with payments')
            bills.append(paid_bill)
            for bill in bills:
                with self.subTest(bill=bill.id):
                    response = client.get(f'/api/accounting/bills/{bill.id}')
                    self.assertEqual(response.status_code, 200, response.text[:200])
                    data = response.json()
                    expected = db.scalar(select(func.sum(Payment.amount)).where(Payment.bill_id == bill.id, Payment.deleted_at.is_(None))) or Decimal('0')
                    self.assertEqual(Decimal(data['item']['paid_sum']), expected)
                    self.assertEqual(Decimal(data['orders_total']), sum((Decimal(row['total']) for row in data['orders']), Decimal('0')))
                    self.assertEqual(data['item']['paid'], bill.paid)

    def test_historical_reference_and_pricing_catalogs(self):
        with self.historical_client() as (_, client):
            paths = [f'/api/references/{kind}' for kind in ('paper', 'materials', 'printers', 'afterprints', 'compiles')]
            paths += ['/api/customer-references', '/api/employee-references']
            paths += [f'/api/reference-works/{kind}' for kind in ('prepresses', 'redactions')]
            paths += [f'/api/pricing/catalog/{kind}' for kind in ('services', 'paper', 'print', 'materials', 'afterprint', 'prepress', 'redaction', 'compile', 'compiles')]
            for path in paths:
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200, response.text[:200])
                    self.assertIsInstance(response.json()['items'], list)

    def test_every_active_historical_report_and_form(self):
        with self.historical_client() as (db, client):
            reports = db.scalars(select(Report).where(Report.deleted_at.is_(None)).order_by(Report.id)).all()
            self.assertGreaterEqual(len(reports), 6)
            for report in reports:
                with self.subTest(report=report.id):
                    if report.model == 'App\\Bill':
                        item = db.scalar(select(Bill).join(Order, Order.bill_id == Bill.id).where(Bill.deleted_at.is_(None), Order.deleted_at.is_(None)).order_by(Bill.id.desc()).limit(1))
                    else:
                        self.assertEqual(report.model, 'App\\Order')
                        query = select(Order).where(Order.deleted_at.is_(None), Order.calc_details.is_not(None), Order.calc_details != '')
                        blocked = [int(value) for value in report.prohibitions.split(',') if value.strip().isdigit()]
                        if blocked:
                            query = query.where(Order.status_id.not_in(blocked))
                        item = db.scalar(query.order_by(Order.id.desc()).limit(1))
                    self.assertIsNotNone(item, 'Require an eligible historical report record')
                    discovery = client.get(f'/api/reports/for/{"bills" if report.model == "App\\Bill" else "orders"}/{item.id}')
                    self.assertEqual(discovery.status_code, 200, discovery.text[:200])
                    action = next(row for row in discovery.json()['items'] if row['id'] == report.id)
                    self.assertTrue(action['available'], action)
                    self.assertFalse(action['blocked'], action)
                    url = f'/reports/{report.id}/item/{item.id}'
                    if report.form:
                        form = client.get(f'/api/reports/form/{report.id}/{item.id}')
                        self.assertEqual(form.status_code, 200, form.text[:200])
                        fields = form.json()['fields']
                        self.assertTrue(fields)
                        response = client.post(url, data={field['name']: field['default'] for field in fields})
                    else:
                        response = client.get(url)
                    self.assert_artifact(response, report.kind, report.download)

    def test_historical_paid_payroll_snapshots(self):
        with self.historical_client() as (db, client):
            statements = db.scalars(select(Payroll).where(Payroll.status == 'paid').order_by(Payroll.id.desc()).limit(3)).all()
            self.assertTrue(statements, 'Require paid historical payrolls')
            for statement in statements:
                with self.subTest(payroll=statement.id):
                    rows = db.scalars(select(PayrollOrder).where(PayrollOrder.payroll_id == statement.id).order_by(PayrollOrder.id)).all()
                    before = [(row.id, row.salary, row.percent, row.total) for row in rows]
                    response = client.get(f'/api/reports/payrolls/{statement.id}')
                    self.assertEqual(response.status_code, 200, response.text[:200])
                    data = response.json()['item']
                    self.assertEqual(len(data['orders']), len(rows))
                    self.assertEqual(Decimal(data['orders_salary']), sum((row.salary for row in rows), Decimal('0')))
                    self.assert_artifact(client.get(f'/reports/payrolls/{statement.id}/export'), 'xls')
                    db.expire_all()
                    after = db.scalars(select(PayrollOrder).where(PayrollOrder.payroll_id == statement.id).order_by(PayrollOrder.id)).all()
                    self.assertEqual(before, [(row.id, row.salary, row.percent, row.total) for row in after])

    def test_real_mysql_crud_round_trip(self):
        url = os.environ['MYSQL_TEST_URL']
        validate_test_url(url, os.getenv('DATABASE_URL'))
        engine = create_engine(url)
        apply_migrations(engine)
        with Session(engine) as db:
            role = db.get(Role, 1)
            if role is None:
                role = Role(id=1, title='VM test')
                db.add(role)
                db.flush()
            actor = User(name='VM test', surname='Test', phone='', post='', role_id=1, email=f'{uuid4().hex}@example.test', password='unused')
            status = db.get(OrderStatus, 1)
            if status is None:
                status = OrderStatus(id=1, title='VM test', sequence=1)
            payer = Payer(title='VM test payer', inn='', phone='', address='', description='')
            db.add_all([actor, status, payer]); db.commit()
            def database():
                yield db
            app.dependency_overrides[get_db] = database
            try:
                with patch('app.main.current_user', return_value=actor), patch.object(User, 'has_permission', return_value=True):
                    client = TestClient(app)
                    payload = {'bill_number': 'VM-test', 'bill_date': '2024-01-02', 'bill_manager': actor.id, 'bill_payer': payer.id, 'bill_amount': '123.45', 'bill_currency': 'RUB'}
                    response = client.post('/api/accounting/bills', json=payload)
                    self.assertEqual(response.status_code, 200, response.text)
                    bill_id = response.json()['id']
                    self.assertEqual(client.patch(f'/api/accounting/bills/{bill_id}', json={**payload, 'bill_amount': '200.00'}).status_code, 200)
                    response = client.post(f'/api/accounting/bills/{bill_id}/payments', json={'payment_amount': '12.34', 'payment_date': '2024-01-03'})
                    self.assertEqual(response.status_code, 200, response.text)
                    payment_id = response.json()['id']
                    self.assertEqual(client.get(f'/api/accounting/bills/{bill_id}').json()['item']['paid_sum'], '12.34')
                    self.assertEqual(client.delete(f'/api/accounting/bills/{bill_id}/payments/{payment_id}').status_code, 200)
                    self.assertEqual(Decimal(client.get(f'/api/accounting/bills/{bill_id}').json()['item']['paid_sum']), Decimal('0.00'))
                    response = client.post('/api/orders/add/poly', data={'order_title': 'VM test order', 'order_printing': '100'})
                    self.assertEqual(response.status_code, 200, response.text)
                    order_id = response.json()['id']
                    response = client.post(f'/api/orders/{order_id}/blanks', json={'title': 'VM test blank', 'details_per_sheet': 1, 'printer_process_id': '', 'paper_id': '', 'material_id': ''})
                    self.assertEqual(response.status_code, 200, response.text)
                    blank_id = response.json()['id']
                    updated = client.patch(f'/api/orders/{order_id}/blanks/{blank_id}', json={'printer_process_id': '', 'paper_id': '', 'material_id': ''})
                    self.assertEqual(updated.status_code, 200, updated.text)
                    self.assertEqual(client.get(f'/api/orders/{order_id}/blanks').status_code, 200)
                    self.assertEqual(client.delete(f'/api/orders/{order_id}').status_code, 200)
                    self.assertEqual(client.post(f'/api/orders/{order_id}/restore').status_code, 200)
                    self.assertIsNotNone(db.get(Order, order_id))
                    self.assertIsNotNone(db.get(Bill, bill_id))
            finally:
                app.dependency_overrides.clear()
        engine.dispose()

    def test_full_clone_historical_reads_and_reports(self):
        url = os.environ['MYSQL_TEST_URL']
        validate_test_url(url, os.getenv('DATABASE_URL'))
        if make_url(url).database != 'typography_fullclone_test':
            self.skipTest('Requires full historical clone')
        engine = create_engine(url)
        apply_migrations(engine)
        failures = []
        with Session(engine) as db:
            actor = db.scalars(select(User).where(User.deleted_at.is_(None))).first()
            def database():
                yield db
            app.dependency_overrides[get_db] = database
            try:
                with patch('app.main.current_user', return_value=actor), patch.object(User, 'has_permission', return_value=True):
                    client = TestClient(app, raise_server_exceptions=False)
                    for kind in ('book', 'poly', 'wide', 'souvenir'):
                        orders = db.scalars(select(Order).where(Order.order_type == kind, Order.deleted_at.is_(None), Order.calc_details.is_not(None)).order_by(Order.id.desc()).limit(3)).all()
                        for order in orders:
                            paths = [f'/api/orders/{order.id}', f'/api/orders/{order.id}/blanks', f'/api/orders/{order.id}/operations', f'/api/orders/{order.id}/history']
                            for report in ('order_transcript', 'order_passport', 'order_economy', 'order_design'):
                                paths.append(f'/reports/{report}/item/{order.id}')
                            for path in paths:
                                response = client.get(path)
                                if response.status_code not in (200, 403, 422):
                                    failures.append((path, response.status_code, response.text[:200]))
                            response = client.post(f'/api/orders/{order.id}/recalculate', json={})
                            if response.status_code != 200:
                                failures.append((f'recalculate/{order.id}', response.status_code, response.text[:200]))
            finally:
                app.dependency_overrides.clear()
        engine.dispose()
        self.assertEqual(failures, [], failures)