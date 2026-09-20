"""What the destination durably recorded, keyed by idempotency key.

This is the destination's own state, not the migration's, so it lives in its own
collection. Keeping it separate is what makes the idempotency claim meaningful:
the engine can lose its response, crash, and retry, and the destination still
knows whether it already accepted that exact payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from schemabridge.server.config import get_settings
from schemabridge.server.mongo import get_client

_COLLECTION = "destination_receipts"


def _receipts() -> Collection[dict[str, Any]]:
    settings = get_settings()
    return get_client()[settings.mongodb_db][_COLLECTION]


@dataclass(frozen=True, slots=True)
class Receipt:
    """Proof the destination accepted a specific payload."""

    idempotency_key: str
    target_id: str
    payload_hash: str
    created_at: datetime
    #: True when this call created the record; False when it replayed an earlier one.
    created: bool


class PayloadConflictError(RuntimeError):
    """The same key arrived with a different payload.

    Accepting this would mean the destination silently held different data under
    one identity, so it is refused rather than reconciled.
    """


def store_receipt(
    idempotency_key: str,
    target_id: str,
    payload_hash: str,
    employee: dict[str, Any],
    *,
    expires_at: datetime | None = None,
) -> Receipt:
    """Record acceptance exactly once for a given key.

    The unique `_id` plus an insert-only write is what enforces it: a concurrent
    duplicate loses the race and reads back the winner's receipt instead of
    creating a second record.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    collection = _receipts()

    try:
        collection.insert_one(
            {
                "_id": idempotency_key,
                "target_id": target_id,
                "payload_hash": payload_hash,
                "employee": employee,
                "created_at": now,
                "expires_at": expires_at or now + timedelta(hours=settings.run_ttl_hours),
            }
        )
    except DuplicateKeyError:
        existing = collection.find_one({"_id": idempotency_key})
        if existing is None:  # pragma: no cover - only under a concurrent expiry
            raise
        if existing["payload_hash"] != payload_hash:
            raise PayloadConflictError(
                f"Key {idempotency_key} was already used for a different payload."
            ) from None
        # A replay of an identical request. Return what was stored the first time.
        return Receipt(
            idempotency_key=idempotency_key,
            target_id=str(existing["target_id"]),
            payload_hash=str(existing["payload_hash"]),
            created_at=existing["created_at"],
            created=False,
        )

    return Receipt(
        idempotency_key=idempotency_key,
        target_id=target_id,
        payload_hash=payload_hash,
        created_at=now,
        created=True,
    )


def find_receipt(idempotency_key: str) -> Receipt | None:
    """Look up a receipt, for reconciling after an unknown outcome."""
    document = _receipts().find_one({"_id": idempotency_key})
    if document is None:
        return None
    return Receipt(
        idempotency_key=idempotency_key,
        target_id=str(document["target_id"]),
        payload_hash=str(document["payload_hash"]),
        created_at=document["created_at"],
        created=False,
    )


def count_receipts() -> int:
    """How many records the destination holds, for the demo's summary."""
    return _receipts().count_documents({})


def ensure_indexes() -> None:
    """Expire demo receipts so the free-tier cluster does not fill up."""
    _receipts().create_index("expires_at", expireAfterSeconds=0)
