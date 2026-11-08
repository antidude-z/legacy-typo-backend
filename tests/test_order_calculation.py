from datetime import date
from decimal import Decimal
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Blank, Compile, CompileStage, CompileStageMaterial, Material, Order, OrderCompile, OrderMarkup, OrderOtherWork, OtherWork, Paper, Price, Rate
from app.orders import calculate_order


class OrderCalculationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.order = Order(id=1, title="Order", order_type="poly", status_id=1, printing=100, total=250)
        self.paper = Paper(id=1, title="Paper", weight=80)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_blank_component_and_markup_aggregation(self):
        blank = Blank(id=1, order_id=1, title="Blank", paper_id=1, paper_price=2,
                      details_per_sheet=1, details_per_blank=1, different_details=1,
                      cutting=1, colors_front=1, colors_back=0)
        markup = OrderMarkup(order_id=1, markup_type="paper", value=10, active=True)
        self.db.add_all([self.order, self.paper, blank, markup])
        self.db.commit()
        result = calculate_order(self.db, self.order)
        self.assertEqual(result["components"]["paper"], "200.00")
        self.assertAlmostEqual(float(result["markups"]["paper"]["total"]), 220.0)
        self.assertAlmostEqual(float(result["result"]), 220.0)
        self.assertEqual(result["status"], "calculated")
        self.assertEqual(result["pending_components"], [])

    def test_compilation_fitting_stages_and_material_breakdown(self):
        self.order.printing = 10
        compile_item = Compile(id=1, title="Сборка", fitting=5)
        stage = CompileStage(id=1, compile_id=1, title="Этап", together=2, waste=1, weight=1)
        material = Material(id=1, title="Клей")
        stage_material = CompileStageMaterial(id=1, compile_stage_id=1, material_id=1, quantity=2)
        relation = OrderCompile(order_id=1, compile_id=1, quantity=2)
        self.db.add_all([self.order, compile_item, stage, material, stage_material, relation])
        self.db.add_all([
            Price(priceable_id=1, priceable_type="App\\Compile", amount=3, currency="RUB", actual_from=0, actual_since=date(2020, 1, 1)),
            Price(priceable_id=1, priceable_type="App\\Material", amount=4, currency="RUB", actual_from=0, actual_since=date(2020, 1, 1)),
        ])
        self.db.commit()
        result = calculate_order(self.db, self.order)
        # Printing becomes 10 + 5 fitting; compile cost is quantity * printing * price.
        self.assertEqual(result["production_printing"], 15)
        self.assertEqual(Decimal(result["components"]["compile"]), 90)
        stage_result = result["work_details"]["compile"][0]["stages"][0]
        self.assertEqual(stage_result["payment_count"], 15)
        self.assertEqual(Decimal(stage_result["materials"][1]["cost"]), 120)
        self.assertEqual(result["pending_components"], [])

    def test_cumulative_fitting_changes_blanks_not_saved_quantity(self):
        self.db.add_all([
            self.order, self.paper,
            Compile(id=1, title="First", fitting=5), Compile(id=2, title="Second", fitting=10),
            OrderCompile(order_id=1, compile_id=1, quantity=2),
            OrderCompile(order_id=1, compile_id=2, quantity=1),
            Blank(order_id=1, title="Blank", paper_id=1, paper_price=2,
                  details_per_sheet=1, details_per_blank=1, different_details=1),
            Price(priceable_type="App\\Compile", priceable_id=1, amount=3,
                  actual_since=date(2020, 1, 1), actual_from=0),
            Price(priceable_type="App\\Compile", priceable_id=2, amount=4,
                  actual_since=date(2020, 1, 1), actual_from=0),
        ])
        self.db.commit()
        result = calculate_order(self.db, self.order)
        self.assertEqual(result["production_printing"], 115)
        self.assertEqual(Decimal(result["components"]["compile"]), 1090)
        self.assertEqual(Decimal(result["components"]["paper"]), 230)
        self.db.refresh(self.order)
        self.assertEqual(self.order.printing, 100)

    def test_compilation_missing_price_is_explicit(self):
        self.db.add_all([self.order, Compile(id=1, title="Work", fitting=2),
                         OrderCompile(order_id=1, compile_id=1, quantity=1)])
        self.db.commit()
        result = calculate_order(self.db, self.order)
        self.assertIn("compile:1", result["missing"])
        self.assertEqual(Decimal(result["components"]["compile"]), 0)

    def test_other_work_uses_assigned_price_and_current_rate(self):
        self.db.add_all([self.order, OtherWork(id=1, title="Delivery"),
                         OrderOtherWork(order_id=1, other_work_id=1, quantity=3, price_id=7),
                         Price(id=7, priceable_id=1, priceable_type="OtherWork", amount=2, currency="USD", actual_from=999, actual_since=date(2099, 1, 1)),
                         Rate(usd=100, eur=110, actual_since=date(2020, 1, 1))])
        self.db.commit()
        result = calculate_order(self.db, self.order)
        self.assertEqual(Decimal(result["components"]["other_works"]), 600)
        self.assertEqual(Decimal(result["work_details"]["other_works"][0]["cost"]), 600)
        self.assertEqual(result["status"], "calculated")

    def test_other_work_missing_assigned_price_is_explicit(self):
        self.db.add_all([self.order, OtherWork(id=1, title="Delivery"),
                         OrderOtherWork(order_id=1, other_work_id=1, quantity=1, price_id=999)])
        self.db.commit()
        result = calculate_order(self.db, self.order)
        self.assertEqual(result["components"]["other_works"], "0")
        self.assertIn("other_works:1:price:999", result["missing"])
        self.assertEqual(result["status"], "missing_prices")

    def test_other_work_markup_and_deleted_assignment(self):
        from datetime import datetime

        self.db.add_all([
            self.order, OtherWork(id=1, title="Delivery"),
            Price(id=1, priceable_type="App\\OtherWork", priceable_id=1,
                  amount=10, currency="RUB", actual_since=date(2020, 1, 1)),
            OrderOtherWork(order_id=1, other_work_id=1, quantity=2, price_id=1),
            OrderOtherWork(order_id=1, other_work_id=1, quantity=100, price_id=1,
                           deleted_at=datetime(2020, 1, 1)),
            OrderMarkup(order_id=1, markup_type="other_works", value=25, active=True),
        ])
        self.db.commit()
        result = calculate_order(self.db, self.order)
        self.assertEqual(Decimal(result["components"]["other_works"]), 20)
        self.assertEqual(Decimal(result["result"]), 25)
        self.assertEqual(len(result["work_details"]["other_works"]), 1)
        self.assertEqual(self.order.total, 250)

    def test_additive_schema_upgrade_preserves_existing_rows(self):
        from unittest.mock import patch
        from sqlalchemy import text
        from app.schema import upgrade_local_schema

        old_engine = create_engine("sqlite:///:memory:")
        try:
            with old_engine.begin() as connection:
                connection.execute(text("CREATE TABLE compiles (id INTEGER PRIMARY KEY, title TEXT)"))
                connection.execute(text("INSERT INTO compiles VALUES (1, 'Existing')"))
            with patch("app.schema.engine", old_engine):
                upgrade_local_schema()
                upgrade_local_schema()
            with old_engine.connect() as connection:
                self.assertEqual(tuple(connection.execute(text("SELECT title, fitting FROM compiles")).one()), ("Existing", 0))
        finally:
            old_engine.dispose()


if __name__ == "__main__":
    unittest.main()