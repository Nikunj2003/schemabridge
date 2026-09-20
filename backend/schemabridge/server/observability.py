"""Optional, fail-open Langfuse export for persisted model evidence."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from langfuse import Langfuse

from schemabridge.server.config import get_settings

logger = logging.getLogger(__name__)


def _mask(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            key: "[redacted]"
            if any(
                token in key.lower() for token in ("secret", "token", "authorization", "api_key")
            )
            else _mask(value)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [_mask(value) for value in data]
    return data


def export_generation(exchange: dict[str, Any]) -> None:
    """Export one completed logical exchange, without affecting migration output."""
    settings = get_settings()
    if not settings.langfuse_configured:
        return
    try:
        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            mask=lambda *, data, **_: _mask(data),
        )
        owner_hash = hashlib.sha256(str(exchange.get("owner_id", "")).encode()).hexdigest()[:16]
        payload = (
            exchange.get("request") if settings.langfuse_capture_content else {"captured": False}
        )
        output = (
            exchange.get("response")
            if settings.langfuse_capture_content
            else {"status": exchange.get("status")}
        )
        with client.start_as_current_observation(
            name=str(exchange.get("operation", "model-call")),
            as_type="generation",
            model=str(exchange.get("model", "")),
            input=payload,
            metadata={
                "run_id": exchange.get("run_id"),
                "exchange_id": exchange.get("_id"),
                "owner": owner_hash,
                "attempts": exchange.get("attempts", 0),
            },
        ) as generation:
            generation.update(output=output)
        client.flush()
    except Exception as error:
        logger.warning("langfuse export failed: %s", type(error).__name__)
