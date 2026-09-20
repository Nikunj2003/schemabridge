"""A Mongo-coordinated rate gate for the shared NVIDIA API key."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from schemabridge.server.config import get_settings
from schemabridge.server.mongo import get_client

_COLLECTION = "model_rate_limits"
_KEY = "nvidia:global"


class ModelRateLimitTimeoutError(RuntimeError):
    """Waiting for a provider slot would exceed this request's bounded budget."""


@dataclass(frozen=True, slots=True)
class RateReservation:
    available_at: datetime
    waited_seconds: float


def _limits() -> Collection[dict[str, Any]]:
    settings = get_settings()
    return get_client()[settings.mongodb_db][_COLLECTION]


def _reserve_now(now: datetime) -> datetime | None:
    """Claim the next globally available slot, or return None when it is busy."""
    settings = get_settings()
    interval = timedelta(seconds=60 / settings.nvidia_requests_per_minute)
    query = {"_id": _KEY, "next_available_at": {"$lte": now}}
    update = {
        "$set": {"next_available_at": now + interval, "updated_at": now},
        "$setOnInsert": {"expires_at": now + timedelta(days=2)},
    }
    try:
        document = _limits().find_one_and_update(
            query, update, upsert=True, return_document=ReturnDocument.AFTER
        )
    except DuplicateKeyError:
        document = _limits().find_one_and_update(
            query, update, upsert=False, return_document=ReturnDocument.AFTER
        )
    return now if document is not None else None


def reserve_slot(*, max_wait_seconds: float | None = None) -> RateReservation:
    """Wait until this process owns one globally spaced provider start slot."""
    settings = get_settings()
    maximum = (
        max_wait_seconds if max_wait_seconds is not None else settings.nvidia_max_queue_seconds
    )
    started = time.monotonic()
    while True:
        now = datetime.now(UTC)
        claimed = _reserve_now(now)
        if claimed is not None:
            return RateReservation(available_at=claimed, waited_seconds=time.monotonic() - started)
        document = _limits().find_one({"_id": _KEY}, {"next_available_at": 1})
        next_at = document.get("next_available_at") if document else now
        delay = (
            max(0.01, (next_at - now).total_seconds()) if isinstance(next_at, datetime) else 0.05
        )
        elapsed = time.monotonic() - started
        if elapsed + delay > maximum:
            raise ModelRateLimitTimeoutError("The model is busy. Try the migration again shortly.")
        # A little jitter avoids every waiting worker racing the same slot.
        jitter = (secrets.randbelow(51) / 1000) * min(1.0, delay / 0.05)
        time.sleep(delay + jitter)


def ensure_indexes() -> None:
    _limits().create_index("expires_at", expireAfterSeconds=0)
