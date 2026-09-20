"""Durable checkpointing.

This is the piece that makes human-in-the-loop viable on serverless. Each HTTP
request runs in a different process, so a run paused in memory would simply be
gone by the time the reviewer answers. Persisting checkpoints to MongoDB means
`interrupt()` genuinely suspends the workflow: a later request in another
process resumes it exactly where it stopped.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from schemabridge.domain import models, rules, schema, target
from schemabridge.server.config import get_settings
from schemabridge.server.mongo import get_client

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


def build_checkpointer() -> Any:
    """A MongoDB-backed checkpointer sharing the application's connection pool.

    Checkpoints live in their own database so LangGraph's collections stay
    separate from the application's, and expire on a TTL — a free cluster has
    limited storage and keeping synthetic demo runs forever serves no purpose.
    """
    settings = get_settings()
    return MongoDBSaver(
        get_client(),
        db_name=f"{settings.mongodb_db}{_CHECKPOINT_DB_SUFFIX}",
        serde=build_serializer(),
        ttl=settings.run_ttl_hours * 3600,
    )
