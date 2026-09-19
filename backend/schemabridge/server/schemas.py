"""Saved target schemas.

Unlike runs, these have **no TTL**. A run is a transient piece of work; the
contract a client's destination expects is the configuration that outlives it, and
expiring it would quietly break every future migration for that client.

Writes are version-guarded. This is the one place in the codebase that updates a
document in place, and two people editing one schema — or one person with two tabs
open — would otherwise silently lose whichever save landed first. Every update
matches on the version it read and bumps it, so a stale write fails loudly instead
of overwriting.

Ownership is by session, checked on every read and write. A schema id appears in
URLs, so it is not a credential.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pymongo.collection import Collection

from schemabridge.domain.schema import TargetSchema
from schemabridge.server.config import get_settings
from schemabridge.server.mongo import get_client

_COLLECTION = "target_schemas"

#: Saved schemas per visitor. Enough for several clients, bounded so the shared
#: cluster cannot be filled by one session.
MAX_PER_SESSION = 20


def _schemas() -> Collection[dict[str, Any]]:
    settings = get_settings()
    return get_client()[settings.mongodb_db][_COLLECTION]


class StaleWriteError(Exception):
    """Raised when a schema changed between being read and being saved."""


@dataclass(frozen=True, slots=True)
class SchemaRecord:
    """A saved schema, with who owns it and when it last changed."""

    schema_id: str
    owner_session_id: str
    schema: TargetSchema
    created_at: datetime
    updated_at: datetime


def new_schema_id() -> str:
    """An unguessable schema id. Not a secret, but not enumerable either."""
    return f"sch_{secrets.token_urlsafe(9)}"


def _record(document: dict[str, Any]) -> SchemaRecord:
    schema_id = str(document["_id"])
    stored = dict(document.get("schema", {}))
    # The id and version live on the document, so a copy of the schema cannot
    # disagree with the row that holds it.
    stored["schema_id"] = schema_id
    stored["version"] = int(document.get("version", 1))
    return SchemaRecord(
        schema_id=schema_id,
        owner_session_id=str(document["owner_session_id"]),
        schema=TargetSchema.model_validate(stored),
        created_at=document["created_at"],
        updated_at=document.get("updated_at", document["created_at"]),
    )


def create_schema(owner_session_id: str, schema: TargetSchema) -> SchemaRecord:
    """Save a new schema, assigning it an id of our own choosing.

    The caller's `schema_id` is ignored: accepting one would let a client claim
    `builtin:employee` or collide with someone else's row.
    """
    schema_id = new_schema_id()
    now = datetime.now(UTC)
    stored = schema.model_dump(mode="json")
    stored.pop("schema_id", None)
    stored.pop("version", None)
    # A saved schema is by definition not the shipped template.
    stored["builtin"] = False
    _schemas().insert_one(
        {
            "_id": schema_id,
            "owner_session_id": owner_session_id,
            "schema": stored,
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
    )
    return SchemaRecord(
        schema_id,
        owner_session_id,
        schema.model_copy(update={"schema_id": schema_id, "version": 1, "builtin": False}),
        now,
        now,
    )


def find_schema(schema_id: str, owner_session_id: str) -> SchemaRecord | None:
    """One schema the caller owns, or None.

    The same answer whether it is absent or someone else's: distinguishing them
    would confirm that a guessed id exists.
    """
    document = _schemas().find_one({"_id": schema_id, "owner_session_id": owner_session_id})
    return None if document is None else _record(document)


def list_schemas(owner_session_id: str, limit: int = MAX_PER_SESSION) -> list[SchemaRecord]:
    """A visitor's saved schemas, most recently changed first."""
    cursor = (
        _schemas().find({"owner_session_id": owner_session_id}).sort("updated_at", -1).limit(limit)
    )
    return [_record(document) for document in cursor]


def count_for_session(owner_session_id: str) -> int:
    return _schemas().count_documents({"owner_session_id": owner_session_id})


def update_schema(
    schema_id: str,
    owner_session_id: str,
    schema: TargetSchema,
    *,
    if_version: int,
) -> SchemaRecord:
    """Replace a saved schema's definition, guarded on the version read.

    Raises `StaleWriteError` when the stored version has moved on, which means
    somebody else saved first and this write would discard their work.
    """
    now = datetime.now(UTC)
    stored = schema.model_dump(mode="json")
    stored.pop("schema_id", None)
    stored.pop("version", None)
    stored["builtin"] = False

    result = _schemas().update_one(
        # The version is part of the filter, not checked beforehand: a read then a
        # write would leave a window where two savers both see the same version.
        {"_id": schema_id, "owner_session_id": owner_session_id, "version": if_version},
        {"$set": {"schema": stored, "updated_at": now}, "$inc": {"version": 1}},
    )
    if result.matched_count == 0:
        existing = _schemas().find_one({"_id": schema_id, "owner_session_id": owner_session_id})
        if existing is None:
            raise KeyError(schema_id)
        raise StaleWriteError(
            "This schema was changed somewhere else after you opened it. "
            "Reload it to see the current version before saving again."
        )

    updated = find_schema(schema_id, owner_session_id)
    if updated is None:  # pragma: no cover - deleted between write and read
        raise KeyError(schema_id)
    return updated


def delete_schema(schema_id: str, owner_session_id: str) -> bool:
    """Forget a saved schema.

    Runs that used it are unaffected: each one snapshotted the schema into its
    own state, so deleting the definition cannot change a migration's history.
    """
    result = _schemas().delete_one({"_id": schema_id, "owner_session_id": owner_session_id})
    return result.deleted_count > 0


def ensure_indexes() -> None:
    _schemas().create_index([("owner_session_id", 1), ("updated_at", -1)])
