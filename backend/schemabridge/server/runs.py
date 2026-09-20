"""The small run manifest that authorizes and locates a checkpointed migration."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pymongo.collection import Collection

from schemabridge.server.auth import WorkspacePrincipal
from schemabridge.server.config import get_settings
from schemabridge.server.mongo import get_client

_COLLECTION = "runs"


def _runs() -> Collection[dict[str, Any]]:
    settings = get_settings()
    return get_client()[settings.mongodb_db][_COLLECTION]


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    owner_id: str
    workspace_kind: str
    created_at: datetime
    expires_at: datetime
    file_names: tuple[str, ...]
    source_rows: int


def new_run_id() -> str:
    return f"run_{secrets.token_urlsafe(12)}"


def _record(document: dict[str, Any]) -> RunRecord:
    return RunRecord(
        run_id=str(document["_id"]),
        # Old, already-expiring rows retain their inaccessible cookie owner.
        owner_id=str(document.get("owner_id", document.get("owner_session_id", "legacy"))),
        workspace_kind=str(document.get("workspace_kind", "legacy")),
        created_at=document["created_at"],
        expires_at=document["expires_at"],
        file_names=tuple(document.get("file_names", [])),
        source_rows=int(document.get("source_rows", 0)),
    )


def create_run(
    run_id: str, principal: WorkspacePrincipal, file_names: tuple[str, ...], source_rows: int
) -> RunRecord:
    now = datetime.now(UTC)
    expires_at = principal.expires_at(now)
    _runs().insert_one(
        {
            "_id": run_id,
            "owner_id": principal.owner_id,
            "workspace_kind": principal.kind,
            "created_at": now,
            "expires_at": expires_at,
            "file_names": list(file_names),
            "source_rows": source_rows,
        }
    )
    return RunRecord(
        run_id, principal.owner_id, principal.kind, now, expires_at, file_names, source_rows
    )


def find_run(run_id: str) -> RunRecord | None:
    now = datetime.now(UTC)
    document = _runs().find_one({"_id": run_id, "expires_at": {"$gt": now}})
    return None if document is None else _record(document)


def list_runs(owner_id: str, limit: int = 20) -> list[RunRecord]:
    now = datetime.now(UTC)
    cursor = (
        _runs()
        .find({"owner_id": owner_id, "expires_at": {"$gt": now}})
        .sort("created_at", -1)
        .limit(limit)
    )
    return [_record(document) for document in cursor]


def ensure_indexes() -> None:
    _runs().create_index([("owner_id", 1), ("created_at", -1)])
    _runs().create_index("expires_at", expireAfterSeconds=0)
