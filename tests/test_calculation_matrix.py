"""Fixed-date, hand-calculated regression fixtures; not legacy golden outputs."""
from datetime import date, datetime
from decimal import Decimal
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (Afterprint, AfterprintStage, Blank, Material, Order, OrderMarkup, Paper, Price,
                        Printer, PrinterProcess, PrinterProcessStage, Rate)
from app.orders import calculate_afterprint, calculate_order, calculate_printer, currency_rate, resolve_price
from app.php_serialization import loads


class CalculationMatrixTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_all_order_types_quantity_rounding_markups_and_repeatability(self):
        self.db.add_all([Paper(id=1, title='Paper'), Material(id=1, title='Vinyl')])
        identity = 0
        for kind in ('book', 'poly', 'wide', 'souvenir'):
            for printing in (0, 1, 7, 1001):
                for active, markup in ((True, 10), (True, -20), (False, 10)):
                    identity += 1
                    with self.subTest(kind=kind, printing=printing, active=active, markup=markup):
                        order = Order(id=identity, title='Fixture', order_type=kind, status_id=1,
                                      printing=printing, total=Decimal('999.99'), order_date=date(2024, 1, 1))
                        blank = Blank(order_id=identity, title='Blank', paper_id=1, material_id=1,
                                      paper_price=Decimal('1.25'), details_per_sheet=2,
                                      details_per_blank=1, different_details=1, cutting=3,
                                      width=Decimal('2'), height=Decimal('1.5'))
                        self.db.add_all([order, blank, OrderMarkup(order_id=identity, markup_type='paper', value=markup, active=active)])
                        self.db.commit()
                        # Production preserves zero printing; only the per-item
                        # division uses one to avoid division by zero.
                        quantity = max(printing, 1)
                        sheets = ((printing + 1) // 2 + 2) // 3
                        base = Decimal('1.25') * (printing * 3 if kind == 'wide' else 0 if kind == 'souvenir' else sheets)
                        expected = base * (Decimal(1) + Decimal(markup) / 100) if active else Decimal(0)
                        result = calculate_order(self.db, order)
                        self.assertEqual(Decimal(result['components']['paper']), base)
                        self.assertEqual(Decimal(result['result']), expected)
                        self.assertEqual(Decimal(result['item']), expected / quantity)
                        expected_manager = Decimal(100) * (Decimal('999.99') - expected) / expected if expected else Decimal(0)
                        self.assertEqual(Decimal(result['manager_markup']), expected_manager)
                        self.assertEqual(result['status'], 'calculated')
                        self.assertEqual(order.total, Decimal('999.99'))
                        serialized = order.calc_details
                        self.assertEqual(loads(serialized)['printing'], printing)
                        repeated = calculate_order(self.db, order)
                        self.assertEqual(repeated, result)
                        self.assertEqual(order.calc_details, serialized)

    def test_price_dates_tiers_deleted_prices_and_currency_cross_rates(self):
        self.db.add_all([
            Rate(usd=80, eur=100, actual_since=date(2000, 1, 1)),
            Rate(usd=90, eur=120, actual_since=date(2001, 1, 1)),
            Rate(usd=999, eur=999, actual_since=date(2002, 1, 1), deleted_at=datetime(2002, 1, 2)),
            Price(priceable_type='App\\Paper', priceable_id=1, amount=1, currency='EUR', actual_from=0, actual_since=date(2000, 1, 1)),
            Price(priceable_type='App\\Paper', priceable_id=1, amount=2, currency='EUR', actual_from=10, actual_since=date(2000, 1, 1)),
            Price(priceable_type='App\\Paper', priceable_id=1, amount=3, currency='EUR', actual_from=10, actual_since=date(2001, 1, 1)),
            Price(priceable_type='App\\Paper', priceable_id=1, amount=999, currency='EUR', actual_from=10, actual_since=date(2001, 1, 2), deleted_at=datetime(2001, 1, 3)),
        ])
        self.db.commit()
        for quantity, effective, amount in [(9, date(2001, 1, 1), 120), (10, date(2000, 1, 1), 240), (10, date(2001, 1, 1), 360)]:
            with self.subTest(quantity=quantity, effective=effective):
                result = resolve_price(self.db, 'App\\Paper', 1, quantity, effective)
                self.assertEqual(result['amount'], Decimal(amount))
        for source, target, expected in [('USD', 'EUR', Decimal('0.75')), ('EUR', 'USD', Decimal(120) / 90), ('RUB', 'USD', Decimal(1) / 90), ('EUR', 'RUB', Decimal(120))]:
            self.assertEqual(currency_rate(self.db, source, target, date(2001, 1, 1)), expected)
        self.assertFalse(resolve_price(self.db, 'App\\Paper', 1, 10, date(1999, 1, 1))['found'])
        self.assertEqual(currency_rate(self.db, 'USD', 'RUB', date(1999, 1, 1)), 1)

    def test_printer_one_pass_separate_pass_and_missing_dependencies(self):
        self.db.add_all([
            Printer(id=1, title='One pass'), Printer(id=2, title='Separate'), Printer(id=3, title='No process'),
            PrinterProcess(id=1, printer_id=1, title='4+4', colors_front=4, colors_back=4),
            PrinterProcess(id=2, printer_id=2, title='2+0', colors_front=2, colors_back=0),
            PrinterProcessStage(id=1, printer_process_id=1, title='Stage', colors=2, together=10, waste=2),
            PrinterProcessStage(id=2, printer_process_id=2, title='Stage', colors=2, together=10, waste=2),
            Price(priceable_type='App\\PrinterProcessStage', priceable_id=1, amount=Decimal('1.25'), currency='RUB', actual_since=date(2000, 1, 1)),
            Price(priceable_type='App\\PrinterProcessStage', priceable_id=2, amount=Decimal('1.25'), currency='RUB', actual_since=date(2000, 1, 1)),
        ])
        self.db.commit()
        one = calculate_printer(self.db, 1, 101, 4, 4, date(2024, 1, 1))
        separate = calculate_printer(self.db, 2, 101, 4, 4, date(2024, 1, 1))
        self.assertEqual(one['result'], Decimal('13.75'))
        self.assertEqual(one['pl_count'], 103)
        self.assertEqual(separate['result'], Decimal('55.00'))
        self.assertEqual(separate['pl_count'], 109)
        self.assertEqual([stage['payment_count'] for stage in separate['details']['stages']], [22, 22])
        self.assertEqual(calculate_printer(self.db, 3, 101, 4, 4)['status'], 'missing_process')
        self.assertEqual(calculate_printer(self.db, 999, 101, 4, 4)['status'], 'missing_printer')
        missing = calculate_printer(self.db, 1, 101, 4, 4, date(1999, 1, 1))
        self.assertEqual(missing['status'], 'missing_prices')
        self.assertEqual(missing['result'], 0)

    def test_afterprint_weight_boundaries_wide_mode_and_fractional_counts(self):
        paper = Paper(id=1, title='Boundary paper', weight=80)
        blank = Blank(order_id=1, title='Boundary blank', paper=paper)
        self.db.add_all([
            paper, blank, Afterprint(id=1, title='Finish'),
            AfterprintStage(id=1, afterprint_id=1, title='Light', min_paper_weight=0, max_paper_weight=80, together=10, waste=0),
            AfterprintStage(id=2, afterprint_id=1, title='Heavy', min_paper_weight=80, max_paper_weight=200, together=10, waste=2),
            Price(priceable_type='App\\AfterprintStage', priceable_id=1, amount=2, currency='RUB', actual_since=date(2000, 1, 1)),
            Price(priceable_type='App\\AfterprintStage', priceable_id=2, amount=3, currency='RUB', actual_since=date(2000, 1, 1)),
        ])
        self.db.commit()
        normal = calculate_afterprint(self.db, blank, 11, 1, Decimal('1.5'), 'poly', date(2024, 1, 1))
        self.assertEqual(normal['result'], 9)
        self.assertEqual(normal['pl_count'], 17)
        wide = calculate_afterprint(self.db, blank, 11, 1, Decimal('1.5'), 'wide', date(2024, 1, 1))
        self.assertEqual(wide['result'], 15)
        self.assertEqual(wide['pl_count'], 17)