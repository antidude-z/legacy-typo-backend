"""Private durable security intents/outcomes; intentionally independent of MyISAM."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from sqlalchemy import select
from .models import User, role_permissions

SAFE_FIELDS = ('id', 'role_id', 'fired', 'deleted')


def destination(db):
    configured = os.getenv('SECURITY_AUDIT_DB')
    if configured:
        return Path(configured)
    engine = db.get_bind()
    if (engine.dialect.name == 'sqlite' and engine.url.database in (None, '', ':memory:')) or os.getenv('MYSQL_ADMIN_TEST_URL') or os.getenv('MYSQL_TEST_URL'):
        # In-memory fixtures own their audit store too. Never touch working data.
        if not hasattr(engine, '_security_audit_directory'):
            import tempfile
            import shutil
            import weakref
            engine._security_audit_directory = tempfile.mkdtemp(prefix='security-audit-test-')
            weakref.finalize(engine, shutil.rmtree, engine._security_audit_directory, True)
        return Path(engine._security_audit_directory) / 'audit.db'
    if engine.dialect.name == 'sqlite':
        return Path(engine.url.database).resolve().parent / 'security-audit.db'
    if os.getenv('S12_MYSQL_ENABLED') == '1':
        # MySQL QA supplies an explicit owned path; fail rather than use live data.
        raise RuntimeError('MySQL audit QA requires SECURITY_AUDIT_DB')
    return Path('/app/data/security-audit.db')


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    try:
        path.chmod(0o600)
        db.execute('PRAGMA synchronous=FULL')
        db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, started REAL NOT NULL, actor INTEGER, action TEXT NOT NULL, target INTEGER, before_state TEXT NOT NULL, after_state TEXT, outcome TEXT NOT NULL, finished REAL)')
        db.commit()
        return db
    except BaseException:
        db.close()
        raise


def initialize(path):
    """Create the protected journal before the first administrative event."""
    with closing(connect(path)):
        pass


def snapshot(db, action, target):
    if action == 'permissions.update_matrix':
        return {'grants': sorted([list(row) for row in db.execute(select(role_permissions.c.role_id, role_permissions.c.permission_id))])}
    if target is None:
        return {}
    row = db.get(User, target)
    if row is None:
        return {'exists': False}
    return {'id': row.id, 'role_id': row.role_id, 'fired': bool(row.fired), 'deleted': row.deleted_at is not None}


def record_admission_denial(db, request, actor):
    import re
    path = request.url.path
    match = re.fullmatch(r'/api/employee-references(?:/(\d+)(?:/restore)?)?', path)
    if request.method not in {'POST', 'PATCH', 'DELETE'} or (not match and path != '/api/options/permissions'):
        return
    action = 'reference_users.admission_denied' if match else 'permissions.admission_denied'
    target = int(match[1]) if match and match[1] else None
    try:
        store = destination(db)
        identity = begin(store, actor.id if actor else None, action, target, {})
        finish(store, identity, 'denied', {})
    except (OSError, sqlite3.Error):
        from fastapi import HTTPException
        raise HTTPException(503, 'Security audit unavailable') from None


def begin(path, actor, action, target, before):
    identity = uuid4().hex
    with closing(connect(path)) as db, db:
        db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,NULL,?,NULL)',
                   (identity, time.time(), actor, action, target, json.dumps(before, sort_keys=True), 'intent'))
    return identity


def bind_target(path, identity, target):
    with closing(connect(path)) as db, db:
        db.execute('UPDATE events SET target=? WHERE id=?', (target, identity))


def finish(path, identity, outcome, after):
    with closing(connect(path)) as db, db:
        db.execute('UPDATE events SET outcome=?,after_state=?,finished=? WHERE id=? AND outcome=?',
                   (outcome, json.dumps(after, sort_keys=True), time.time(), identity, 'intent'))
    if outcome in ('denied', 'error'):
        import logging
        logging.getLogger(__name__).warning('security_action_%s event=%s', outcome, identity)
    with closing(connect(path)) as db:
        count = db.execute("SELECT COUNT(*) FROM events WHERE action='reference_users.delete' AND started>=?", (time.time()-300,)).fetchone()[0]
    if count >= 5:
        import logging
        logging.getLogger(__name__).warning('security_bulk_delete_alert event=%s count=%s window_seconds=300', identity, count)


def view(path, limit=100, alerts=False):
    # Read-only host-operator tool: no API, no automatic deletion/rotation.
    uri = Path(path).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute('SELECT * FROM events ORDER BY started DESC LIMIT ?', (limit,))]
    if alerts:
        now = time.time()
        return {'unresolved': [row for row in rows if row['outcome'] == 'intent'],
                'denied_or_error': [row for row in rows if row['outcome'] in ('denied', 'error')],
                'bulk_delete_alert': sum(row['action'] == 'reference_users.delete' and row['started'] >= now-300 for row in rows) >= 5,
                'bounded_to_latest': limit}
    return rows


def main():
    parser = argparse.ArgumentParser(description='Host-operator-only security audit viewer; no secrets or automatic retention deletion')
    parser.add_argument('--path', default=os.getenv('SECURITY_AUDIT_DB', '/app/data/security-audit.db'))
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--alerts', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.limit <= 10000:
        parser.error('limit must be between 1 and 10000')
    print(json.dumps(view(args.path, args.limit, args.alerts), ensure_ascii=False))


if __name__ == '__main__':
    main()