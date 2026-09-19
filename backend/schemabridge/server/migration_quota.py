"""Per-session migration start allowance.

A migration start consumes one allowance only after its upload and target schema
have passed validation. The reservation lives independently from the run registry:
the registry documents expire with runs, while a day's allowance must continue to
apply even if a run is later cleaned up.

Each quota document represents one anonymous browser session and one
Asia/Kolkata calendar day. ``run_ids`` makes a reservation's logical key
``(session_id, day, run_id)`` and lets a registry-persist failure release exactly
the reservation it created. Keeping the counter and those ids in one document
makes the limit check and claim one atomic Mongo update.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pymongo import ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from schemabridge.server.config import get_settings
from schemabridge.server.mongo import get_client

_COLLECTION = "migration_quotas"
_TIMEZONE = ZoneInfo("Asia/Kolkata")
_SCOPE = "anonymous_browser_session"


@dataclass(frozen=True, slots=True)
class MigrationUsage:
    """The caller's allowance in the current India calendar-day window."""

    used: int
    limit: int
    reset_at: datetime
    scope: str = _SCOPE


@dataclass(frozen=True, slots=True)
class _QuotaWindow:
    day: str
    reset_at: datetime


class MigrationQuotaExhaustedError(RuntimeError):
    """The anonymous session has started all migrations allowed today."""


def _quotas() -> Collection[dict[str, Any]]:
    settings = get_settings()
    return get_client()[settings.mongodb_db][_COLLECTION]


def _window(now: datetime | None = None) -> _QuotaWindow:
    """The IST day key and its next midnight, independent of server timezone."""
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("A quota timestamp must be timezone-aware.")
    local = instant.astimezone(_TIMEZONE)
    next_day = local.date() + timedelta(days=1)
    reset_at = datetime.combine(next_day, time.min, tzinfo=_TIMEZONE)
    return _QuotaWindow(day=local.date().isoformat(), reset_at=reset_at)


def _quota_id(session_id: str, day: str) -> str:
    """Stable document id for a session's one IST-day allowance."""
    return f"migration:{session_id}:{day}"


def reserve_migration_start(session_id: str, run_id: str) -> MigrationUsage:
    """Atomically reserve one start for ``run_id``, or reject it at the limit.

    The conditional counter increment and the run id are written together. A run
    id is generated once per create request, so it is never reused for a new run.
    """
    settings = get_settings()
    limit = settings.max_migration_starts_per_session_per_day
    window = _window()
    query = {
        "_id": _quota_id(session_id, window.day),
        "used": {"$lt": limit},
        "run_ids": {"$ne": run_id},
    }
    update = {
        "$inc": {"used": 1},
        "$addToSet": {"run_ids": run_id},
        "$setOnInsert": {
            "session_id": session_id,
            "day": window.day,
            "limit": limit,
            # Retain the counter briefly past its window for diagnostics and
            # delayed retries, then let Mongo clean it up automatically.
            "expires_at": window.reset_at.astimezone(UTC) + timedelta(days=1),
        },
    }
    try:
        document = _quotas().find_one_and_update(
            query, update, upsert=True, return_document=ReturnDocument.AFTER
        )
    except DuplicateKeyError:
        # Two first starts can race to create the one daily row. Retry without an
        # upsert now that one row exists; the same conditional gate remains atomic.
        document = _quotas().find_one_and_update(
            query, update, upsert=False, return_document=ReturnDocument.AFTER
        )
    if document is None:
        raise MigrationQuotaExhaustedError(
            f"You can start up to {limit} migrations per day. Try again after midnight IST."
        )
    return MigrationUsage(used=int(document.get("used", 1)), limit=limit, reset_at=window.reset_at)


def release_migration_start(session_id: str, run_id: str) -> None:
    """Release precisely one failed-to-persist run reservation.

    This is intentionally not a general cancellation operation. Once the run
    registry has persisted, the migration has successfully started and continues
    to count even if the graph later fails or is abandoned.
    """
    window = _window()
    _quotas().update_one(
        {"_id": _quota_id(session_id, window.day), "run_ids": run_id},
        {"$inc": {"used": -1}, "$pull": {"run_ids": run_id}},
    )


def usage_for_session(session_id: str) -> MigrationUsage:
    """Return this browser session's current IST-day migration usage."""
    settings = get_settings()
    window = _window()
    document = _quotas().find_one({"_id": _quota_id(session_id, window.day)})
    return MigrationUsage(
        used=int(document.get("used", 0)) if document else 0,
        limit=settings.max_migration_starts_per_session_per_day,
        reset_at=window.reset_at,
    )


def ensure_indexes() -> None:
    """Expire completed IST-day quota documents after their diagnostic window."""
    _quotas().create_index("expires_at", expireAfterSeconds=0)
