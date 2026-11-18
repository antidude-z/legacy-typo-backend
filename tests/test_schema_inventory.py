import tempfile
import unittest
from pathlib import Path

from app.schema_inventory import compare_schemas, dump_schema


class SchemaInventoryTests(unittest.TestCase):
    def test_dump_parser_reads_tables_and_columns_without_executing_sql(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "dump.sql"
            dump.write_text(
                "CREATE TABLE `orders` (\n"
                "  `id` bigint(20) NOT NULL,\n"
                "  `title` varchar(255) NOT NULL,\n"
                ") ENGINE=InnoDB;\n"
                "CREATE TABLE `users` (\n"
                "  `id` int(11) NOT NULL\n"
                ");\n",
                encoding="utf-8",
            )
            self.assertEqual(dump_schema(dump), {"orders": ["id", "title"], "users": ["id"]})

    def test_comparison_reports_missing_and_extra_schema_names(self):
        result = compare_schemas(
            {"orders": ["id", "legacy_field"], "old_table": ["id"]},
            {"orders": ["id", "new_field"], "new_table": ["id"]},
        )
        self.assertEqual(result["missing_tables_in_rework"], ["old_table"])
        self.assertEqual(result["extra_tables_in_rework"], ["new_table"])
        self.assertEqual(result["column_differences"]["orders"], {
            "missing_in_rework": ["legacy_field"],
            "extra_in_rework": ["new_field"],
        })


if __name__ == "__main__":
    unittest.main()