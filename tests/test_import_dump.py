import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.import_dump import import_dump
from app.models import Option, Order


class DumpImportTests(unittest.TestCase):
    def make_dump(self, directory):
        path = Path(directory) / "small.sql"
        path.write_text(
            """CREATE TABLE `options` (
  `id` int,
  `depart` varchar(50),
  `alias` varchar(50),
  `title` varchar(50),
  `value` varchar(50),
  `actual_since` date,
  `deleted_at` timestamp,
  `created_at` timestamp,
  `updated_at` timestamp
);
CREATE TABLE `orders` (
  `id` int,
  `title` varchar(100),
  `order_type` varchar(20),
  `status_id` int,
  `printing` int,
  `volume` varchar(50),
  `format` varchar(50),
  `width` decimal(8,2),
  `height` decimal(8,2),
  `order_date` date,
  `prod_date` date,
  `deadline` date,
  `customer_id` int,
  `user_id` int,
  `comment` text,
  `total` decimal(10,2),
  `calc_details` text,
  `files` text,
  `bill_id` int,
  `prepress` int,
  `compile` int,
  `other` int,
  `deleted_at` timestamp,
  `created_at` timestamp,
  `updated_at` timestamp
);
INSERT INTO `options` VALUES (1,'markups','min_markup','Максимальная скидка','-5','1970-01-01',NULL,'2016-01-01 00:00:00','2016-01-01 00:00:00');
INSERT INTO `orders` (`id`,`title`,`order_type`,`status_id`,`printing`,`format`,`order_date`,`prod_date`,`deadline`,`customer_id`,`user_id`,`total`,`comment`,`files`,`bill_id`) VALUES (7,'Test','poly',1,1000,'A4','2016-01-01','0000-00-00','0000-00-00',1,1,10,'','',1);
INSERT INTO `migrations` VALUES (1,'ignored');
""", encoding="utf-8")
        return path

    def test_import_is_allowlisted_and_converts_zero_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine("sqlite://")
            Base.metadata.create_all(engine)
            result = import_dump(engine, self.make_dump(directory))
            self.assertEqual(result["rows"], {"options": 1, "orders": 1})
            self.assertIn("migrations", result["skipped_rows"])
            with Session(engine) as db:
                self.assertEqual(db.get(Option, 1).value, "-5")
                self.assertIsNone(db.get(Order, 7).prod_date)

    def test_dry_run_does_not_write_and_existing_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine("sqlite://")
            Base.metadata.create_all(engine)
            self.assertEqual(import_dump(engine, self.make_dump(directory), dry_run=True, tables=["orders"])["rows"]["orders"], 1)
            with Session(engine) as db:
                self.assertIsNone(db.get(Order, 7))
                db.add(Order(id=7, title="existing", order_type="poly", status_id=1, printing=1))
                db.commit()
            with self.assertRaises(ValueError):
                import_dump(engine, self.make_dump(directory))
            engine.dispose()


if __name__ == "__main__":
    unittest.main()