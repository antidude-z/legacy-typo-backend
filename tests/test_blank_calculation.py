from datetime import date
from decimal import Decimal
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Afterprint, AfterprintStage, AfterprintStageMaterial, Blank, BlankAfterprint, BlankImagesetter,
    Material, Order, Paper, PaperFormat, PaperType, Price, Printer, PrinterField, PrinterProcess, PrinterProcessStage, Service,
)
from app.orders import afterprint_count, calculate_blank, normalize_blank_production


class BlankCalculationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.order = Order(id=1, title="Test", order_type="poly", status_id=1,
                           printing=100, order_date=date(2024, 1, 1))
        self.paper = Paper(id=1, title="Paper", weight=80)
        self.blank = Blank(id=1, order_id=1, title="Blank", paper_id=1,
                           paper_price=2, different_details=1, details_per_blank=1,
                           details_per_sheet=1, cutting=1, colors_front=4, colors_back=4)
        self.db.add_all([self.order, self.paper, self.blank])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def price(self, kind, identity, amount):
        self.db.add(Price(priceable_type=f"App\\{kind}", priceable_id=identity,
                          amount=amount, currency="RUB", actual_from=0,
                          actual_since=date(2020, 1, 1)))

    def test_stored_paper_price_and_persistence(self):
        self.price("Paper", 1, 999)
        self.db.commit()
        result = calculate_blank(self.db, self.blank, self.order)
        self.assertEqual(result["result"], Decimal("200"))
        self.db.refresh(self.blank)
        self.assertEqual(self.blank.cost, Decimal("200"))
        self.assertEqual(self.blank.paper_price, Decimal("2"))

    def test_fractional_sheet_rounding(self):
        self.blank.different_details = 7
        self.blank.details_per_blank = 7
        self.blank.details_per_sheet = 4
        result = calculate_blank(self.db, self.blank, self.order)
        self.assertEqual(result["details"]["steps"], [100, 100])
        self.blank.different_details = 5
        self.blank.details_per_blank = 5
        result = calculate_blank(self.db, self.blank, self.order)
        self.assertEqual(result["details"]["steps"], [100, 50])

    def test_no_sheet_divisor_matches_empty_legacy_steps(self):
        self.blank.details_per_sheet = 0
        self.assertEqual(calculate_blank(self.db, self.blank, self.order)["paper"], 0)

    def test_afterprint_then_printer_waste_and_imagesetter(self):
        self.db.add_all([
            Printer(id=1, title="Press", need_imagesetter=True),
            PrinterProcess(id=1, printer_id=1, title="4+4", colors_front=4, colors_back=4),
            PrinterProcessStage(id=1, printer_process_id=1, title="Setup", colors=1, together=1, waste=2),
            Afterprint(id=1, title="Cut"),
            AfterprintStage(id=1, afterprint_id=1, title="Cut", together=100, waste=5),
            BlankAfterprint(blank_id=1, afterprint_id=1, active=True, parameters='a:1:{i:1;s:1:"2";}'),
            BlankImagesetter(blank_id=1, plates=4),
            Service(id=1, title="Plates", kind="imagesetter"),
        ])
        self.blank.printer_id = 1
        self.price("PrinterProcessStage", 1, 3)
        self.price("AfterprintStage", 1, 10)
        self.price("Service", 1, 5)
        self.db.commit()
        result = calculate_blank(self.db, self.blank, self.order)
        self.assertEqual(result["afterprint"], 20)
        self.assertEqual(result["print"], 336)
        self.assertEqual(result["paper"], 224)
        self.assertEqual(result["imagesetter"], 20)
        self.assertEqual(result["result"], 600)

    def test_wide_uses_area_and_stored_material_price(self):
        self.db.add_all([
            Material(id=1, title="Vinyl"), Printer(id=1, title="Wide"),
            PrinterProcess(id=1, printer_id=1, title="720dpi"),
            PrinterProcessStage(id=1, printer_process_id=1, title="Print", together=1, waste=1),
        ])
        self.order.order_type = "wide"
        self.order.printing = 2
        self.blank.printer_id = 1
        self.blank.printer_process_id = 1
        self.blank.material_id = 1
        self.blank.width = Decimal("2")
        self.blank.height = Decimal("1.5")
        self.blank.paper_price = 4
        self.price("PrinterProcessStage", 1, 5)
        self.db.commit()
        result = calculate_blank(self.db, self.blank, self.order)
        self.assertEqual(result["print"], 45)
        self.assertEqual(result["paper"], 36)
        self.assertEqual(result["result"], 81)

    def test_missing_price_is_explicit(self):
        self.db.add_all([
            Printer(id=1, title="Press"),
            PrinterProcess(id=1, printer_id=1, title="4+4", colors_front=4, colors_back=4),
            PrinterProcessStage(id=1, printer_process_id=1, title="Print", together=1),
        ])
        self.blank.printer_id = 1
        self.db.commit()
        result = calculate_blank(self.db, self.blank, self.order)
        self.assertEqual(result["status"], "missing_prices")
        self.assertIn("printer:1", result["missing"])

    def test_parameter_formats_and_zero(self):
        self.assertEqual(afterprint_count('a:2:{i:3;s:3:"2.5";i:4;s:1:"9";}'), Decimal("2.5"))
        self.assertEqual(afterprint_count('{"3": "0"}'), 0)
        self.assertEqual(afterprint_count("2"), 2)

    def test_blank_production_derives_plates_and_preserves_fixed_override(self):
        values = normalize_blank_production({
            "colors_front": 4, "colors_back": 4, "details_per_sheet": 2,
            "pages_per_sheet": 0, "details_per_blank": 4, "different_details": 3,
            "cutting": 1, "self_print": True,
        })
        self.assertEqual(values["plates"], 8)
        self.assertFalse(values["fix_plates"])
        fixed = normalize_blank_production({**values, "fix_plates": True, "plates": 3})
        self.assertEqual(fixed["plates"], 3)

    def test_blank_production_rejects_ambiguous_imposition_and_missing_wide_area(self):
        with self.assertRaises(ValueError):
            normalize_blank_production({"details_per_sheet": 2, "pages_per_sheet": 2})
        with self.assertRaises(ValueError):
            normalize_blank_production({"details_per_sheet": 2}, "wide")
        wide = normalize_blank_production({"width": "2", "height": "1.5"}, "wide")
        self.assertEqual(wide["details_per_sheet"], 0)
        self.assertEqual(wide["pages_per_sheet"], 0)

    def test_blank_metadata_contains_dependent_reference_data(self):
        from app.orders import blank_metadata
        self.db.add_all([
            PaperType(id=1, title="Offset"),
            PaperFormat(id=1, title="A4", width=210, height=297),
            Paper(id=2, title="Offset A4 80", type_id=1, format_id=1, weight=80),
            Printer(id=2, title="Press", production_poly=True),
            PrinterField(id=2, printer_id=2, paper_format_id=1, width=210, height=297, pieces=2, paper_width=420, paper_height=297),
            Material(id=2, title="Ink", production_poly=True),
        ])
        self.db.commit()
        metadata = blank_metadata(self.db, "poly")
        self.assertEqual(metadata["printers"][0]["id"], 2)
        self.assertEqual(metadata["printer_fields"][0]["pieces"], 2)
        self.assertEqual(metadata["papers"][0]["weight"], 80)
        self.assertEqual(metadata["materials"][0]["id"], 2)

    def test_afterprint_material_is_breakdown_only_like_php(self):
        self.db.add_all([
            Afterprint(id=1, title="Finish"),
            AfterprintStage(id=1, afterprint_id=1, title="Finish", together=100),
            Material(id=1, title="Glue"),
            AfterprintStageMaterial(afterprint_stage_id=1, material_id=1, quantity=2),
            BlankAfterprint(blank_id=1, afterprint_id=1, active=True, parameters="1"),
        ])
        self.price("AfterprintStage", 1, 3)
        self.price("Material", 1, 4)
        self.db.commit()
        result = calculate_blank(self.db, self.blank, self.order)
        self.assertEqual(result["afterprint"], 3)
        stage = result["details"]["afterprint"][0]["steps"][0]["details"]["stages"][0]
        self.assertEqual(Decimal(stage["materials"][0]["cost"]), 8)
        self.assertEqual(result["result"], 203)


if __name__ == "__main__":
    unittest.main()