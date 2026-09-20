"""Learned rules: the part of the policy a person owns.

The shipped engine decides from evidence it can derive — a header spelling, a
value's shape, whether two fields both claim one name. That covers the exports it
was written against and, because the derivation is generic, a good deal more. What
it cannot do is know that *this* client writes `Cost Centre Ref` where the schema
says `department`. Nobody can derive that. It has to be told once.

This module is where being told once is stored. A rule is the durable form of a
decision a person already made, so the second migration of the same export asks
nothing, calls no model, and costs nothing.

Four commitments shape the design, and each rules something out:

* **A rule is data, never an expression.** Every match is equality on an
  already-normalised string. No user-supplied regex, no predicate, no template.
  That is partly the obvious injection and ReDoS argument, but mostly it is what
  makes a rule previewable: the page can say exactly which columns and values a
  draft would touch, because matching has no hidden behaviour.

* **A rule can only say what the engine could already have concluded.** Each kind
  feeds a decision the deterministic code makes today, at the same gate, producing
  the same kind of answer. A rule therefore cannot invent a value, skip
  validation, or reach the destination — it can only supply evidence earlier than
  the engine would have found it, or not at all.

* **Shipped rules are not editable, and are not stored.** They are derived from
  the code that implements them, so the two cannot drift; there is no seed step
  and no migration. Disagreeing with one is expressed as an *override* in your own
  layer, which disables it for you and leaves it intact for everyone else.

* **A rule never silently outranks an escalation.** `Date`, which both a start and
  an end field claim, stays ambiguous no matter how many rules exist, unless a rule
  names that exact header for one field. Overlap between fields is the mechanism
  that makes a genuinely ambiguous column escalate, and quietly resolving it is the
  worst failure available here: every row in the file is misdated and nothing says
  so.

The layering is override → yours → shipped. An empty rule set must behave exactly
as the engine did before this module existed, which is asserted directly rather
than assumed.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schemabridge.domain.normalize import normalize_header, trim_surrounding
from schemabridge.domain.schema import TargetSchema, ValueKind

#: Longest stored match or replacement value. Long enough for any real header or
#: enum spelling, short enough that a rule cannot be used to store a document.
MAX_RULE_VALUE = 120

#: One sentence explaining why a rule exists, shown wherever the rule is. Capped
#: because it is displayed inline, and because a model writes some of them.
MAX_RATIONALE = 240

#: Rules one session may hold. A limit on stored state, not on expressiveness.
MAX_RULES_PER_SESSION = 200


class RuleKind(StrEnum):
    """What a rule decides.

    Closed, and each member names an existing decision point. Adding a kind means
    adding a consumer in the deterministic path — which is the point: a rule kind
    with no consumer would be configuration that silently does nothing.
    """

    #: This header means this field. Feeds the mapping candidate gates.
    HEADER_ALIAS = "header_alias"
    #: This spelling of an enum value means this member. Feeds safe repairs.
    VALUE_ALIAS = "value_alias"
    #: Numeric dates in this column are day-first (or month-first). Feeds date
    #: parsing, and only where the reading is otherwise genuinely ambiguous.
    DATE_ORDER = "date_order"
    #: This header carries nothing worth migrating. Feeds column selection.
    COLUMN_IGNORE = "column_ignore"
    #: Disable a shipped rule, for this session only.
    OVERRIDE = "override"


class RuleOrigin(StrEnum):
    """Where a rule came from. Provenance, not permission."""

    #: Derived from code. Read-only, never stored.
    BUILTIN = "builtin"
    #: Typed by the person on the rules page.
    HANDWRITTEN = "handwritten"
    #: Proposed by the model from a decision the person made, then approved.
    LEARNED = "learned"
    #: A disagreement with a shipped rule.
    OVERRIDE = "override"


class DateOrder(StrEnum):
    """Which number comes first in an ambiguous numeric date."""

    DAY_FIRST = "day_first"
    MONTH_FIRST = "month_first"


class RuleProvenance(BaseModel):
    """The decision a learned rule came from.

    Kept so the rules page can show the question that produced a rule rather than
    asking someone to trust an assertion about their own past behaviour.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = ""
    issue_id: str = ""
    #: The reviewer's answer, as the engine recorded it.
    decision: str = ""


