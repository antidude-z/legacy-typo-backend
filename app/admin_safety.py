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
import sqlite3

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
        arguments = signature.bind(*args, **kwargs).arguments
        db = arguments['db']
        if db.new or db.dirty or db.deleted:
            raise RuntimeError('Security writer requires a clean session')
        db.rollback()  # End any earlier snapshot before waiting for the lock.
        with security_lock(db):
            db.expire_all()
            audited = function.__module__.rsplit('.', 1)[-1] in {'reference_users', 'permissions', 'assign_role'}
            audited = audited and not (function.__name__ == 'assign_role' and not arguments.get('apply', False))
            audit_id = None
            if audited:
                from . import security_audit
                from .main import current_user
                request = arguments.get('request')
                actor = current_user(request, db) if request is not None else None
                target = arguments.get('identity')
                selector = arguments.get('user_selector', '')
                if target is None and selector.startswith('id:') and selector[3:].isdigit():
                    target = int(selector[3:])
                elif target is None and selector:
                    target = db.scalar(select(User.id).where(User.email == selector))
                action = function.__module__.rsplit('.', 1)[-1] + '.' + function.__name__
                try:
                    audit_path = security_audit.destination(db)
                    before = security_audit.snapshot(db, action, target)
                    if request is None:
                        before['operator_uid'] = os.getuid() if hasattr(os, 'getuid') else 'local-host-operator'
                    payload = arguments.get('payload', {})
                    if action == 'reference_users.update' and isinstance(payload, dict):
                        before['credential_reset_requested'] = payload.get('user_change_password', payload.get('change_password', False)) in (True, 1, '1')
                        before['email_field_supplied'] = 'email' in payload or 'user_email' in payload
                    audit_id = security_audit.begin(audit_path, actor.id if actor else None, action, target, before)
                except (OSError, RuntimeError, sqlite3.Error):
                    raise HTTPException(503, 'Security audit unavailable; action not performed') from None
            try:
                result = function(*args, **kwargs)
            except BaseException as exc:
                db.rollback()
                if audit_id:
                    try:
                        security_audit.finish(audit_path, audit_id, 'denied' if isinstance(exc, (HTTPException, ValueError)) else 'error',
                                              security_audit.snapshot(db, action, target))
                    except Exception:
                        # Durable intent remains unresolved. Never obscure the original error.
                        import logging
                        logging.getLogger(__name__).error('security_audit_outcome_unresolved event=%s', audit_id)
                raise
            if audit_id:
                if target is None and isinstance(result, dict):
                    target = result.get('id', result.get('user_id'))
                try:
                    security_audit.bind_target(audit_path, audit_id, target)
                    security_audit.finish(audit_path, audit_id, 'success', security_audit.snapshot(db, action, target))
                except Exception:
                    # MyISAM may already be committed: no false rollback/success claim.
                    import logging
                    logging.getLogger(__name__).error('security_audit_outcome_unresolved event=%s', audit_id)
                    raise HTTPException(503, 'Action outcome requires operator reconciliation') from None
            return result
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