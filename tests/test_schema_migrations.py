import unittest

from sqlalchemy import create_engine, inspect, text

from app.schema import MIGRATIONS, MIGRATION_TABLE, apply_migrations, migration_status


class SchemaMigrationTests(unittest.TestCase):
    def test_fresh_database_records_and_repeats_migrations(self):
        database_engine = create_engine("sqlite://")
        self.assertEqual(apply_migrations(database_engine), [version for version, _ in MIGRATIONS])
        self.assertEqual(apply_migrations(database_engine), [])
        self.assertEqual(migration_status(database_engine), [{"version": version, "applied": True} for version, _ in MIGRATIONS])
        self.assertIn(MIGRATION_TABLE, inspect(database_engine).get_table_names())
        database_engine.dispose()

    def test_existing_legacy_shape_gets_missing_columns_without_data_loss(self):
        database_engine = create_engine("sqlite://")
        with database_engine.begin() as connection:
            connection.execute(text("CREATE TABLE papers (id INTEGER PRIMARY KEY, title VARCHAR(50) NOT NULL, type_id INTEGER, format_id INTEGER, weight INTEGER, deleted_at DATETIME)"))
            connection.execute(text("INSERT INTO papers (id, title, weight) VALUES (17, 'Legacy paper', 80)"))
        self.assertNotIn("markup", {column["name"] for column in inspect(database_engine).get_columns("papers")})
        apply_migrations(database_engine)
        columns = {column["name"] for column in inspect(database_engine).get_columns("papers")}
        self.assertIn("markup", columns)
        with database_engine.connect() as connection:
            self.assertEqual(tuple(connection.execute(text("SELECT id, title, weight, markup FROM papers")).one()), (17, "Legacy paper", 80, 10))
        self.assertEqual(apply_migrations(database_engine), [])
        database_engine.dispose()

    def test_status_does_not_create_tables(self):
        database_engine = create_engine("sqlite://")
        self.assertEqual(migration_status(database_engine), [{"version": version, "applied": False} for version, _ in MIGRATIONS])
        self.assertEqual(inspect(database_engine).get_table_names(), [])
        database_engine.dispose()

    def test_legacy_action_mapping_is_repeatable_and_preserves_other_types(self):
        engine = create_engine('sqlite://')
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE actions (id INTEGER PRIMARY KEY, actionable_id VARCHAR(255), actionable_type VARCHAR(255))'))
            connection.execute(text('INSERT INTO actions VALUES (1, :item, :kind), (2, :item, :other)'), {'item': '17', 'kind': 'App\\Order', 'other': 'App\\Bill'})
        apply_migrations(engine)
        apply_migrations(engine)
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text('SELECT item_id FROM actions ORDER BY id')).scalars().all(), [17, None])
        engine.dispose()


if __name__ == "__main__":
    unittest.main()