class Rule(BaseModel):
    """One learned decision.

    `match` and `apply` are deliberately narrow scalars rather than open
    dictionaries: a rule whose shape varied per kind could not be validated once,
    and the validation is the only thing standing between a proposal and the
    engine.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str = ""
    kind: RuleKind
    origin: RuleOrigin = RuleOrigin.HANDWRITTEN
    enabled: bool = True

    #: Normalised source header. Set for HEADER_ALIAS and COLUMN_IGNORE, and
    #: optionally for DATE_ORDER when the rule is scoped to one column.
    header: str = ""
    #: Target field this rule concerns. Set for HEADER_ALIAS, VALUE_ALIAS, and
    #: optionally DATE_ORDER.
    field_name: str = ""
    #: Normalised source value. Set for VALUE_ALIAS.
    value: str = ""
    #: Canonical enum member. Set for VALUE_ALIAS.
    canonical: str = ""
    #: Reading for ambiguous numeric dates. Set for DATE_ORDER.
    date_order: DateOrder | None = None
    #: Shipped rule this one disables. Set for OVERRIDE.
    targets_rule_id: str = ""

    #: Which schema this rule belongs to. Required, for every kind.
    #:
    #: A rule is a statement about migrating onto one contract, so it is owned by
    #: that contract. Two kinds could not work otherwise — `header_alias` and
    #: `value_alias` name a target field, and mean nothing against a schema without
    #: it — but the other three are scoped for a different and better reason: a
    #: person reading the rules page has to be able to answer "will this affect the
    #: migration I am about to run", and a rule that silently applies everywhere
    #: makes that unanswerable. Teaching the same fact for a second client is one
    #: click; discovering that a rule from an unrelated engagement quietly changed
    #: this one is a support case.
    schema_id: str

    rationale: str = Field(default="", max_length=MAX_RATIONALE)
    provenance: RuleProvenance | None = None
    #: Times this rule has supplied an answer. What makes a savings claim checkable.
    hits: int = 0

    @field_validator("header", "value", mode="before")
    @classmethod
    def _normalize_match(cls, raw: Any) -> Any:
        """Store matches in the form they are compared in.

        Normalising on the way in rather than at every comparison is what keeps a
        rule previewable: what the page shows is what will be matched.
        """
        if not isinstance(raw, str):
            return raw
        return normalize_header(raw)[:MAX_RULE_VALUE]

    @field_validator("field_name", "canonical", "targets_rule_id", "schema_id", mode="before")
    @classmethod
    def _tidy(cls, raw: Any) -> Any:
        if not isinstance(raw, str):
            return raw
        return trim_surrounding(raw)[:MAX_RULE_VALUE]

    @field_validator("rationale", mode="before")
    @classmethod
    def _tidy_rationale(cls, raw: Any) -> Any:
        if not isinstance(raw, str):
            return raw
        return trim_surrounding(raw)[:MAX_RATIONALE]

    @model_validator(mode="after")
    def _check_shape(self) -> Rule:
        """Every kind must carry exactly what its consumer needs.

        A rule missing a field it needs would be stored happily and then do
        nothing, which is worse than being refused: the person believes they have
        taught the engine something.
        """
        if not self.schema_id:
            raise ValueError("A rule has to name the schema it applies to.")

        if self.kind is RuleKind.HEADER_ALIAS:
            if not self.header or not self.field_name:
                raise ValueError("A header alias needs both a header and a target field.")
        elif self.kind is RuleKind.VALUE_ALIAS:
            if not self.field_name or not self.value or not self.canonical:
                raise ValueError("A value alias needs a field, a source value and a canonical one.")
        elif self.kind is RuleKind.DATE_ORDER:
            if self.date_order is None:
                raise ValueError("A date rule needs a reading: day-first or month-first.")
            if not self.header and not self.field_name:
                raise ValueError("A date rule needs a column or a field to apply to.")
        elif self.kind is RuleKind.COLUMN_IGNORE:
            if not self.header:
                raise ValueError("An ignore rule needs a header.")
        elif self.kind is RuleKind.OVERRIDE and not self.targets_rule_id:
            raise ValueError("An override needs the rule it disables.")
        return self

    def applies_to(self, schema_id: str) -> bool:
        """Whether this rule is in force for a run against `schema_id`.

        Exact equality, with no wildcard. A rule that could apply to a schema it was
        not written for is a rule nobody can reason about from the page.
        """
        return self.schema_id == schema_id


class RuleScope(StrEnum):
    """How far a proposed rule reaches, which decides when it may be offered.

    The distinction is not cosmetic. A value-scope rule settles a question that is
    about to be asked again for every remaining record carrying the same spelling,
    so offering it mid-run turns many questions into one. A column-scope rule
    cannot help the run that produced it — mapping is decided once, before records
    exist — so offering it mid-run would interrupt someone with a choice that
    changes nothing until next time.
    """

    #: Applies to the remaining values in this run, and to future runs.
    VALUE = "value"
    #: Applies to future runs only.
    COLUMN = "column"


class ProposedRule(BaseModel):
    """A rule the model drafted from a decision, awaiting approval.

    Held on the run rather than written straight to the rule store, because an
    unapproved rule is not a rule. The reviewer's decision is already recorded and
    already applied; this is a separate offer, and declining it must leave no trace
    in the engine's behaviour.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: str
    rule: Rule
    scope: RuleScope
    #: Why this generalises, in the model's words, for the person deciding.
    rationale: str = Field(default="", max_length=MAX_RATIONALE)
    #: Whether the reviewer pre-authorised this by ticking "remember this", in
    #: which case a value-scope proposal applies without a second interruption.
    pre_approved: bool = False


