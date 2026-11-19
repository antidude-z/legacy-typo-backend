from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from .config import PRODUCTION



CSRF_COOKIE = "typography_csrf"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def token_for_session(request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


class CSRFMiddleware(BaseHTTPMiddleware):
    """Require double-submit CSRF protection for opted-in browser sessions.

    A browser opts in by requesting ``/api/csrf-token``; stateless compatibility
    callers that never establish that token remain outside this contract.
    """

    async def dispatch(self, request, call_next):
        if request.method not in SAFE_METHODS and (PRODUCTION or request.cookies.get(CSRF_COOKIE)):
            cookie_token = request.cookies.get(CSRF_COOKIE)
            header_token = request.headers.get(CSRF_HEADER)
            session_token = request.session.get('csrf_token')
            if (not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token)
                    or (PRODUCTION and (not session_token or not secrets.compare_digest(session_token, header_token)))):
                return JSONResponse({"error": "csrf_failed", "message": "Недействительный CSRF-токен."}, status_code=419)
        response = await call_next(request)
        return response