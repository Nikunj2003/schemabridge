"""Stored rules, and the layered view a run actually consults.

Like saved schemas and unlike runs, these have **no TTL**. A rule is the durable
form of a decision someone already made; expiring it would mean the same question
came back a week later, which is precisely the behaviour the feature exists to
remove.

Three properties carried over from `server.schemas`, for the same reasons:

* **Ownership is by workspace, checked on every read and write.** A rule id
  appears in URLs, so it is not a credential, and an absent rule and one from
  another workspace are reported identically so a guessed id is never confirmed.
* **Writes are version-guarded**, with the version inside the update filter rather
  than checked beforehand. Two tabs editing one rule would otherwise silently lose
  whichever save landed first.
* **Ids are assigned here.** A caller-supplied id would let a request claim a
  `builtin:` id and so disable a shipped rule for everyone who imports it.

One thing this module adds: hit counts are written back **after** a run, in a
single bulk update, never during mapping. Counting a hit is bookkeeping, not a
decision that needs durable ordering, and a write inside the mapping loop would
put a database round trip between a column and its answer.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pymongo import UpdateOne
from pymongo.collection import Collection

from schemabridge.domain.rules import (
    MAX_RULES_PER_SESSION,
    Rule,
    RuleKind,
    RuleOrigin,
    RuleSet,
    builtin_rules,
    layered,
)
from schemabridge.domain.schema import TargetSchema
from schemabridge.server.config import get_settings
from schemabridge.server.mongo import get_client

logger = logging.getLogger(__name__)

_COLLECTION = "migration_rules"


def _rules() -> Collection[dict[str, Any]]:
    settings = get_settings()
    return get_client()[settings.mongodb_db][_COLLECTION]


class StaleWriteError(Exception):
    """Raised when a rule changed between being read and being saved."""


class RuleLimitError(Exception):
    """The session already holds as many rules as it may."""


@dataclass(frozen=True, slots=True)
class RuleRecord:
    """A stored rule, with who owns it and when it last changed."""

    rule_id: str
    owner_id: str
    rule: Rule
    version: int
    created_at: datetime
    updated_at: datetime


def new_rule_id() -> str:
    """An unguessable rule id, and never one a shipped rule could hold."""
    return f"rule_{secrets.token_urlsafe(9)}"


def _record(document: dict[str, Any]) -> RuleRecord:
    rule_id = str(document["_id"])
    stored = dict(document.get("rule", {}))
    # The id, hit count and version live on the document, so a copy of the rule
    # cannot disagree with the row that holds it.
    stored["rule_id"] = rule_id
    stored["hits"] = int(document.get("hits", 0))
    return RuleRecord(
        rule_id=rule_id,
        owner_id=str(document["owner_id"]),
        rule=Rule.model_validate(stored),
        version=int(document.get("version", 1)),
        created_at=document["created_at"],
        updated_at=document.get("updated_at", document["created_at"]),
    )


def _stored(rule: Rule) -> dict[str, Any]:
    payload = rule.model_dump(mode="json")
    for owned in ("rule_id", "hits"):
        payload.pop(owned, None)
    return payload


def create_rule(owner_id: str, rule: Rule) -> RuleRecord:
    """Store a new rule, assigning it an id of our own choosing."""
    if count_for_session(owner_id) >= MAX_RULES_PER_SESSION:
        raise RuleLimitError(
            f"You can keep up to {MAX_RULES_PER_SESSION} rules. "
            f"Delete one you no longer need to add another."
        )
    rule_id = new_rule_id()
    now = datetime.now(UTC)
    _rules().insert_one(
        {
            "_id": rule_id,
            "owner_id": owner_id,
            "rule": _stored(rule),
            "hits": 0,
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
    )
    return RuleRecord(
        rule_id,
        owner_id,
        rule.model_copy(update={"rule_id": rule_id, "hits": 0}),
        1,
        now,
        now,
    )


def find_rule(rule_id: str, owner_id: str) -> RuleRecord | None:
    """One rule the caller owns, or None for both absent and not-theirs."""
    document = _rules().find_one({"_id": rule_id, "owner_id": owner_id})
    return None if document is None else _record(document)


def list_rules(owner_id: str, limit: int = MAX_RULES_PER_SESSION) -> list[RuleRecord]:
    """A visitor's rules, most recently changed first."""
    cursor = _rules().find({"owner_id": owner_id}).sort("updated_at", -1).limit(limit)
    return [_record(document) for document in cursor]


def count_for_session(owner_id: str) -> int:
    return _rules().count_documents({"owner_id": owner_id})


