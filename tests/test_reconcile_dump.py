import tempfile
import unittest
from pathlib import Path

from app.reconcile_dump import audit_dump


class DumpReconciliationTests(unittest.TestCase):
    def test_audit_counts_rows_and_exposes_relationship_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "small.sql"
            dump.write_text(
                "CREATE TABLE `options` (\n"
                "  `id` int,\n  `depart` varchar(50),\n  `alias` varchar(50),\n"
                "  `title` varchar(50),\n  `value` varchar(50),\n  `actual_since` date\n);\n"
                "INSERT INTO `options` VALUES (1,'markups','min','Min','-5','1970-01-01');\n"
                "INSERT INTO `migrations` VALUES (1,'ignored');\n",
                encoding="utf-8",
            )
            result = audit_dump(dump)
            self.assertEqual(result["insert_statements"], 2)
            self.assertEqual(result["row_counts"]["options"], 1)
            self.assertEqual(result["framework_rows_excluded"]["migrations"], 1)
            self.assertTrue(result["source_not_modified"])
            self.assertIn("zero_dates", result["conversion_rules"])


if __name__ == "__main__":
    unittest.main()