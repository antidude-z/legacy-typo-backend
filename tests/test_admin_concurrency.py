"""S01 competing operator changes; isolated file SQLite or guarded MySQL only."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import threading
import unittest
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.admin_safety import ADMIN_PERMISSION
from app.admin_safety import require_surviving_admin, security_writer
from app.assign_role import assign_role
from app.db import Base
from app.models import Permission, Role, User, role_permissions
from app.mysql_test_guard import verify_test_database


class AdminConcurrencyChecks:
    def test_competing_demotions_preserve_exactly_one_effective_admin(self):
        self.competing_changes(False)

    def test_matrix_revocation_competes_with_operator_demotion(self):
        self.competing_changes(True)

    def competing_changes(self, matrix):
        with tempfile.TemporaryDirectory() as directory:
            if self.mysql:
                url = os.environ['MYSQL_TEST_URL']
                verify_test_database(url, os.getenv('DATABASE_URL'))
            else:
                path = Path(directory) / 's01-test.db'
                self.assertFalse(path.exists())
                url = f'sqlite:///{path.as_posix()}'
            engine = create_engine(url)
            try:
                if not self.mysql:
                    Base.metadata.create_all(engine)
                with Session(engine) as db:
                    if db.scalar(select(User.id).limit(1)) is not None:
                        raise RuntimeError('Requires empty disposable security fixture database')
                suffix = uuid4().hex
                with Session(engine) as db:
                    permission = db.get(Permission, ADMIN_PERMISSION)
                    created_permission = permission is None
                    if permission is None:
                        permission = Permission(id=ADMIN_PERMISSION, title='Security', module='options')
                    admin = Role(title='QA admin ' + suffix[:12], permissions=[permission])
                    other_admin = Role(title='QA second ' + suffix[:12], permissions=[permission])
                    staff = Role(title='QA staff ' + suffix[:12])
                    users = [User(name='QA', email=f'{suffix}-{n}@example.test', password='unused', role=role)
                             for n, role in enumerate((admin, other_admin))]
                    db.add_all([admin, staff, *users]); db.commit()
                    ids, admin_id, other_admin_id, staff_id = [u.id for u in users], admin.id, other_admin.id, staff.id
                barrier = threading.Barrier(2)

                @security_writer
                def revoke(db):
                    from fastapi import HTTPException
                    roles = set(db.scalars(select(role_permissions.c.role_id).where(
                        role_permissions.c.permission_id == ADMIN_PERMISSION))) - {other_admin_id}
                    try:
                        require_surviving_admin(db, admin_roles=roles)
                    except HTTPException as exc:
                        raise ValueError(exc.detail) from exc
                    db.execute(role_permissions.delete().where(role_permissions.c.role_id == other_admin_id))
                    db.commit()

                def demote(identity):
                    with Session(engine) as db:
                        barrier.wait(timeout=10)
                        try:
                            if matrix and identity == ids[1]:
                                revoke(db)
                            else:
                                assign_role(db, f'id:{identity}', f'id:{staff_id}', True)
                            return 'changed'
                        except ValueError:
                            return 'denied'

                with ThreadPoolExecutor(max_workers=2) as pool:
                    outcomes = list(pool.map(demote, ids))
                self.assertCountEqual(outcomes, ['changed', 'denied'])
                with Session(engine) as db:
                    effective = db.scalars(select(User.id).join(role_permissions,
                        role_permissions.c.role_id == User.role_id).where(
                        role_permissions.c.permission_id == ADMIN_PERMISSION)).all()
                    self.assertEqual(len(effective), 1)
                    for identity in ids:
                        db.delete(db.get(User, identity))
                    db.flush()
                    admin = db.get(Role, admin_id)
                    admin.permissions.clear()
                    other_admin = db.get(Role, other_admin_id)
                    other_admin.permissions.clear()
                    db.delete(admin); db.delete(other_admin); db.delete(db.get(Role, staff_id))
                    if created_permission:
                        db.delete(db.get(Permission, ADMIN_PERMISSION))
                    db.commit()
            finally:
                engine.dispose()


class SQLiteAdminConcurrencyTests(AdminConcurrencyChecks, unittest.TestCase):
    mysql = False


@unittest.skipUnless(os.getenv('MYSQL_ADMIN_TEST_URL'), 'Dedicated empty MySQL test schema required')
class MySQLAdminConcurrencyTests(AdminConcurrencyChecks, unittest.TestCase):
    mysql = True

    def setUp(self):
        from unittest.mock import patch
        self.environment = patch.dict(os.environ, {'MYSQL_TEST_URL': os.environ['MYSQL_ADMIN_TEST_URL']})
        self.environment.start()
        self.addCleanup(self.environment.stop)