class RuleSet:
    """The rules in force for one run, already layered.

    Built once per run and passed down, so the deterministic functions stay pure
    and testable and no layer of the engine reaches for the database mid-decision.

    Hits are counted here rather than written through, because a rule firing is
    not a decision anyone needs durably ordered — and a write per matched value
    would put a database round trip inside the mapping loop.
    """

    __slots__ = (
        "_by_header",
        "_dates_by_field",
        "_dates_by_header",
        "_hits",
        "_ignored",
        "_source",
        "_values",
    )

    def __init__(self, rules: tuple[Rule, ...] = (), *, schema_id: str = "") -> None:
        # Kept verbatim, including the entries this set filtered out. A run
        # snapshots what it was given rather than what survived resolution, so a
        # rule disabled today and re-enabled tomorrow does not silently change what
        # a paused run decides when it resumes.
        self._source = rules
        disabled = {
            rule.targets_rule_id
            for rule in rules
            if rule.kind is RuleKind.OVERRIDE and rule.enabled
        }
        active = [
            rule
            for rule in rules
            if rule.enabled
            and rule.kind is not RuleKind.OVERRIDE
            and rule.rule_id not in disabled
            and rule.applies_to(schema_id)
        ]

        # Later rules win within a layer, and callers hand over the layers in
        # precedence order — so a session rule overwrites a shipped one for the
        # same header without either needing to know about the other.
        self._by_header: dict[str, Rule] = {}
        self._values: dict[tuple[str, str], Rule] = {}
        self._dates_by_header: dict[str, Rule] = {}
        self._dates_by_field: dict[str, Rule] = {}
        self._ignored: dict[str, Rule] = {}
        self._hits: dict[str, int] = {}

        for rule in active:
            if rule.kind is RuleKind.HEADER_ALIAS:
                self._by_header[rule.header] = rule
            elif rule.kind is RuleKind.VALUE_ALIAS:
                self._values[(rule.field_name, rule.value)] = rule
            elif rule.kind is RuleKind.DATE_ORDER:
                if rule.header:
                    self._dates_by_header[rule.header] = rule
                if rule.field_name:
                    self._dates_by_field[rule.field_name] = rule
            elif rule.kind is RuleKind.COLUMN_IGNORE:
                self._ignored[rule.header] = rule

    def __bool__(self) -> bool:
        return bool(
            self._by_header
            or self._values
            or self._dates_by_header
            or self._dates_by_field
            or self._ignored
        )

    def _hit(self, rule: Rule) -> Rule:
        self._hits[rule.rule_id] = self._hits.get(rule.rule_id, 0) + 1
        return rule

    @property
    def rules(self) -> tuple[Rule, ...]:
        """Every rule handed to this set, for snapshotting onto a run."""
        return self._source

    @property
    def hits(self) -> dict[str, int]:
        """Rule id to times fired, for persisting after the run."""
        return dict(self._hits)

    def alias_for(self, header: str) -> Rule | None:
        """The rule mapping this header onto a field, if one exists."""
        rule = self._by_header.get(normalize_header(header))
        return self._hit(rule) if rule is not None else None

    def canonical_for(self, field_name: str, value: str) -> Rule | None:
        """The rule canonicalising this value for this field, if one exists."""
        key = (field_name, normalize_header(value))
        rule = self._values.get(key)
        return self._hit(rule) if rule is not None else None

    def date_order_for(self, *, header: str = "", field_name: str = "") -> Rule | None:
        """The reading for ambiguous numeric dates here, if one was taught.

        A column-specific rule wins over a field-wide one: the person who said
        "this export writes day-first" was looking at a column, and another column
        of the same field may come from a system that does not.
        """
        if header:
            rule = self._dates_by_header.get(normalize_header(header))
            if rule is not None:
                return self._hit(rule)
        if field_name:
            rule = self._dates_by_field.get(field_name)
            if rule is not None:
                return self._hit(rule)
        return None

    def ignores(self, header: str) -> Rule | None:
        """The rule dropping this column, if one exists."""
        rule = self._ignored.get(normalize_header(header))
        return self._hit(rule) if rule is not None else None


