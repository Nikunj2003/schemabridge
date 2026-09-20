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


class RankedOption(BaseModel):
    """One of the engine's own options, with a reason to prefer it."""

    model_config = ConfigDict(extra="forbid")

    option_id: str = Field(description="An option id exactly as the question offered it")
    why: str = Field(description="One short sentence on what the evidence favours")


class EscalationGuidance(BaseModel):
    """Help for a person answering a question the engine could not settle.

    Advisory by construction. The model may rank options the engine already offered
    and say what the evidence favours; it cannot add an option, answer, or change
    what the question is. Any option id it returns that the question did not offer
    is dropped rather than shown, so a hallucinated choice cannot appear as
    something clickable.

    There is no confidence field, here as everywhere. A reviewer cannot act on
    0.87, and a self-reported number would read as calibrated when it is not.
    """

    model_config = ConfigDict(extra="forbid")

    ranked_options: list[RankedOption] = Field(
        default_factory=list,
        description="The offered options, most likely first. Omit any you cannot justify.",
    )
    caveat: str = Field(
        default="",
        description="What would make this reading wrong, in one sentence. Empty if nothing would.",
    )


class ProposedRuleDraft(BaseModel):
    """A rule the model thinks a decision generalises into.

    Narrow on purpose: the model chooses a kind and fills the few scalars that kind
    needs. It cannot write a pattern, a predicate, or a field the rule model does
    not already have — the shape is the whole safety argument, since the draft is
    then validated into a `Rule` and checked against the run's schema before anyone
    is offered it.
    """

    model_config = ConfigDict(extra="forbid")

    generalises: bool = Field(
        description="False when this decision is about one record and teaches nothing"
    )
    kind: str = Field(
        default="",
        description="One of: header_alias, value_alias, date_order, column_ignore",
    )
    header: str = Field(default="", description="Source column header, for header rules")
    field_name: str = Field(default="", description="Target field name this rule concerns")
    value: str = Field(default="", description="Source value, for a value rule")
    canonical: str = Field(default="", description="Canonical target value, for a value rule")
    date_order: str = Field(default="", description="day_first or month_first, for a date rule")
    rationale: str = Field(
        default="",
        description="One sentence a non-technical reviewer can judge, naming the evidence",
    )
