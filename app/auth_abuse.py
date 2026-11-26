"""Atomic host-shared auth budgets. No raw account/IP identifiers are stored."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import time

from fastapi import HTTPException
from starlette.responses import JSONResponse
from .config import PRODUCTION, LOGIN_LIMIT_DB

POLICIES = {'login': (20, 100, 1000), 'register': (3, 10, 100),
            'reset-email': (3, 10, 100), 'reset': (10, 50, 500)}
WINDOW = 900
AUTH_PATHS = {prefix + suffix for prefix in ('', '/api') for suffix in
              ('/auth/login', '/auth/register', '/password/email', '/password/reset')}
MAX_BODY = 16384


class AuthBodyLimitMiddleware:
    """Bound actual streamed bytes before form parsing, including chunked bodies."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST' or scope['path'].rstrip('/') not in AUTH_PATHS:
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            if len(body) + len(chunk) > MAX_BODY:
                response = JSONResponse({'error': 'auth_request_too_large'}, status_code=413)
                return await response(scope, receive, send)
            body.extend(chunk)
            if not message.get('more_body', False):
                break
        async def replay():
            nonlocal body
            if body is not None:
                data, body = bytes(body), None
                return {'type': 'http.request', 'body': data, 'more_body': False}
            return await receive()
        return await self.app(scope, replay, send)


def reserve(path, action, account, address, *, now=None):
    stamp = time.time() if now is None else now
    keys = [hashlib.sha256(f'{action}:{scope}:{value}'.encode()).hexdigest()
            for scope, value in (('account', account.strip().casefold()),
                                 ('ip', address), ('global', '*'))]
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(destination, timeout=10)) as db, db:
        destination.chmod(0o600)
        db.execute('CREATE TABLE IF NOT EXISTS auth_budgets (identity TEXT PRIMARY KEY, expires REAL NOT NULL, count INTEGER NOT NULL)')
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM auth_budgets WHERE expires <= ?', (stamp,))
        for key, limit in zip(keys, POLICIES[action]):
            row = db.execute('SELECT count FROM auth_budgets WHERE identity=?', (key,)).fetchone()
            if row and row[0] >= limit:
                return False
        for key in keys:
            db.execute('INSERT INTO auth_budgets VALUES (?, ?, 1) ON CONFLICT(identity) DO UPDATE SET count=count+1',
                       (key, stamp + WINDOW))
        return True


def guard(request, action, email):
    if not PRODUCTION and os.getenv('AUTH_ABUSE_ENABLED', 'false').lower() != 'true':
        return
    try:
        allowed = reserve(LOGIN_LIMIT_DB, action, email,
                          request.client.host if request.client else 'unknown')
    except (OSError, sqlite3.Error):
        raise HTTPException(503, 'Authentication temporarily unavailable') from None
    if not allowed:
        raise HTTPException(429, 'Too many requests; retry later', headers={'Retry-After': str(WINDOW)})