"""Workspace identity resolution.

A missing bearer token deliberately selects the single shared anonymous workspace.
A bearer token, when supplied, is always validated: an invalid token must never
fall through to that shared workspace.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from jwt import InvalidTokenError, PyJWKClient
from jwt.exceptions import PyJWKClientError

from schemabridge.server.config import get_settings

logger = logging.getLogger(__name__)

_ANONYMOUS_WORKSPACE = "anonymous:shared"


@dataclass(frozen=True, slots=True)
class WorkspacePrincipal:
    """A server-derived workspace policy and opaque storage owner id."""

    owner_id: str
    kind: str
    daily_run_limit: int
    retention: timedelta

    @property
    def retention_hours(self) -> int:
        return int(self.retention.total_seconds() // 3600)

    @property
    def usage_scope(self) -> str:
        return "authenticated_user" if self.kind == "authenticated" else "shared_anonymous"

    def expires_at(self, now: datetime | None = None) -> datetime:
        return (now or datetime.now(UTC)) + self.retention


def anonymous_principal() -> WorkspacePrincipal:
    settings = get_settings()
    return WorkspacePrincipal(
        owner_id=_ANONYMOUS_WORKSPACE,
        kind="anonymous",
        daily_run_limit=settings.anonymous_migration_starts_per_day,
        retention=timedelta(hours=settings.anonymous_retention_hours),
    )


def _authenticated_principal(subject: str) -> WorkspacePrincipal:
    settings = get_settings()
    material = f"{settings.auth0_issuer_url}\x00{subject}".encode()
    # The subject never needs to appear in Mongo, URLs, telemetry, or logs.
    owner_id = f"user:{hashlib.sha256(material).hexdigest()[:32]}"
    return WorkspacePrincipal(
        owner_id=owner_id,
        kind="authenticated",
        daily_run_limit=settings.authenticated_migration_starts_per_day,
        retention=timedelta(hours=settings.authenticated_retention_hours),
    )


@lru_cache(maxsize=4)
def _jwk_client(jwks_url: str, cache_lifespan_seconds: int) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=cache_lifespan_seconds)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="The supplied access token is invalid or has expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def validate_access_token(token: str) -> WorkspacePrincipal:
    """Validate an Auth0 RS256 access token and derive its workspace.

    Kept as a small standalone function so tests can replace it without network
    access and API routes do not need to know how JWKS rotation works.
    """
    settings = get_settings()
    if not settings.auth0_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sign-in is not configured on this deployment.",
        )
    try:
        signing_key = _jwk_client(
            f"{settings.auth0_issuer_url}.well-known/jwks.json",
            settings.auth0_jwks_cache_seconds,
        ).get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.auth0_audience,
            issuer=settings.auth0_issuer_url,
            options={"require": ["exp", "iat", "sub"]},
        )
    except (InvalidTokenError, PyJWKClientError, ValueError, OSError) as error:
        # `PyJWKClientError` covers a key the tenant does not publish — an
        # unsigned or foreign-signed token. It does not derive from
        # `InvalidTokenError`, so without naming it a forged token would escape as
        # a 500 instead of a refusal.
        logger.info("access token validation failed: %s", type(error).__name__)
        raise _unauthorized() from None
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise _unauthorized()
    return _authenticated_principal(subject)


def principal_from_request(request: Request) -> WorkspacePrincipal:
    """Resolve a personal workspace or the intentionally shared guest workspace."""
    authorization = request.headers.get("authorization")
    if authorization is None:
        return anonymous_principal()
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized()
    return validate_access_token(token.strip())
