"""
Minimal CSRF protection for session-cookie + form-based routes.

A token is stored in the signed session and echoed into every form as a
hidden field; POST handlers reject the request unless the two match. This
is intentionally simple (no extra dependency) — SessionMiddleware already
signs the cookie, so an attacker can't forge the session-side token, only
fail to know it.
"""

import secrets

from fastapi import Request


def get_or_create_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def verify_csrf_token(request: Request, submitted_token: str) -> bool:
    expected = request.session.get("csrf_token")
    return bool(expected) and secrets.compare_digest(expected, submitted_token or "")
