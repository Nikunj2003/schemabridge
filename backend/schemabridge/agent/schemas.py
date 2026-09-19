"""Structured shapes the model is allowed to return.

The model proposes; it never decides. Everything it sends back is validated
against these schemas and then re-checked against deterministic evidence before
anything is applied, so a hallucinated field name or an invented value is
rejected rather than migrated.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProposedMapping(BaseModel):
    """One suggested pairing of a source column with a target field."""

    model_config = ConfigDict(extra="forbid")

    column_id: str = Field(description="The exact source column id from the profile")
    target: str = Field(description="One permitted target field name")
    reason: str = Field(description="One short sentence on why the column holds that field's data")


class MappingProposal(BaseModel):
    """The model's final answer for a batch of unresolved columns.

    Columns it cannot place confidently are simply left out — an omission is a
    useful signal, and far better than a guess dressed up as an answer.
    """

    model_config = ConfigDict(extra="forbid")

    mappings: list[ProposedMapping] = Field(
        default_factory=list,
        description="Only columns you can place confidently. Omit the rest.",
    )