#: The rule set that changes nothing.
#:
#: Every consumer defaults to this, so adding the overlay could not alter existing
#: behaviour even if a caller forgot to pass one. `test_rules.py` asserts the
#: equivalence directly on the shipped fixtures rather than trusting the argument.
EMPTY_RULES: Final = RuleSet()


# ---------------------------------------------------------------------------
# The shipped layer, derived rather than stored
# ---------------------------------------------------------------------------


def builtin_rule_id(kind: RuleKind, *parts: str) -> str:
    """A stable id for a rule that lives in code.

    Deterministic, so an override written today still names the same rule after a
    redeploy. The `builtin:` prefix is also what stops a stored rule impersonating
    a shipped one: ids for stored rules are assigned by the server and always
    carry their own prefix.
    """
    return ":".join(("builtin", kind.value, *parts))


def builtin_rules(schema: TargetSchema) -> tuple[Rule, ...]:
    """The shipped rule layer for one schema, projected from the code.

    Derived on demand rather than seeded into the database, which is what keeps the
    two from drifting: there is only one definition, and it is the one the engine
    actually consults.

    A header claimed by more than one field is deliberately omitted. Those are the
    overlaps that make a column ambiguous, and presenting them as two separate
    rules would invite someone to disable one and so convert a correct escalation
    into a silent mapping — the exact failure this feature must not enable. The
    ambiguity is shown on the page as what it is: a property of the schema.
    """
    rules: list[Rule] = []

    for field_name, names in sorted(schema.spelling_index.items()):
        if len(names) != 1:
            continue
        spec = schema.field(names[0])
        if spec is None or field_name == spec.name.lower():
            # A header identical to the field's own name is not an alias; it needs
            # no rule and disabling it would be meaningless.
            continue
        rules.append(
            Rule(
                rule_id=builtin_rule_id(RuleKind.HEADER_ALIAS, spec.name, field_name),
                kind=RuleKind.HEADER_ALIAS,
                origin=RuleOrigin.BUILTIN,
                header=field_name,
                field_name=spec.name,
                schema_id=schema.schema_id,
                rationale=f'"{field_name}" is a known spelling of {spec.label}.',
            )
        )

    for spec in schema.fields:
        for spelling, canonical in sorted(spec.value_aliases.items()):
            if canonical not in spec.enum_values:
                continue
            rules.append(
                Rule(
                    rule_id=builtin_rule_id(RuleKind.VALUE_ALIAS, spec.name, spelling),
                    kind=RuleKind.VALUE_ALIAS,
                    origin=RuleOrigin.BUILTIN,
                    field_name=spec.name,
                    value=spelling,
                    canonical=canonical,
                    schema_id=schema.schema_id,
                    rationale=f'"{spelling}" is a known spelling of "{canonical}".',
                )
            )

    return tuple(rules)


