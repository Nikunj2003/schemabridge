"""Durable checkpointing.

This is the piece that makes human-in-the-loop viable on serverless. Each HTTP
request runs in a different process, so a run paused in memory would simply be
gone by the time the reviewer answers. Persisting checkpoints to MongoDB means
`interrupt()` genuinely suspends the workflow: a later request in another
process resumes it exactly where it stopped.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata
from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from schemabridge.domain import models, rules, schema, target
from schemabridge.server.config import get_settings
from schemabridge.server.mongo import get_client

logger = logging.getLogger(__name__)

_CHECKPOINT_DB_SUFFIX = "_checkpoints"

#: Every domain type that can appear inside checkpointed state.
#:
#: The serializer matches an exact (module, name) pair — there is no wildcard —
#: and a type it does not recognise comes back as a plain dict rather than the
#: model it was written as. Listing the classes themselves means the allowlist
#: cannot drift out of step with a rename, since an unknown name would not
#: import.
_ALLOWED_TYPES: tuple[type, ...] = (
    models.Actor,
    models.AppliedRepair,
    models.AuditEvent,
    models.CanonicalRecord,
    models.ColumnProfile,
    models.DeliveryAttempt,
    models.DeliveryIntent,
    models.DeliveryOutcome,
    models.DeliveryState,
    models.Disposition,
    # Reaches a channel as a bare enum on an event's own field, so it needs
    # listing in its own right. Without it every restored event's provenance
    # degraded to a plain string and the audit could no longer say what did the
    # work — a silent loss, since a string compares equal to the value it lost.
    models.EventExecutionBasis,
    models.IssueOption,
    models.IssueResolution,
    models.IssueStatus,
    models.IssueType,
    models.MappingBasis,
    models.MappingCandidate,
    models.MappingDecision,
    models.MappingOutcome,
    models.Provenance,
    models.ResolutionAction,
    models.ReviewIssue,
    models.RunCounters,
    models.RunPhase,
    models.SourceColumn,
    models.SourceFile,
    models.SourceKind,
    models.SourceRow,
    models.ValidationError,
    models.ValidationPass,
    models.ValidationPassLabel,
    target.TargetField,
    # Only the outer class needs listing: nested models, frozensets and tuples
    # ride along on it. Verified rather than assumed.
    schema.TargetSchema,
    schema.ValueKind,
    # Rules and proposals are top-level channel values, so each needs listing in
    # its own right. `RuleProvenance` rides along inside `Rule`, and `Rule` inside
    # `ProposedRule`, but both are also stored directly, so both are named.
    rules.DateOrder,
    rules.ProposedRule,
    rules.Rule,
    rules.RuleKind,
    rules.RuleOrigin,
    rules.RuleScope,
)


def build_serializer() -> JsonPlusSerializer:
    """Serializer that recognises this application's domain models.

    `pickle_fallback` stays off deliberately: everything in the state is a
    Pydantic model or a primitive, and allowing pickle would turn a checkpoint
    into arbitrary code execution on read.
    """
    return JsonPlusSerializer(
        pickle_fallback=False,
        allowed_msgpack_modules=_ALLOWED_TYPES,
    )


class FixedExpiryMongoDBSaver(MongoDBSaver):
    """LangGraph saver that uses the manifest's immutable run expiry.

    The upstream ``ttl`` option stamps a fresh ``created_at`` on every checkpoint
    write, extending retention as a run is advanced. This wrapper instead stores
    the run's immutable deadline and indexes that field on both collections.
    """

    def _expires_at(self, config: RunnableConfig) -> datetime | None:
        value = config.get("configurable", {}).get("run_expires_at")
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, str | int | float],
    ) -> RunnableConfig:
        result = super().put(config, checkpoint, metadata, new_versions)
        expires_at = self._expires_at(config)
        if expires_at is not None:
            self.checkpoint_collection.update_one(
                dict(result["configurable"]), {"$set": {"expires_at": expires_at}}
            )
        return result

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        super().put_writes(config, writes, task_id, task_path)
        expires_at = self._expires_at(config)
        if expires_at is None:
            return
        configurable = dict(config.get("configurable", {}))
        query: dict[str, Any] = {
            name: configurable[name]
            for name in ("thread_id", "checkpoint_ns", "checkpoint_id")
            if name in configurable
        }
        self.writes_collection.update_many(query, {"$set": {"expires_at": expires_at}})


def build_checkpointer(workspace_kind: str = "legacy") -> Any:
    """Build a saver for one retention policy.

    LangGraph's Mongo saver configures a collection-wide TTL. Separate databases
    keep the two explicitly different workspace retention policies from leaking
    into one another; the run registry additionally refuses expired manifests
    before Mongo's asynchronous TTL monitor has removed their checkpoints.
    """
    settings = get_settings()
    suffix = (
        _CHECKPOINT_DB_SUFFIX
        if workspace_kind == "legacy"
        else f"{_CHECKPOINT_DB_SUFFIX}_{workspace_kind}"
    )
    saver = FixedExpiryMongoDBSaver(
        get_client(),
        db_name=f"{settings.mongodb_db}{suffix}",
        serde=build_serializer(),
        # No upstream TTL: it is sliding. The immutable field below is authoritative.
        ttl=None,
    )
    for collection in (saver.checkpoint_collection, saver.writes_collection):
        collection.create_index("expires_at", expireAfterSeconds=0)
        _drop_sliding_ttl(collection)
    return saver


def _drop_sliding_ttl(collection: Any) -> None:
    """Remove the upstream `created_at` TTL index if an earlier build left one.

    It expires a document a fixed time after its own last write, so on a run that
    is still being advanced it competes with the immutable deadline above — and
    being the shorter of the two on an authenticated run, it would win. Best
    effort: an index that cannot be dropped must not stop the app from starting.
    """
    try:
        for index in collection.list_indexes():
            keys = list(index["key"].items())
            if keys == [("created_at", 1)] and "expireAfterSeconds" in index:
                collection.drop_index(index["name"])
    except Exception as error:
        logger.warning("could not drop a superseded TTL index: %s", type(error).__name__)
