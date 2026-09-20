"""Rule induction, and the four things it must refuse.

Every test here is about a refusal. Induction's value is obvious and its risk is
not: a wrong rule is applied silently to every future migration, long after the
person who approved it has forgotten the question it came from. So the interesting
behaviour is what never reaches them.

No model is called anywhere in this file. The pre-filter and the verifier are both
deterministic, which is the point — the expensive, unreliable step sits between two
cheap, reliable ones.
"""

from __future__ import annotations

import pytest

from schemabridge.agent.induce import _verified_rule, is_generalisable
from schemabridge.agent.schemas import ProposedRuleDraft
from schemabridge.domain.models import IssueOption, IssueType, ReviewIssue
from schemabridge.domain.rules import RuleKind, RuleOrigin
from schemabridge.domain.target import BUILTIN_SCHEMA

SCHEMA = BUILTIN_SCHEMA


def _issue(issue_type: IssueType, **extra: object) -> ReviewIssue:
    return ReviewIssue(
        id="issue:test",
        type=issue_type,
        reason="Something needed a person.",
        blocking=True,
        options=(
            IssueOption(
                id="map:department", label="Map to Department", detail="Use it as Department."
            ),
        ),
        **extra,  # type: ignore[arg-type]
    )


def _draft(**fields: object) -> ProposedRuleDraft:
    base: dict[str, object] = {"generalises": True}
    base.update(fields)
    return ProposedRuleDraft.model_validate(base)


class TestPreFilter:
    """The half that runs before any request, so a refusal costs nothing."""

    @pytest.mark.parametrize(
        "issue_type",
        [
            IssueType.VALIDATION_FAILED_TWICE,
            IssueType.IDENTITY_CONFLICT,
            IssueType.DUPLICATE_EMAIL,
            IssueType.DELIVERY_FAILED,
        ],
    )
    def test_record_level_decisions_never_reach_the_model(self, issue_type: IssueType) -> None:
        """These concern one row. A rule from them would rewrite everyone's data."""
        assert not is_generalisable(_issue(issue_type), "approve")

    @pytest.mark.parametrize(
        "issue_type",
        [
            IssueType.AMBIGUOUS_MAPPING,
            IssueType.COMPETING_COLUMNS,
            IssueType.REQUIRED_FIELD_UNMAPPED,
            IssueType.AMBIGUOUS_DATE,
            IssueType.UNSAFE_CLEANUP,
        ],
    )
    def test_structural_decisions_are_candidates(self, issue_type: IssueType) -> None:
        assert is_generalisable(_issue(issue_type), "approve")

    @pytest.mark.parametrize("action", ["reject", "exclude"])
    def test_a_refusal_teaches_nothing_whatever_the_question(self, action: str) -> None:
        assert not is_generalisable(_issue(IssueType.AMBIGUOUS_MAPPING), action)


class TestVerifier:
    """The half that runs after, judging what came back."""

    def test_a_sound_header_rule_is_accepted(self) -> None:
        rule, _ = _verified_rule(
            _draft(kind="header_alias", header="Cost Centre Ref", field_name="department"),
            SCHEMA,
        )
        assert rule is not None
        assert rule.kind is RuleKind.HEADER_ALIAS
        assert rule.field_name == "department"
        # Learned, not handwritten: provenance is not cosmetic, it decides how the
        # rule is presented and whether it can be silently trusted.
        assert rule.origin is RuleOrigin.LEARNED

    def test_generalises_false_is_honoured(self) -> None:
        draft = _draft(
            generalises=False, kind="header_alias", header="Ref", field_name="department"
        )
        assert _verified_rule(draft, SCHEMA)[0] is None

    def test_an_unknown_field_is_refused(self) -> None:
        draft = _draft(kind="header_alias", header="Ref", field_name="notAField")
        assert _verified_rule(draft, SCHEMA)[0] is None

    def test_an_ambiguous_header_is_refused(self) -> None:
        """The one refusal that matters most.

        "Date" is claimed by both startDate and endDate, which is what makes a bare
        Date column escalate. A rule resolving it would remove that escalation for
        every future run, and every row in those files would be silently misdated.
        """
        for header in ("Date", "dates", "Effective Date", "Contract Date"):
            draft = _draft(kind="header_alias", header=header, field_name="startDate")
            assert _verified_rule(draft, SCHEMA)[0] is None, header

    def test_a_value_outside_the_vocabulary_is_refused(self) -> None:
        draft = _draft(
            kind="value_alias",
            field_name="employmentType",
            value="Seasonal Temp",
            canonical="seasonal",  # not a member
        )
        assert _verified_rule(draft, SCHEMA)[0] is None

    def test_a_value_inside_the_vocabulary_is_accepted(self) -> None:
        rule, _ = _verified_rule(
            _draft(
                kind="value_alias",
                field_name="employmentType",
                value="Seasonal Temp",
                canonical="contract",
            ),
            SCHEMA,
        )
        assert rule is not None
        assert rule.canonical == "contract"

    def test_a_value_rule_on_a_non_enum_field_is_refused(self) -> None:
        draft = _draft(kind="value_alias", field_name="fullName", value="priya", canonical="Priya")
        assert _verified_rule(draft, SCHEMA)[0] is None

    def test_an_override_cannot_be_inferred(self) -> None:
        """Disabling a shipped rule is a person's disagreement, never an inference.

        Guaranteed twice over: the draft schema has no field naming a rule to
        disable, so the model cannot express one, and the kind is refused even if
        it names it.
        """
        assert "targets_rule_id" not in ProposedRuleDraft.model_fields
        assert _verified_rule(_draft(kind="override"), SCHEMA)[0] is None

    def test_an_unknown_kind_is_refused(self) -> None:
        assert _verified_rule(_draft(kind="rewrite_everything"), SCHEMA)[0] is None

    @pytest.mark.parametrize("order", ["", "dd/mm", "whatever"])
    def test_a_date_rule_needs_a_real_reading(self, order: str) -> None:
        draft = _draft(kind="date_order", header="doj", date_order=order)
        assert _verified_rule(draft, SCHEMA)[0] is None

    def test_a_date_rule_with_a_real_reading_is_accepted(self) -> None:
        rule, _ = _verified_rule(
            _draft(kind="date_order", header="doj", date_order="day_first"), SCHEMA
        )
        assert rule is not None
        assert rule.date_order is not None

    def test_an_incomplete_draft_is_refused(self) -> None:
        """The rule model's own shape validators are the last gate."""
        assert _verified_rule(_draft(kind="header_alias", header="Ref"), SCHEMA)[0] is None
        assert _verified_rule(_draft(kind="column_ignore"), SCHEMA)[0] is None


