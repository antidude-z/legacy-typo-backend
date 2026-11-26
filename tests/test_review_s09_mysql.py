"""S09 initialization on guarded, disposable historical FK-free MySQL tables."""
import os
import unittest

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from app.bootstrap import SCHEMA_VERSION, initialize_database, preview_initialization
from app.db import Base
from app.models import Permission, Role, SchemaVersion, User, role_permissions
from app.mysql_test_guard import verify_test_database


@unittest.skipUnless(os.getenv('S09_MYSQL_ENABLED') == '1', 'Requires isolated S09 MySQL')
class MySQLInitializationTests(unittest.TestCase):
    def setUp(self):
        url = os.environ['MYSQL_ADMIN_TEST_URL']
        verify_test_database(url, os.getenv('DATABASE_URL'))
        self.engine = create_engine(url)
        storage = os.environ['S03_MYSQL_ENGINE']
        if storage not in ('InnoDB', 'MyISAM'):
            raise RuntimeError('Unsupported storage engine')
        with self.engine.begin() as connection:
            if list(connection.scalars(text('SHOW TABLES'))):
                raise RuntimeError('S09 requires an empty disposable database')
            for table in Base.metadata.sorted_tables:
                ddl = str(CreateTable(table, include_foreign_key_constraints=[]).compile(self.engine))
                connection.execute(text(ddl + ' ENGINE=' + storage + ' DEFAULT CHARSET=utf8mb3'))

    def tearDown(self):
        try:
            Base.metadata.drop_all(self.engine)
            with self.engine.begin() as connection:
                connection.execute(text('DROP TABLE IF EXISTS schema_migrations'))
        finally:
            self.engine.dispose()

    def test_missing_marker_and_revoked_grants_preserve_exact_assignments(self):
        with Session(self.engine) as db:
            permission = Permission(id='view_menu_orders', title='Historical title', module='orders')
            roles = [Role(id=91, title='Руководство', permissions=[permission]),
                     Role(id=92, title='Администратор'), Role(id=93, title='Менеджер')]
            user = User(name='Imported', email='imported@example.test', password='preserved',
                        role=roles[0], security_stamp='preserved-stamp', remember_token='preserved-digest')
            db.add_all(roles + [user])
            db.commit()
            before = list(db.execute(select(role_permissions).order_by(role_permissions.c.id)))
            users_before = list(db.execute(select(User.__table__)))
        preview = preview_initialization(self.engine)
        self.assertEqual(preview['mode'], 'upgrade')
        self.assertEqual(preview['grant_additions'], [])
        for _ in range(2):
            initialize_database(self.engine)
        with Session(self.engine) as db:
            self.assertEqual(list(db.execute(select(role_permissions).order_by(role_permissions.c.id))), before)
            self.assertEqual(list(db.execute(select(User.__table__))), users_before)
            self.assertEqual(db.get(Permission, 'view_menu_orders').title, 'Historical title')
            revoked_role = db.get(Role, 91)
            revoked_role.permissions.clear()
            db.delete(db.get(SchemaVersion, SCHEMA_VERSION))
            db.commit()
        for _ in range(2):
            initialize_database(self.engine)
        with Session(self.engine) as db:
            self.assertEqual(list(db.execute(select(role_permissions))), [])

    def test_fresh_baseline_matches_read_only_preview(self):
        preview = preview_initialization(self.engine)
        self.assertEqual(preview['mode'], 'fresh')
        initialize_database(self.engine)
        initialize_database(self.engine)
        with Session(self.engine) as db:
            actual = {(role.title, permission.id) for role in db.scalars(select(Role))
                      for permission in role.permissions}
        self.assertEqual(actual, {(row['role_title'], row['permission_id'])
                                 for row in preview['grant_additions']})