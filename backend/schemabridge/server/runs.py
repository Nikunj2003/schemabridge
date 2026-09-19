"""The run registry.

LangGraph's checkpointer owns the workflow state, so this collection holds only
what the checkpointer does not model: who owns a run, when it was created, and a
small summary for listing. Duplicating graph state here would create two sources
of truth that could disagree.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.collection import Collection

from schemabridge.server.config import get_settings
from schemabridge.server.mongo import get_client

_COLLECTION = "runs"


def _runs() -> Collection[dict[str, Any]]:
    settings = get_settings()
    return get_client()[settings.mongodb_db][_COLLECTION]


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Ownership and provenance for one migration run."""

    run_id: str
    owner_session_id: str
    created_at: datetime
    file_names: tuple[str, ...]
    source_rows: int


def new_run_id() -> str:
    """An unguessable run id. Not a secret, but not enumerable either."""
    return f"run_{secrets.token_urlsafe(12)}"


def create_run(
    run_id: str, owner_session_id: str, file_names: tuple[str, ...], source_rows: int
) -> RunRecord:
    settings = get_settings()
    now = datetime.now(UTC)
    _runs().insert_one(
        {
            "_id": run_id,
            "owner_session_id": owner_session_id,
            "created_at": now,
            "file_names": list(file_names),
            "source_rows": source_rows,
            "expires_at": now + timedelta(hours=settings.run_ttl_hours),
        }
    )
    return RunRecord(run_id, owner_session_id, now, file_names, source_rows)


def find_run(run_id: str) -> RunRecord | None:
    document = _runs().find_one({"_id": run_id})
    if document is None:
        return None
    return RunRecord(
        run_id=run_id,
        owner_session_id=str(document["owner_session_id"]),
        created_at=document["created_at"],
        file_names=tuple(document.get("file_names", [])),
        source_rows=int(document.get("source_rows", 0)),
    )


def list_runs(owner_session_id: str, limit: int = 20) -> list[RunRecord]:
    """A visitor's own runs, newest first."""
    cursor = (
        _runs().find({"owner_session_id": owner_session_id}).sort("created_at", -1).limit(limit)
    )
    return [
        RunRecord(
            run_id=str(document["_id"]),
            owner_session_id=owner_session_id,
            created_at=document["created_at"],
            file_names=tuple(document.get("file_names", [])),
            source_rows=int(document.get("source_rows", 0)),
        )
        for document in cursor
    ]


def count_runs_for_session(owner_session_id: str, within_hours: int = 24) -> int:
    """How many runs this visitor started recently, for rate limiting."""
    since = datetime.now(UTC) - timedelta(hours=within_hours)
    return _runs().count_documents(
        {"owner_session_id": owner_session_id, "created_at": {"$gte": since}}
    )


def ensure_indexes() -> None:
    _runs().create_index([("owner_session_id", 1), ("created_at", -1)])
    _runs().create_index("expires_at", expireAfterSeconds=0)