def layered(
    builtin: tuple[Rule, ...], session: tuple[Rule, ...], *, schema_id: str = ""
) -> RuleSet:
    """Compose the two layers in precedence order: shipped first, yours second.

    Held here rather than at the call site so precedence is decided once. A caller
    that assembled its own order could silently let a shipped rule win over the
    person's own, which would make the rules page a suggestion box.
    """
    return RuleSet(builtin + session, schema_id=schema_id)


class RuleRejectedError(ValueError):
    """A rule the engine will not stand behind, with a reason to show."""


def check_against_schema(rule: Rule, schema: TargetSchema) -> None:
    """Refuse a rule the schema cannot support, whoever wrote it.

    Lives here rather than in the route or the induction module because both need
    exactly this answer, and the two must not be able to drift: a rule a person
    types by hand is applied by the same engine as one the model drafts, so it has
    to clear the same bar. An earlier version of this feature checked only the
    model's drafts, which meant the safest path was the automated one and the
    dangerous path was the manual one.

    Three refusals, in order of how much damage each prevents.
    """
    if rule.kind is RuleKind.OVERRIDE:
        return

    if rule.kind is RuleKind.HEADER_ALIAS:
        claimants = schema.fields_for_header(rule.header)
        if len(claimants) > 1:
            # The worst outcome this feature could produce. A header two fields
            # both claim is what makes a column escalate; a rule settling it would
            # silently resolve every future occurrence, and if the guess is wrong
            # every row in those files is wrong with nothing saying so.
            labels = " or ".join(
                spec.label for name in claimants if (spec := schema.field(name)) is not None
            )
            raise RuleRejectedError(
                f'"{rule.header}" could be {labels}, so a rule cannot settle it. '
                f"A column like this is meant to be asked about, because choosing "
                f"wrong would change every record in the file without saying so."
            )

    if rule.kind in {RuleKind.HEADER_ALIAS, RuleKind.VALUE_ALIAS}:
        spec = schema.field(rule.field_name)
        if spec is None:
            raise RuleRejectedError(f'"{rule.field_name}" is not a field in the target schema.')
        if rule.kind is RuleKind.VALUE_ALIAS:
            if spec.kind is not ValueKind.ENUM:
                raise RuleRejectedError(
                    f"{spec.label} does not have a fixed set of values, so there is "
                    f"nothing for a value rule to canonicalise onto."
                )
            if rule.canonical not in spec.enum_values:
                permitted = ", ".join(spec.enum_values)
                raise RuleRejectedError(
                    f'"{rule.canonical}" is not one of the values {spec.label} permits '
                    f"({permitted}). A rule writing anything else would fail validation "
                    f"later, with nothing to say where the value came from."
                )

    if rule.kind is RuleKind.DATE_ORDER and rule.field_name:
        spec = schema.field(rule.field_name)
        if spec is None:
            raise RuleRejectedError(f'"{rule.field_name}" is not a field in the target schema.')
        if spec.kind is not ValueKind.DATE:
            raise RuleRejectedError(
                f"{spec.label} does not hold dates, so a date rule cannot apply."
            )