def update_rule(
    rule_id: str,
    owner_id: str,
    rule: Rule,
    *,
    if_version: int,
) -> RuleRecord:
    """Replace a rule's definition, guarded on the version read."""
    now = datetime.now(UTC)
    result = _rules().update_one(
        {"_id": rule_id, "owner_id": owner_id, "version": if_version},
        {"$set": {"rule": _stored(rule), "updated_at": now}, "$inc": {"version": 1}},
    )
    if result.matched_count == 0:
        existing = _rules().find_one({"_id": rule_id, "owner_id": owner_id})
        if existing is None:
            raise KeyError(rule_id)
        raise StaleWriteError(
            "This rule was changed somewhere else after you opened it. "
            "Reload it to see the current version before saving again."
        )
    updated = find_rule(rule_id, owner_id)
    if updated is None:  # pragma: no cover - deleted between write and read
        raise KeyError(rule_id)
    return updated


def delete_rule(rule_id: str, owner_id: str) -> bool:
    """Forget a rule.

    Runs that used it are unaffected: each snapshotted its rules into its own
    state, so deleting one cannot rewrite a migration's history.
    """
    result = _rules().delete_one({"_id": rule_id, "owner_id": owner_id})
    return result.deleted_count > 0


def set_enabled(rule_id: str, owner_id: str, *, enabled: bool) -> RuleRecord:
    """Turn one of the caller's own rules on or off.

    Separate from `update_rule` and deliberately not version-guarded: toggling is
    idempotent and order-independent, so failing it on a concurrent edit would be
    friction with nothing to protect.
    """
    now = datetime.now(UTC)
    result = _rules().update_one(
        {"_id": rule_id, "owner_id": owner_id},
        {"$set": {"rule.enabled": enabled, "updated_at": now}, "$inc": {"version": 1}},
    )
    if result.matched_count == 0:
        raise KeyError(rule_id)
    updated = find_rule(rule_id, owner_id)
    if updated is None:  # pragma: no cover
        raise KeyError(rule_id)
    return updated


def override_builtin(
    owner_id: str, builtin_rule_id: str, *, schema_id: str, rationale: str = ""
) -> RuleRecord:
    """Disable a shipped rule for this session.

    Expressed as a rule of the caller's own rather than as a mutation, because the
    shipped layer is derived from code and has nothing to mutate. The consequence is
    the one we want: disagreeing with a shipped rule is a recorded, reversible,
    per-session act that leaves everyone else's engine untouched.
    """
    existing = _rules().find_one(
        {
            "owner_id": owner_id,
            "rule.kind": RuleKind.OVERRIDE.value,
            "rule.targets_rule_id": builtin_rule_id,
            "rule.schema_id": schema_id,
        }
    )
    if existing is not None:
        # Already overridden once and then re-enabled: flip it back rather than
        # accumulating a second override for the same target.
        return set_enabled(str(existing["_id"]), owner_id, enabled=True)
    return create_rule(
        owner_id,
        Rule(
            kind=RuleKind.OVERRIDE,
            origin=RuleOrigin.OVERRIDE,
            targets_rule_id=builtin_rule_id,
            # An override belongs to the schema whose shipped rule it disables, so
            # disagreeing with an alias for one contract leaves the others alone.
            schema_id=schema_id,
            rationale=rationale,
        ),
    )


def record_hits(hits: dict[str, int]) -> None:
    """Add a run's rule hits to their stored totals.

    Best effort and deliberately swallowed on failure: a hit count is a display
    number, and losing one must never turn a finished migration into an error. Ids
    that are not stored rules — the shipped layer, which has no row — are skipped.
    """
    writes = [
        UpdateOne({"_id": rule_id}, {"$inc": {"hits": count}})
        for rule_id, count in hits.items()
        if count > 0 and rule_id.startswith("rule_")
    ]
    if not writes:
        return
    try:
        _rules().bulk_write(writes, ordered=False)
    except Exception as error:
        logger.warning("could not record rule hits: %s", type(error).__name__)


def resolve_rules(owner_id: str, schema: TargetSchema) -> RuleSet:
    """The rules in force for one run: shipped, then the caller's own.

    Called once per run and snapshotted, so the rest of the engine never reaches
    for the database mid-decision.

    A database problem degrades to the shipped layer alone rather than failing the
    run. That is the same choice model assistance makes: the migration still works,
    it just knows less, and the trail says so because the learned marks are simply
    absent.
    """
    shipped = builtin_rules(schema)
    try:
        session = tuple(record.rule for record in list_rules(owner_id))
    except Exception as error:
        logger.warning("rule store unavailable: %s", type(error).__name__)
        session = ()
    return layered(shipped, session, schema_id=schema.schema_id)


def ensure_indexes() -> None:
    _rules().create_index([("owner_id", 1), ("updated_at", -1)])
