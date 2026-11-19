"""Serialize cooperating security writers, including imported MyISAM tables.

MySQL named locks are connection-scoped, not transaction/engine scoped. SQLite
uses an OS file lock across processes. Neither mechanism protects direct SQL by
an operator; database maintenance must stop application writers.
"""
from contextlib import contextmanager
from functools import wraps
import hashlib
import inspect
import os
from pathlib import Path
import tempfile
import time

from fastapi import HTTPException
from sqlalchemy import select, text

from .models import User, role_permissions

ADMIN_PERMISSION = 'view_menu_options_permissions'


@contextmanager
def security_lock(db):
    engine = db.get_bind()
    if engine.dialect.name == 'mysql':
        # Keep this dedicated connection checked out until after the caller's
        # commit; a Session commit must not return the lock owner to the pool.
        with engine.connect() as owner:
            name = 'typography-security-' + hashlib.sha256(str(engine.url.database).encode()).hexdigest()[:32]
            acquired = owner.scalar(text('SELECT GET_LOCK(:name, 10)'), {'name': name})
            if acquired != 1:
                raise HTTPException(503, 'Security administration is busy; retry.')
            try:
                yield
            finally:
                if owner.scalar(text('SELECT RELEASE_LOCK(:name)'), {'name': name}) != 1:
                    owner.invalidate()
    elif engine.dialect.name == 'sqlite':
        database = engine.url.database
        key = str(Path(database).resolve()) if database and database != ':memory:' else str(id(engine))
        path = Path(tempfile.gettempdir()) / ('typography-security-' + hashlib.sha256(key.encode()).hexdigest() + '.lock')
        with path.open('a+b') as handle:
            handle.seek(0); handle.write(b'0'); handle.flush()
            deadline = time.monotonic() + 10
            while True:
                try:
                    handle.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise HTTPException(503, 'Security administration is busy; retry.')
                    time.sleep(.02)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)
    else:
        raise HTTPException(503, 'Unsupported security-lock database.')


def security_writer(function):
    signature = inspect.signature(function)

    @wraps(function)
    def guarded(*args, **kwargs):
        db = signature.bind(*args, **kwargs).arguments['db']
        if db.new or db.dirty or db.deleted:
            raise RuntimeError('Security writer requires a clean session')
        db.rollback()  # End any earlier snapshot before waiting for the lock.
        with security_lock(db):
            db.expire_all()
            try:
                return function(*args, **kwargs)
            except BaseException:
                db.rollback()
                raise
    return guarded


def require_surviving_admin(db, *, identity=None, changes=None, removed=False, admin_roles=None):
    """Check the proposed state before any write (works without MyISAM rollback)."""
    current_roles = set(db.scalars(select(role_permissions.c.role_id).where(
        role_permissions.c.permission_id == ADMIN_PERMISSION)))
    proposed_roles = current_roles if admin_roles is None else set(admin_roles)
    before, after = set(), set()
    for row in db.execute(select(User.id, User.role_id, User.fired, User.deleted_at)):
        if row.role_id in current_roles and not row.fired and row.deleted_at is None:
            before.add(row.id)
        values = dict(row._mapping)
        if row.id == identity:
            if removed:
                continue
            values.update(changes or {})
        if values['role_id'] in proposed_roles and not values['fired'] and values['deleted_at'] is None:
            after.add(row.id)
    if before and not after:
        raise HTTPException(409, 'Cannot disable the last effective security administrator.')