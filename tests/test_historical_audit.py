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


if __name__ == "__main__":
    unittest.main()