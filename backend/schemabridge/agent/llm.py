"""The model client, configured from measurement rather than defaults.

The model is chosen by environment variable, not baked in. That is deliberate:
free endpoints fluctuate badly. The same Nemotron endpoint answered a bare ping
in 17s one hour and 75s the next, while gpt-oss answered the same
schema-constrained request in 11s. Neither is reliably the faster choice, so
switching has to be a one-line change with no code edit.

Different model families expose the same idea under different names, and an
endpoint ignores parameters it does not recognise. Rather than branch on the
model id, every known switch is sent together — with per-family output ceilings,
because that is the one setting where a single value does not suit both.

Measured behaviour that drove these numbers:

| Setting                          | Effect                                    |
| -------------------------------- | ----------------------------------------- |
| gpt-oss at 300 output tokens     | returned only reasoning, no answer at all  |
| gpt-oss at default effort        | 26s; at low effort, 11s, same answer       |
| Nemotron with reasoning enabled  | exceeded 45s and returned nothing usable   |
| Nemotron with reasoning_budget 0 | answered in about 30s                      |
"""

from __future__ import annotations

from typing import Any, Final

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from schemabridge.server.config import get_settings

#: Sent on every request. `reasoning_effort` is honoured by the gpt-oss family,
#: `reasoning_budget` and `enable_thinking` by the Nemotron family. Sending all
#: three keeps one adapter working across both without inspecting the model id.
_EXTRA_BODY: Final[dict[str, Any]] = {
    "reasoning_effort": "low",
    "reasoning_budget": 0,
    "chat_template_kwargs": {"enable_thinking": False},
}

#: Output ceilings differ by family, and this is the one place a shared value
#: fails. A reasoning model emits its thinking before the answer, so too small a
#: ceiling truncates mid-thought and yields nothing; a non-reasoning model just
#: wastes budget on headroom it never uses.
_REASONING_MAX_TOKENS: Final = 1500
_DIRECT_MAX_TOKENS: Final = 600

#: Model families that spend output tokens on visible reasoning first.
_REASONING_FAMILIES: Final = ("gpt-oss", "deepseek", "qwen3", "nemotron-3.5", "glm")


def is_reasoning_model(model_id: str) -> bool:
    """Whether this model spends output tokens thinking before answering."""
    lowered = model_id.lower()
    return any(family in lowered for family in _REASONING_FAMILIES)


def default_max_tokens(model_id: str) -> int:
    """Output ceiling appropriate to the model's family."""
    return _REASONING_MAX_TOKENS if is_reasoning_model(model_id) else _DIRECT_MAX_TOKENS


def build_model(*, max_tokens: int | None = None) -> ChatOpenAI:
    """A chat model pointed at whichever endpoint is configured."""
    settings = get_settings()
    model_id = settings.nvidia_model
    return ChatOpenAI(
        model=model_id,
        base_url=settings.nvidia_base_url,
        api_key=SecretStr(settings.require_model_key()),
        temperature=0,  # Mapping a column to a field is not a creative task.
        # This OpenAI-compatible endpoint expects the established `max_tokens`
        # request field. Current LangChain types expose the newer
        # `max_completion_tokens` constructor parameter instead, so keep the
        # endpoint-specific field in the documented pass-through map.
        model_kwargs={"max_tokens": max_tokens or default_max_tokens(model_id)},
        timeout=settings.model_timeout_seconds,
        # Without this the client retries transparently, turning one logical
        # request into three upstream calls and quietly outspending the budget.
        max_retries=0,
        extra_body=_EXTRA_BODY,
    )


def structured_model(schema: type, *, max_tokens: int | None = None) -> Any:
    """A model returning `schema`, using the strategy measured as fastest.

    Of the four strategies available, `json_schema` with `strict=True` was the
    only one both fast and reliable. The default took twice as long, `json_mode`
    timed out, and `function_calling` returned a null target *without raising* —
    which would have written nulls into mappings rather than failing visibly.
    """
    return build_model(max_tokens=max_tokens).with_structured_output(
        schema, method="json_schema", strict=True
    )
