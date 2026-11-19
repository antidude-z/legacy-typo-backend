"""Opt-in real MySQL CRUD checks. Never point at a business database."""
import os
import unittest
from uuid import uuid4
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app
from app.models import Bill, Order, OrderStatus, Payer, Role, User
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
                    response = client.post(f'/api/orders/{order_id}/blanks', json={'title': 'VM test blank', 'details_per_sheet': 1})
                    self.assertEqual(response.status_code, 200, response.text)
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