class TestRefusalsAreExplained:
    """A refused draft must say why, because a spent request has to be accounted for.

    The trail previously showed the model being asked about a rule and then showed
    nothing at all — no rule, no reason — and the only honest reading of that was
    that something had broken. The reviewer does not have to adjudicate the model's
    mistake, but they are entitled to know a request produced nothing and why.
    """

    def test_every_refusal_carries_a_reason(self) -> None:
        refusals = [
            _draft(generalises=False),
            _draft(kind="rewrite_everything"),
            _draft(kind="header_alias", header="Date", field_name="startDate"),
            _draft(kind="header_alias", header="Ref", field_name="notAField"),
            _draft(kind="header_alias", header="Ref"),
            _draft(kind="date_order", header="doj", date_order="sideways"),
            _draft(
                kind="value_alias",
                field_name="employmentType",
                value="x",
                canonical="seasonal",
            ),
        ]
        for draft in refusals:
            rule, reason = _verified_rule(draft, SCHEMA)
            assert rule is None, draft
            assert reason, f"refused with no reason: {draft}"

    def test_an_accepted_draft_carries_no_reason(self) -> None:
        rule, reason = _verified_rule(
            _draft(kind="header_alias", header="Cost Centre Ref", field_name="department"),
            SCHEMA,
        )
        assert rule is not None
        assert reason is None


class TestAmbiguousHeadersCostNothing:
    """A decision no rule could capture must not reach the model at all.

    Resolving a header two fields claim is the case: the verifier would refuse any
    draft from it, so asking spends a request that cannot produce anything. On a real
    run this showed as a request made and no rule to show for it.
    """

    def test_an_ambiguous_header_decision_is_filtered_before_the_model(self) -> None:
        issue = _issue(IssueType.AMBIGUOUS_MAPPING, column_id="f0:c3")
        assert not is_generalisable(issue, "approve", schema=SCHEMA, column_header="Date")

    def test_an_unambiguous_header_decision_still_reaches_the_model(self) -> None:
        issue = _issue(IssueType.AMBIGUOUS_MAPPING, column_id="f0:c5")
        assert is_generalisable(issue, "approve", schema=SCHEMA, column_header="Cost Centre Ref")

    def test_without_a_header_the_filter_does_not_guess(self) -> None:
        """A decision with no column is judged on its type alone, as before."""
        issue = _issue(IssueType.AMBIGUOUS_MAPPING)
        assert is_generalisable(issue, "approve", schema=SCHEMA, column_header="")


class TestDraftShape:
    def test_a_draft_cannot_carry_an_expression(self) -> None:
        """The model has no way to express a pattern, which is the safety argument."""
        forbidden = {"pattern", "regex", "expression", "predicate", "code", "script"}
        assert forbidden.isdisjoint(ProposedRuleDraft.model_fields)

    def test_unknown_keys_are_refused(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ProposedRuleDraft.model_validate(
                {"generalises": True, "kind": "header_alias", "confidence": 0.9}
            )
