import unittest

from sqlalchemy import create_engine, text

from app.db import Base
from app import models  # noqa: F401
from app.validate_import import validate_import


class ImportValidationTests(unittest.TestCase):
    def test_clean_import_is_valid(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        result = validate_import(engine)
        self.assertTrue(result["valid"])
        self.assertEqual(result["foreign_key_violations"], [])

    def test_foreign_key_violation_is_reported(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO order_statuses (id, title, sequence) VALUES (1, 'Status', 1)"))
            connection.execute(text("INSERT INTO orders (id, title, order_type, status_id, printing, total) VALUES (1, 'Order', 'poly', 1, 1, 0)"))
        engine.dispose()
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO order_statuses (id, title, sequence) VALUES (1, 'Status', 1)"))
            connection.execute(text("INSERT INTO orders (id, title, order_type, status_id, printing, total) VALUES (1, 'Order', 'poly', 1, 1, 0)"))
            connection.execute(text("INSERT INTO order_prepresses (id, order_id, prepress_id, quantity) VALUES (1, 999, 999, 1)"))
        result = validate_import(engine)
        self.assertFalse(result["valid"])
        self.assertTrue(result["preservation_valid"])
        self.assertTrue(result["foreign_key_violations"])
        self.assertIn("order_prepresses->prepresses", result["foreign_key_summary"])


if __name__ == "__main__":
    unittest.main()