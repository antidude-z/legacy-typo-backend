"""Atomic host-shared login attempt buckets; share the data volume across workers."""
import hashlib
from pathlib import Path
import sqlite3
import time
from contextlib import closing


def reserve_attempt(path, key, limit, window, now=None):
    stamp = time.time() if now is None else now
    identity = hashlib.sha256(key.encode()).hexdigest()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(destination, timeout=10)) as db, db:
        destination.chmod(0o600)
        db.execute('CREATE TABLE IF NOT EXISTS attempts (identity TEXT PRIMARY KEY, started REAL NOT NULL, count INTEGER NOT NULL)')
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM attempts WHERE started <= ?', (stamp - window,))
        row = db.execute('SELECT count FROM attempts WHERE identity=?', (identity,)).fetchone()
        if row and row[0] >= limit:
            return False
        db.execute('INSERT INTO attempts VALUES (?, ?, 1) ON CONFLICT(identity) DO UPDATE SET count=count+1', (identity, stamp))
        return True


def clear_attempts(path, key):
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('DELETE FROM attempts WHERE identity=?', (hashlib.sha256(key.encode()).hexdigest(),))