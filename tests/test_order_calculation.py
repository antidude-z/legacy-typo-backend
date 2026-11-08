from datetime import date
from decimal import Decimal
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Blank, Order, OrderMarkup, Paper
from app.orders import calculate_order


class OrderCalculationTests(unittest.TestCase):
    def test_blank_component_and_markup_aggregation(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = Session(engine)
        order = Order(id=1, title="Order", order_type="poly", status_id=1, printing=100, total=250)
        paper = Paper(id=1, title="Paper", weight=80)
        blank = Blank(id=1, order_id=1, title="Blank", paper_id=1, paper_price=2,
                      details_per_sheet=1, details_per_blank=1, different_details=1,
                      cutting=1, colors_front=1, colors_back=0)
        markup = OrderMarkup(order_id=1, markup_type="paper", value=10, active=True)
        db.add_all([order, paper, blank, markup])
        db.commit()
        result = calculate_order(db, order)
        self.assertEqual(result["components"]["paper"], "200.00")
        self.assertAlmostEqual(float(result["markups"]["paper"]["total"]), 220.0)
        self.assertAlmostEqual(float(result["result"]), 220.0)
        self.assertEqual(result["status"], "partial")
        self.assertIn("compile", result["pending_components"])
        db.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()