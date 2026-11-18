import unittest

from sqlalchemy import create_engine, text

from app.db import Base
from app.historical_audit import audit_database
from app import models  # noqa: F401


class HistoricalAuditTests(unittest.TestCase):
    def test_audit_is_read_only_and_reports_calc_details(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO orders (id,title,order_type,status_id,printing,total,calc_details) VALUES (1,'A','poly',1,1,0,'a:1:{s:8:\"printing\";i:1;}')"))
        result = audit_database(engine)
        self.assertEqual(result["calculation_details"]["decoded"], 1)
        self.assertTrue(result["read_only"])

    def test_audit_reports_customer_payer_associations_without_mutating_them(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO customers (id,title,profit) VALUES (1,'Client',0)"))
            connection.execute(text("INSERT INTO payers (id,title,profit) VALUES (2,'Payer',0)"))
            connection.execute(text("INSERT INTO customer_payer (id,customer_id,payer_id) VALUES (3,1,2)"))
        result = audit_database(engine)
        self.assertEqual(result["customer_payer"]["pivot_rows"], 1)
        self.assertEqual(result["customer_payer"]["valid_pairs"], 1)
        self.assertEqual(result["customer_payer"]["duplicate_pairs"], 0)
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM customer_payer")).scalar(), 1)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()