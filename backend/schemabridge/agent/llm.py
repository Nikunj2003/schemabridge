"""The model client and its rate-limited, observed invocation boundary."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from schemabridge.agent.config import (
    EXTRA_BODY,
    MAX_RETRIES,
    STRUCTURED_OUTPUT_METHOD,
    STRUCTURED_OUTPUT_STRICT,
    TEMPERATURE,
    default_max_tokens,
    is_reasoning_model,
    model_id,
)
from schemabridge.server import model_exchanges, model_rate_limit, observability
from schemabridge.server.config import get_settings

logger = logging.getLogger(__name__)

__all__ = [
    "build_model",
    "default_max_tokens",
    "invoke_structured",
    "is_reasoning_model",
    "structured_model",
]


def build_model(*, max_tokens: int | None = None) -> ChatOpenAI:
    settings = get_settings()
    model = model_id()
    return ChatOpenAI(
        model=model,
        base_url=settings.nvidia_base_url,
        api_key=SecretStr(settings.require_model_key()),
        temperature=TEMPERATURE,
        max_completion_tokens=max_tokens or default_max_tokens(model),
        timeout=settings.model_timeout_seconds,
        # Retry ownership belongs below so each physical request observes the
        # shared 45 RPM gate and persists its outcome.
        max_retries=MAX_RETRIES,
        extra_body=EXTRA_BODY,
    )


def structured_model(schema: type, *, max_tokens: int | None = None) -> Any:
    return build_model(max_tokens=max_tokens).with_structured_output(
        schema, method=STRUCTURED_OUTPUT_METHOD, strict=STRUCTURED_OUTPUT_STRICT
    )


def _serialise(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, tuple):
        return [_serialise(item) for item in value]
    if isinstance(value, list):
        return [_serialise(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialise(item) for key, item in value.items()}
    return value


def _record(write: Callable[[], None]) -> None:
    """Journal an attempt without letting bookkeeping sink a working migration.

    The evidence trail is valuable but never authoritative for the run itself: a
    Mongo hiccup must not turn a successful model call into a failed one.
    """
    try:
        write()
    except Exception as error:
        logger.warning("could not record a model exchange: %s", type(error).__name__)


def _retryable(error: Exception) -> bool:
    name = type(error).__name__.lower()
    return any(marker in name for marker in ("rate", "timeout", "connection", "server", "apierror"))


def invoke_structured(
    schema: type,
    messages: list[tuple[str, str]],
    *,
    operation: str,
    run_id: str,
    owner_id: str,
    workspace_kind: str,
    expires_at: datetime,
) -> Any:
    """Call a constrained model after a shared rate reservation and record it.

    The same logical product budget is charged by the caller once. Retried provider
    attempts are recorded here but do not repeatedly consume that product budget.
    """
    settings = get_settings()
    exchange_id = model_exchanges.new_exchange_id()
    started = time.monotonic()
    request = _serialise(messages)
    # Written before the outbound call, so an interrupted request still leaves
    # evidence that it was made.
    _record(
        lambda: model_exchanges.start(
            exchange_id=exchange_id,
            run_id=run_id,
            owner_id=owner_id,
            workspace_kind=workspace_kind,
            expires_at=expires_at,
            operation=operation,
            model=model_id(),
            request=request,
        )
    )
    attempts = 0
    error: Exception | None = None
    for attempts in range(1, settings.nvidia_retry_attempts + 1):
        try:
            model_rate_limit.reserve_slot()
            proposal = structured_model(schema).invoke(messages)
            elapsed = int((time.monotonic() - started) * 1000)
            response = _serialise(proposal)

            # Bound as defaults rather than captured: a late-binding closure
            # would read whatever the loop variables held by the time it ran.
            def _finish(
                answer: Any = response, attempt: int = attempts, took: int = elapsed
            ) -> None:
                model_exchanges.finish(
                    exchange_id, response=answer, attempts=attempt, latency_ms=took
                )

            _record(_finish)
            observability.export_generation(
                {
                    "_id": exchange_id,
                    "run_id": run_id,
                    "owner_id": owner_id,
                    "operation": operation,
                    "model": model_id(),
                    "request": request,
                    "response": response,
                    "status": "completed",
                    "attempts": attempts,
                }
            )
            return proposal
        except Exception as caught:
            error = caught
            if not _retryable(caught) or attempts >= settings.nvidia_retry_attempts:
                break
            time.sleep(min(2**attempts, 8))
    elapsed = int((time.monotonic() - started) * 1000)
    _record(
        lambda: model_exchanges.fail(
            exchange_id,
            error=type(error).__name__ if error else "UnknownModelError",
            attempts=attempts,
            latency_ms=elapsed,
        )
    )
    if error is not None:
        raise error
    raise RuntimeError("Model invocation did not start.")
