from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


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
    """Double-submit protection for browser/API traffic.

    Existing non-browser compatibility clients may not have a CSRF cookie. Once
    the browser obtains the token, however, a state-changing request must send
    the matching header. This preserves the legacy API test/client contract
    while protecting the Svelte application's cookie-authenticated requests.
    """

    async def dispatch(self, request, call_next):
        if request.method not in SAFE_METHODS and request.cookies.get(CSRF_COOKIE):
            cookie_token = request.cookies.get(CSRF_COOKIE)
            header_token = request.headers.get(CSRF_HEADER)
            if not header_token or not secrets.compare_digest(cookie_token, header_token):
                return JSONResponse({"error": "csrf_failed", "message": "Недействительный CSRF-токен."}, status_code=419)
        response = await call_next(request)
        return response