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

from schemabridge.server.config import get_settings
from schemabridge.server.mongo import get_client

_CHECKPOINT_DB_SUFFIX = "_checkpoints"

#: Modules whose types appear inside checkpointed state — the domain models and
#: the enums they reference. The serializer warns on unregistered types today and
#: will refuse them in a later version, so they are declared explicitly rather
#: than relying on a default that is going away.
_ALLOWED_MODULES: tuple[tuple[str, str], ...] = (
    ("schemabridge.domain.models", "*"),
    ("schemabridge.domain.target", "*"),
)


def build_serializer() -> JsonPlusSerializer:
    """Serializer that recognises this application's domain models.

    `pickle_fallback` stays off deliberately: everything in the state is a
    Pydantic model or a primitive, and allowing pickle would turn a checkpoint
    into arbitrary code execution on read.
    """
    return JsonPlusSerializer(
        pickle_fallback=False,
        allowed_msgpack_modules=_ALLOWED_MODULES,
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
