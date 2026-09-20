"""The model client.

Construction only. Every value it sends — the model id, the temperature, the
per-family output ceilings, the structured-output strategy — lives in
`agent.config` alongside the measurements that chose it, so this module is the
one place that *builds* a client and nowhere that decides how one should behave.

`is_reasoning_model` and `default_max_tokens` are re-exported because callers
reason about output ceilings without caring where the thresholds are defined.
"""

from __future__ import annotations

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
from schemabridge.server.config import get_settings

__all__ = ["build_model", "default_max_tokens", "is_reasoning_model", "structured_model"]


def build_model(*, max_tokens: int | None = None) -> ChatOpenAI:
    """A chat model pointed at whichever endpoint is configured."""
    settings = get_settings()
    model = model_id()
    return ChatOpenAI(
        model=model,
        base_url=settings.nvidia_base_url,
        api_key=SecretStr(settings.require_model_key()),
        temperature=TEMPERATURE,
        # This client renamed the constructor parameter to `max_completion_tokens`,
        # following the OpenAI API; it sends the same field either way, and passing
        # the old name through `model_kwargs` only earns a warning. Verified by
        # comparing the request payloads.
        max_completion_tokens=max_tokens or default_max_tokens(model),
        timeout=settings.model_timeout_seconds,
        max_retries=MAX_RETRIES,
        extra_body=EXTRA_BODY,
    )


def structured_model(schema: type, *, max_tokens: int | None = None) -> Any:
    """A model constrained to return `schema`."""
    return build_model(max_tokens=max_tokens).with_structured_output(
        schema, method=STRUCTURED_OUTPUT_METHOD, strict=STRUCTURED_OUTPUT_STRICT
    )
