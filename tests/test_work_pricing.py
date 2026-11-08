from datetime import date, datetime, timedelta
from decimal import Decimal
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Order, OrderMarkup, OrderPrepress, OrderRedaction, Prepress, Price, Rate, Redaction
from app.orders import calculate_order


class WorkPricingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.order = Order(id=1, title="Book", order_type="book", status_id=1,
                           printing=10, order_date=date(2000, 1, 1), total=1000)
        self.db.add_all([
            self.order, Prepress(id=1, title="Design"), Redaction(id=1, title="Editing"),
            OrderPrepress(order_id=1, prepress_id=1, quantity=3, price_id=999),
            OrderRedaction(order_id=1, redaction_id=1, quantity=2),
            OrderMarkup(order_id=1, markup_type="design", active=True, value=10),
            OrderMarkup(order_id=1, markup_type="redaction", active=True, value=-20),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def price(self, kind, amount, since=date(2020, 1, 1), threshold=0, currency="RUB"):
        self.db.add(Price(priceable_type=f"App\\{kind}", priceable_id=1,
                          amount=amount, currency=currency, actual_since=since,
                          actual_from=threshold))

    def test_current_zero_threshold_prices_and_markups(self):
        self.price("Prepress", 5, date(1999, 1, 1))
        self.price("Prepress", 10)
        self.price("Prepress", 999, threshold=2)
        self.price("Prepress", 999, since=date.today() + timedelta(days=1))
        self.price("Redaction", 20)
        self.db.commit()
        result = calculate_order(self.db, self.order)
        self.assertEqual(Decimal(result["components"]["design"]), 30)
        self.assertEqual(Decimal(result["components"]["redaction"]), 40)
        self.assertEqual(Decimal(result["result"]), 65)
        self.assertEqual(Decimal(result["item"]), Decimal("6.5"))
        self.assertEqual(self.order.total, 1000)
        self.assertEqual(result["pending_components"], ["other_works"])
        self.assertEqual(result["work_details"]["design"][0]["title"], "Design")

    def test_missing_prices_are_zero_and_explicit(self):
        result = calculate_order(self.db, self.order)
        self.assertEqual(set(result["missing"]), {"design:1", "redaction:1"})
        self.assertEqual(Decimal(result["result"]), 0)

    def test_inactive_markup_does_not_hide_cost_breakdown(self):
        self.price("Prepress", 10)
        self.db.query(OrderMarkup).filter_by(markup_type="design").one().active = False
        self.db.commit()
        result = calculate_order(self.db, self.order)
        self.assertEqual(Decimal(result["components"]["design"]), 30)
        self.assertEqual(Decimal(result["markups"]["design"]["base"]), 0)

    def test_deleted_operations_and_references_are_excluded(self):
        self.price("Prepress", 10)
        self.price("Redaction", 20)
        self.db.query(OrderPrepress).one().deleted_at = datetime(2020, 1, 1)
        self.db.get(Redaction, 1).deleted_at = datetime(2020, 1, 1)
        self.db.commit()
        result = calculate_order(self.db, self.order)
        self.assertEqual(result["work_details"], {"design": [], "redaction": [], "compile": []})

    def test_currency_conversion(self):
        self.price("Prepress", 2, currency="USD")
        self.price("Redaction", 4)
        self.db.add(Rate(usd=100, eur=110, actual_since=date(2020, 1, 1)))
        self.db.commit()
        result = calculate_order(self.db, self.order)
        self.assertEqual(Decimal(result["components"]["design"]), 600)


if __name__ == "__main__":
    unittest.main()