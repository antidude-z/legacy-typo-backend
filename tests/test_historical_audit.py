import unittest

from sqlalchemy import create_engine, text

from app.db import Base
from app.historical_audit import audit_database
from app import models  # noqa: F401


class HistoricalAuditTests(unittest.TestCase):
    def test_audit_is_read_only_and_reports_calc_details(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
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

    def test_audit_reports_payroll_snapshots_and_eligibility_integrity(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id,name,surname,email,password,fired) VALUES (1,'M','Manager','m@example.test','x',0)"))
            connection.execute(text("INSERT INTO order_statuses (id,title,sequence) VALUES (1,'Draft',1)"))
            connection.execute(text("INSERT INTO bills (id,number,amount,currency,paid,closed,filed) VALUES (1,'B',10,'RUB',1,1,1)"))
            connection.execute(text("INSERT INTO orders (id,title,order_type,status_id,printing,total,user_id,bill_id) VALUES (1,'Order','poly',1,1,10,1,1)"))
            connection.execute(text("INSERT INTO payrolls (id,user_id,salary,period,status) VALUES (1,1,0,'2024-01-01','paid')"))
            connection.execute(text("INSERT INTO payroll_orders (id,payroll_id,order_id,title,printing,bill_number,materials,works,contractors,total,percent,salary) VALUES (1,1,1,'Order',1,'B',0,0,0,10,3,0)"))
        result = audit_database(engine)
        self.assertEqual(result['payroll']['statements'], 1)
        self.assertEqual(result['payroll']['paid_statements'], 1)
        self.assertEqual(result['payroll']['paid_snapshot_rows'], 1)
        self.assertEqual(result['payroll']['orphan_snapshot_rows'], 0)
        self.assertEqual(result['payroll']['duplicate_statement_orders'], 0)
        self.assertEqual(result['payroll']['invalid_percent_rows'], 0)
        self.assertEqual(result['payroll']['eligible_orders'], 1)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()