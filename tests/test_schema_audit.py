import unittest
from sqlalchemy import create_engine, text, inspect
from app.schema_audit import audit_schema
from app.schema import apply_migrations, migration_2026_11_19_04


class SchemaAuditTests(unittest.TestCase):
    def test_fractional_work_quantities_round_trip_in_fresh_schema(self):
        from sqlalchemy.orm import Session
        from app.models import OrderPrepress, OrderRedaction
        from decimal import Decimal
        engine = create_engine('sqlite://')
        try:
            apply_migrations(engine)
            with Session(engine) as db:
                db.add_all([OrderPrepress(order_id=1, prepress_id=1, quantity=Decimal('1.25')),
                            OrderRedaction(order_id=1, redaction_id=1, quantity=Decimal('2.75'))])
                db.commit()
                self.assertEqual(db.query(OrderPrepress).first().quantity, Decimal('1.25'))
                self.assertEqual(db.query(OrderRedaction).first().quantity, Decimal('2.75'))
        finally:
            engine.dispose()

    def test_audit_reports_drift_without_changing_schema(self):
        engine = create_engine('sqlite://')
        try:
            with engine.begin() as connection:
                connection.execute(text('CREATE TABLE bills (id INTEGER PRIMARY KEY, number VARCHAR(2), amount NUMERIC(6,1), bill_date DATE)'))
            before = inspect(engine).get_table_names()
            audit = audit_schema(engine)
            self.assertEqual(before, inspect(engine).get_table_names())
            differences = audit['tables']['bills']['differences']
            self.assertTrue(any(row['issue'] == 'decimal_precision' for row in differences))
            self.assertTrue(any(row['issue'] == 'missing_column' for row in differences))
            self.assertTrue(audit['tables']['orders']['missing_table'])
        finally:
            engine.dispose()

    def test_indexes_are_added_once_without_replacing_existing_equivalents(self):
        engine = create_engine('sqlite://')
        try:
            apply_migrations(engine)
            with engine.begin() as connection:
                connection.execute(text('DROP INDEX ix_customer_payer_customer_id'))
                connection.execute(text('CREATE INDEX historical_customer ON customer_payer(customer_id)'))
                connection.execute(text('DROP INDEX ix_customer_payer_payer_id'))
                migration_2026_11_19_04(connection)
                migration_2026_11_19_04(connection)
            names = {row['name'] for row in inspect(engine).get_indexes('customer_payer')}
            self.assertIn('historical_customer', names)
            self.assertNotIn('ix_customer_payer_customer_id', names)
            self.assertIn('ix_customer_payer_payer_id', names)
            self.assertEqual(apply_migrations(engine), [])
        finally:
            engine.dispose()