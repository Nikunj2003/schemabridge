"""Visitor sessions.

The demo has no login, but "no login" is not the same as "no ownership". Each
visitor gets an unguessable session id in an HttpOnly cookie, and every run
operation checks it. A run id alone is never treated as authorisation: ids appear
in URLs, logs and screenshots, so anyone holding one could otherwise read or
change someone else's migration.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response

SESSION_COOKIE = "sb_session"
_SESSION_BYTES = 32
_SESSION_DAYS = 7


def new_session_id() -> str:
    """A fresh, unguessable session identifier."""
    return secrets.token_urlsafe(_SESSION_BYTES)


def read_session(request: Request) -> str | None:
    """The caller's session, if they have one."""
    value = request.cookies.get(SESSION_COOKIE)
    return value if value and len(value) >= 20 else None


def attach_session(response: Response, session_id: str, *, secure: bool) -> None:
    """Set the session cookie.

    HttpOnly so client script cannot read it, SameSite=Lax so it is not sent on
    cross-site requests, and Secure whenever the deployment is served over TLS.
    """
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=_SESSION_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


def ensure_session(request: Request, response: Response) -> str:
    """Return the caller's session, creating one if needed."""
    existing = read_session(request)
    if existing:
        return existing
    session_id = new_session_id()
    attach_session(response, session_id, secure=is_secure(request))
    return session_id


def is_secure(request: Request) -> bool:
    """Whether this request arrived over TLS, accounting for a proxy."""
    forwarded = request.headers.get("x-forwarded-proto", "")
    return request.url.scheme == "https" or forwarded.split(",")[0].strip() == "https"


def session_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=_SESSION_DAYS)
