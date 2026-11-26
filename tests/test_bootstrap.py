import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.bootstrap import SCHEMA_VERSION, initialize_database, preview_initialization, PERMISSIONS
from app.db import Base
from app.models import Format, Option, OrderStatus, PaperFormatFormat, Permission, Rate, Report, ReportParam, Role, SchemaVersion, Service, CustomerContact, User, role_permissions


class BootstrapTests(unittest.TestCase):
    def make_engine(self):
        return create_engine("sqlite://")

    def test_preview_never_creates_tables_and_matches_fresh_baseline(self):
        from sqlalchemy import inspect
        engine = self.make_engine()
        try:
            preview = preview_initialization(engine)
            self.assertEqual(inspect(engine).get_table_names(), [])
            self.assertEqual(preview['mode'], 'fresh')
            self.assertEqual(len(preview['grant_additions']), 2 * len(PERMISSIONS) + 3)
            initialize_database(engine)
            with Session(engine) as db:
                actual = {(role.title, permission.id) for role in db.scalars(select(Role))
                          for permission in role.permissions}
            self.assertEqual(actual, {(row['role_title'], row['permission_id'])
                                      for row in preview['grant_additions']})
            upgraded = preview_initialization(engine)
            self.assertEqual(upgraded['mode'], 'upgrade')
            self.assertEqual(upgraded['grant_additions'], [])
            self.assertEqual(upgraded['grant_removals'], [])
        finally:
            engine.dispose()

    def test_fresh_database_gets_legacy_catalogs_and_version(self):
        engine = self.make_engine()
        initialize_database(engine)
        with Session(engine) as db:
            self.assertEqual(db.query(SchemaVersion).count(), 1)
            self.assertIsNotNone(db.get(SchemaVersion, SCHEMA_VERSION))
            self.assertEqual(db.query(Role).count(), 7)
            self.assertEqual(db.query(Permission).count(), 78)
            self.assertEqual(db.query(OrderStatus).count(), 6)
            self.assertEqual(db.query(Report).count(), 6)
            self.assertEqual(db.query(ReportParam).count(), 8)
            self.assertEqual(db.query(Service).count(), 1)
            self.assertEqual(db.query(Rate).count(), 7)
            self.assertEqual(db.query(Option).count(), 3)
            self.assertEqual(db.query(Format).count(), 0)
            self.assertEqual(db.query(CustomerContact).count(), 0)
            self.assertEqual(db.query(PaperFormatFormat).count(), 0)
            admin = db.scalar(select(Role).where(Role.title == "Администратор"))
            manager = db.scalar(select(Role).where(Role.title == "Менеджер"))
            self.assertEqual(len(admin.permissions), 48)
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
            self.assertEqual(db.query(Permission).count(), 78)
            self.assertEqual(db.query(ReportParam).count(), 8)
            self.assertEqual(db.query(Service).count(), 1)
            self.assertEqual(db.query(Rate).count(), 7)
            self.assertEqual(db.query(Option).count(), 3)
            self.assertEqual(db.execute(select(role_permissions.c.role_id, role_permissions.c.permission_id)).all().__len__(), 99)
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
            self.assertEqual(admin.permissions, [])
        engine.dispose()

    def test_legacy_roles_without_version_marker_preserve_restricted_grants(self):
        engine = self.make_engine()
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            restricted = Permission(id='view_menu_orders', title='Orders', module='orders')
            leadership = Role(id=91, title='Руководство', permissions=[restricted])
            db.add_all([restricted, leadership])
            db.commit()
            before = {(role.id, permission.id) for role in db.query(Role).all() for permission in role.permissions}

        preview = preview_initialization(engine)
        self.assertEqual(preview['mode'], 'upgrade')
        self.assertEqual(preview['grant_additions'], [])
        self.assertEqual(preview['existing_grants'], [{'id': 1, 'role_id': 91, 'permission_id': 'view_menu_orders'}])

        initialize_database(engine)
        initialize_database(engine)

        with Session(engine) as db:
            leadership = db.scalar(select(Role).where(Role.id == 91))
            after = {(role.id, permission.id) for role in db.query(Role).all() for permission in role.permissions}
            self.assertEqual(leadership.title, 'Руководство')
            self.assertEqual(after, before)
            self.assertEqual(len(leadership.permissions), 1)
            self.assertIsNotNone(db.get(SchemaVersion, SCHEMA_VERSION))
        engine.dispose()

    def test_existing_catalog_gets_payroll_gate_without_role_escalation(self):
        engine = self.make_engine()
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(SchemaVersion(version=SCHEMA_VERSION))
            db.add(Role(title="Existing role"))
            db.commit()
        initialize_database(engine)
        initialize_database(engine)
        with Session(engine) as db:
            self.assertIsNotNone(db.get(Permission, 'edit_reports_payrolls'))
            from app.reference_works import WORK_CAPABILITIES
            for identity, _ in WORK_CAPABILITIES:
                self.assertIsNotNone(db.get(Permission, identity))
            self.assertEqual(db.scalar(select(Role)).permissions, [])
        engine.dispose()

    def test_partial_account_import_never_receives_baseline_grants(self):
        for partial in ('user', 'permission'):
            with self.subTest(partial=partial):
                engine = self.make_engine()
                try:
                    Base.metadata.create_all(engine)
                    with Session(engine) as db:
                        if partial == 'user':
                            db.add(User(name='Imported pending', email='pending@example.test', password='unchanged'))
                        else:
                            db.add(Permission(id='custom_imported', title='Custom', module='custom'))
                        db.commit()
                    initialize_database(engine)
                    initialize_database(engine)
                    with Session(engine) as db:
                        self.assertEqual(db.execute(select(role_permissions)).all(), [])
                        if partial == 'user':
                            user = db.scalar(select(User))
                            self.assertIsNone(user.role_id)
                            self.assertEqual(user.password, 'unchanged')
                finally:
                    engine.dispose()

    def test_removed_marker_does_not_restore_intentionally_revoked_grants(self):
        engine = self.make_engine()
        try:
            initialize_database(engine)
            with Session(engine) as db:
                for role in db.scalars(select(Role)).all():
                    role.permissions.clear()
                db.delete(db.get(SchemaVersion, SCHEMA_VERSION))
                db.commit()
            initialize_database(engine)
            initialize_database(engine)
            with Session(engine) as db:
                self.assertEqual(db.execute(select(role_permissions)).all(), [])
        finally:
            engine.dispose()

    def test_s03_capabilities_are_cataloged_but_never_automatically_assigned(self):
        from app.s03_policy import policy_payload
        capabilities = {domain[action] for domain in policy_payload()['domains'] for action in ('edit', 'delete')}
        engine = self.make_engine()
        initialize_database(engine)
        with Session(engine) as db:
            assigned_before = set(db.execute(select(role_permissions)).all())
            self.assertTrue(all(db.get(Permission, identity) for identity in capabilities))
            self.assertFalse(any(row.permission_id in capabilities for row in assigned_before))
            role = db.scalar(select(Role).where(Role.title == 'Менеджер'))
            role.permissions.append(db.get(Permission, 'edit_orders'))
            db.commit()
            approved = set(db.execute(select(role_permissions)).all())
        initialize_database(engine)
        with Session(engine) as db:
            self.assertEqual(set(db.execute(select(role_permissions)).all()), approved)
        engine.dispose()

    def test_s04_delegation_is_cataloged_without_automatic_grants(self):
        engine = self.make_engine()
        try:
            initialize_database(engine)
            initialize_database(engine)
            with Session(engine) as db:
                for identity in ('user_assign_role', 'user_reset_credentials'):
                    self.assertIsNotNone(db.get(Permission, identity))
                    self.assertEqual(db.execute(select(role_permissions).where(
                        role_permissions.c.permission_id == identity)).all(), [])
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()