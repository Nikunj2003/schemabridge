"""MongoDB access.

One client per warm execution environment, held at module scope. Serverless
functions are reused between requests, so connecting per request would exhaust
the connection allowance on a free cluster. The pool is deliberately small for
the same reason: every concurrent function instance has its own.
"""

from __future__ import annotations

from typing import Any

from pymongo import MongoClient

from schemabridge.server.config import get_settings

_client: MongoClient[dict[str, Any]] | None = None


def get_client() -> MongoClient[dict[str, Any]]:
    """The shared client, created on first use."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = MongoClient(
            settings.require_mongodb_uri(),
            maxPoolSize=8,
            minPoolSize=0,
            maxIdleTimeMS=60_000,
            serverSelectionTimeoutMS=8_000,
            connectTimeoutMS=8_000,
            socketTimeoutMS=20_000,
            retryWrites=True,
            tz_aware=True,
        )
    return _client


def close_client() -> None:
    """Release the connection. Used by tests and local scripts."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
