"""Shared inference budget.

The demo is public and unauthenticated, so the model key has to be protected by
the application rather than by a login. Two limits apply, and they guard against
different failures:

* **Per run.** A run now has several places it may consult the model, and one of
  them sits on a path the graph re-enters once per reviewer decision. The per-run
  cap is what stops a migration with many questions from spending the allowance
  one correction at a time. It is checked against the run's own committed counter,
  so it survives the run being paused and resumed in a different process.
* **Per day, across everyone.** So one visitor cannot exhaust the free-tier
  allowance for the next.

Reservations are taken *before* the upstream call and counted atomically, because
a budget checked after the fact is not a budget.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

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


def run_requests_remaining(used_in_run: int) -> int:
    """Model requests this run may still make.

    Separate from the daily counter and deliberately not stored: the authoritative
    number is the run's own `model_requests`, which the checkpointer already
    persists. A second copy in the database could disagree with the trail the
    reviewer is shown.
    """
    limit = get_settings().max_model_requests_per_run
    return max(0, limit - max(0, used_in_run))


def check_run_budget(used_in_run: int) -> None:
    """Refuse a further request once this run has spent its own allowance."""
    if run_requests_remaining(used_in_run) > 0:
        return
    limit = get_settings().max_model_requests_per_run
    raise BudgetExhaustedError(
        f"This migration has used its {limit} model requests. "
        f"Deterministic rules still apply, and anything left over is asked of you."
    )


def reserve_model_request(count: int = 1) -> int:
    """Claim `count` upstream requests for today, or refuse.

    Uses a single atomic update so two concurrent requests cannot both pass a
    check that only one of them should. Returns the total used after the claim.
    """
    settings = get_settings()
    limit = settings.max_model_requests_per_day
    collection = _budgets()
    key = _today_key()

    query = {"_id": key, "used": {"$lte": limit - count}}
    update = {
        "$inc": {"used": count},
        "$setOnInsert": {
            "limit": limit,
            # Expires on its own; a stale counter would wrongly block a later day.
            "expires_at": datetime.now(UTC) + timedelta(days=2),
        },
    }
    try:
        document = collection.find_one_and_update(query, update, upsert=True, return_document=True)
    except DuplicateKeyError:
        # The day's row exists and is already at the limit, so the conditional
        # filter matched nothing and the upsert collided with it. Retrying without
        # the upsert returns None, which is the refusal this function reports —
        # otherwise a spent budget would surface as a database error and the
        # caller would blame an outage for a limit working correctly.
        document = collection.find_one_and_update(query, update, upsert=False, return_document=True)

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
