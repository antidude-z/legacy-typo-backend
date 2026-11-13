import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.bootstrap import SCHEMA_VERSION, initialize_database
from app.db import Base
from app.models import OrderStatus, Permission, Rate, Report, ReportParam, Role, SchemaVersion, Service, role_permissions


class BootstrapTests(unittest.TestCase):
    def make_engine(self):
        return create_engine("sqlite://")

    def test_fresh_database_gets_legacy_catalogs_and_version(self):
        engine = self.make_engine()
        initialize_database(engine)
        with Session(engine) as db:
            self.assertEqual(db.query(SchemaVersion).count(), 1)
            self.assertIsNotNone(db.get(SchemaVersion, SCHEMA_VERSION))
            self.assertEqual(db.query(Role).count(), 7)
            self.assertEqual(db.query(Permission).count(), 47)
            self.assertEqual(db.query(OrderStatus).count(), 6)
            self.assertEqual(db.query(Report).count(), 6)
            self.assertEqual(db.query(ReportParam).count(), 8)
            self.assertEqual(db.query(Service).count(), 1)
            self.assertEqual(db.query(Rate).count(), 7)
            admin = db.scalar(select(Role).where(Role.title == "Администратор"))
            manager = db.scalar(select(Role).where(Role.title == "Менеджер"))
            self.assertEqual(len(admin.permissions), 47)
            self.assertEqual({permission.id for permission in manager.permissions}, {
                "view_menu_orders", "view_menu_references", "view_menu_references_customers"
            })
        engine.dispose()

    def test_repeated_initialization_is_idempotent(self):
        engine = self.make_engine()
        initialize_database(engine)
        initialize_database(engine)
        with Session(engine) as db:
            self.assertEqual(db.query(SchemaVersion).count(), 1)
            self.assertEqual(db.query(Role).count(), 7)
            self.assertEqual(db.query(Permission).count(), 47)
            self.assertEqual(db.query(ReportParam).count(), 8)
            self.assertEqual(db.query(Service).count(), 1)
            self.assertEqual(db.query(Rate).count(), 7)
            self.assertEqual(db.execute(select(role_permissions.c.role_id, role_permissions.c.permission_id)).all().__len__(), 97)
        engine.dispose()

    def test_existing_rows_and_nonstandard_role_ids_are_preserved(self):
        engine = self.make_engine()
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(Role(id=50, title="Администратор"))
            db.add(OrderStatus(id=50, title="Custom", sequence=99))
            db.commit()
        initialize_database(engine)
        with Session(engine) as db:
            admin = db.scalar(select(Role).where(Role.title == "Администратор"))
            self.assertEqual(admin.id, 50)
            self.assertIsNotNone(db.get(OrderStatus, 50))
            self.assertEqual(db.scalar(select(OrderStatus).where(OrderStatus.title == "Custom")).sequence, 99)
            self.assertEqual(len(admin.permissions), 47)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()