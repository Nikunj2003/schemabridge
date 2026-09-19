"""Shared inference budget.

The demo is public and unauthenticated, so the model key has to be protected by
the application rather than by a login. Two limits apply: a per-run cap, so one
migration cannot loop, and a rolling daily cap across all visitors, so one person
cannot exhaust the free-tier allowance for everyone.

Reservations are taken *before* the upstream call and counted atomically, because
a budget checked after the fact is not a budget.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.collection import Collection

from schemabridge.server.config import get_settings
from schemabridge.server.mongo import get_client

_COLLECTION = "budgets"


def _budgets() -> Collection[dict[str, Any]]:
    settings = get_settings()
    return get_client()[settings.mongodb_db][_COLLECTION]


def _today_key() -> str:
    return f"model:{datetime.now(UTC):%Y-%m-%d}"


class BudgetExhaustedError(RuntimeError):
    """The demo has spent its allowance. Not a failure of the migration."""


def reserve_model_request(count: int = 1) -> int:
    """Claim `count` upstream requests for today, or refuse.

    Uses a single atomic update so two concurrent requests cannot both pass a
    check that only one of them should. Returns the total used after the claim.
    """
    settings = get_settings()
    limit = settings.max_model_requests_per_day
    collection = _budgets()
    key = _today_key()

    document = collection.find_one_and_update(
        {"_id": key, "used": {"$lte": limit - count}},
        {
            "$inc": {"used": count},
            "$setOnInsert": {
                "limit": limit,
                # Expires on its own; a stale counter would wrongly block a
                # later day.
                "expires_at": datetime.now(UTC) + timedelta(days=2),
            },
        },
        upsert=True,
        return_document=True,
    )

    if document is None:
        raise BudgetExhaustedError(
            f"The shared daily limit of {limit} model requests is spent. "
            f"Deterministic mapping still works; try again tomorrow."
        )
    used: int = document.get("used", count)
    return used


def usage_today() -> tuple[int, int]:
    """Requests used today and the limit, for display."""
    settings = get_settings()
    document = _budgets().find_one({"_id": _today_key()})
    used = int(document.get("used", 0)) if document else 0
    return used, settings.max_model_requests_per_day


def ensure_indexes() -> None:
    """Expire budget counters so old days do not accumulate."""
    _budgets().create_index("expires_at", expireAfterSeconds=0)
