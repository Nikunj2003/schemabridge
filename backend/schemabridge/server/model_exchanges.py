"""Durable, access-controlled evidence for every upstream model attempt."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from pymongo.collection import Collection

from schemabridge.server.config import get_settings
from schemabridge.server.mongo import get_client

_COLLECTION = "model_exchanges"


def _exchanges() -> Collection[dict[str, Any]]:
    settings = get_settings()
    return get_client()[settings.mongodb_db][_COLLECTION]


def new_exchange_id() -> str:
    return f"llm_{secrets.token_urlsafe(9)}"


def start(
    *,
    exchange_id: str,
    run_id: str,
    owner_id: str,
    workspace_kind: str,
    expires_at: datetime,
    operation: str,
    model: str,
    request: Any,
) -> None:
    _exchanges().insert_one(
        {
            "_id": exchange_id,
            "run_id": run_id,
            "owner_id": owner_id,
            "workspace_kind": workspace_kind,
            "operation": operation,
            "model": model,
            "request": request,
            "status": "pending",
            "attempts": 0,
            "created_at": datetime.now(UTC),
            "expires_at": expires_at,
        }
    )


def finish(exchange_id: str, *, response: Any, attempts: int, latency_ms: int) -> None:
    _exchanges().update_one(
        {"_id": exchange_id},
        {
            "$set": {
                "status": "completed",
                "response": response,
                "attempts": attempts,
                "latency_ms": latency_ms,
                "completed_at": datetime.now(UTC),
            }
        },
    )


def fail(exchange_id: str, *, error: str, attempts: int, latency_ms: int) -> None:
    _exchanges().update_one(
        {"_id": exchange_id},
        {
            "$set": {
                "status": "failed",
                "error": error,
                "attempts": attempts,
                "latency_ms": latency_ms,
                "completed_at": datetime.now(UTC),
            }
        },
    )


def list_for_run(run_id: str) -> list[dict[str, Any]]:
    return list(_exchanges().find({"run_id": run_id}, {"owner_id": 0}).sort("created_at", 1))


def list_recent(*, limit: int = 100) -> list[dict[str, Any]]:
    return list(
        _exchanges().find({}, {"request": 0, "response": 0}).sort("created_at", -1).limit(limit)
    )


def ensure_indexes() -> None:
    _exchanges().create_index([("run_id", 1), ("created_at", 1)])
    _exchanges().create_index([("owner_id", 1), ("created_at", -1)])
    _exchanges().create_index("expires_at", expireAfterSeconds=0)
