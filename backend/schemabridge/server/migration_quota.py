"""Atomic daily migration-start allowances for workspace principals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pymongo import ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from schemabridge.server.auth import WorkspacePrincipal
from schemabridge.server.config import get_settings
from schemabridge.server.mongo import get_client

_COLLECTION = "migration_quotas"
_TIMEZONE = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True, slots=True)
class MigrationUsage:
    used: int
    limit: int
    reset_at: datetime
    scope: str
    workspace_kind: str
    retention_hours: int


@dataclass(frozen=True, slots=True)
class _QuotaWindow:
    day: str
    reset_at: datetime


@dataclass(frozen=True, slots=True)
class Reservation:
    owner_id: str
    day: str
    run_id: str


class MigrationQuotaExhaustedError(RuntimeError):
    """The workspace has started all migrations allowed today."""


def _quotas() -> Collection[dict[str, Any]]:
    settings = get_settings()
    return get_client()[settings.mongodb_db][_COLLECTION]


def _window(now: datetime | None = None) -> _QuotaWindow:
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("A quota timestamp must be timezone-aware.")
    local = instant.astimezone(_TIMEZONE)
    reset_at = datetime.combine(local.date() + timedelta(days=1), time.min, tzinfo=_TIMEZONE)
    return _QuotaWindow(day=local.date().isoformat(), reset_at=reset_at)


def _quota_id(owner_id: str, day: str) -> str:
    return f"migration:{owner_id}:{day}"


def _usage(
    document: dict[str, Any] | None, principal: WorkspacePrincipal, window: _QuotaWindow
) -> MigrationUsage:
    return MigrationUsage(
        used=int(document.get("used", 0)) if document else 0,
        limit=principal.daily_run_limit,
        reset_at=window.reset_at,
        scope=principal.usage_scope,
        workspace_kind=principal.kind,
        retention_hours=principal.retention_hours,
    )


def reserve_migration_start(principal: WorkspacePrincipal, run_id: str) -> Reservation:
    """Atomically reserve one run start for this workspace's India-day limit."""
    window = _window()
    query = {
        "_id": _quota_id(principal.owner_id, window.day),
        "used": {"$lt": principal.daily_run_limit},
        "run_ids": {"$ne": run_id},
    }
    update = {
        "$inc": {"used": 1},
        "$addToSet": {"run_ids": run_id},
        "$setOnInsert": {
            "owner_id": principal.owner_id,
            "workspace_kind": principal.kind,
            "day": window.day,
            "limit": principal.daily_run_limit,
            "expires_at": window.reset_at.astimezone(UTC) + timedelta(days=1),
        },
    }
    try:
        document = _quotas().find_one_and_update(
            query, update, upsert=True, return_document=ReturnDocument.AFTER
        )
    except DuplicateKeyError:
        document = _quotas().find_one_and_update(
            query, update, upsert=False, return_document=ReturnDocument.AFTER
        )
    if document is None:
        raise MigrationQuotaExhaustedError(
            f"This workspace can start up to {principal.daily_run_limit} migrations per day. "
            "Try again after midnight IST."
        )
    return Reservation(principal.owner_id, window.day, run_id)


def release_migration_start(reservation: Reservation) -> None:
    """Release the exact reservation that failed before its run was persisted."""
    _quotas().update_one(
        {"_id": _quota_id(reservation.owner_id, reservation.day), "run_ids": reservation.run_id},
        {"$inc": {"used": -1}, "$pull": {"run_ids": reservation.run_id}},
    )


def usage_for_principal(principal: WorkspacePrincipal) -> MigrationUsage:
    window = _window()
    document = _quotas().find_one({"_id": _quota_id(principal.owner_id, window.day)})
    return _usage(document, principal, window)


def ensure_indexes() -> None:
    _quotas().create_index("expires_at", expireAfterSeconds=0)
