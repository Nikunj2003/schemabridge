"""Model assistance: advisory, bounded, and safe when the provider is slow."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from schemabridge.agent import tools as tools_module
from schemabridge.agent.config import default_max_tokens, is_reasoning_model
from schemabridge.agent.schemas import MappingProposal, ProposedMapping
from schemabridge.agent.tools import CheckedMapping, describe_columns
from schemabridge.domain.models import ColumnProfile, SourceColumn
from schemabridge.domain.normalize import detect_value_kinds, normalize_header
from schemabridge.domain.target import BUILTIN_SCHEMA


def check_proposed_mapping(
    source_column: SourceColumn,
    column_profile: ColumnProfile | None,
    target: str,
    already_taken: set[str],
) -> CheckedMapping:
    """Check against the built-in template, which these gate cases are about."""
    return tools_module.check_proposed_mapping(
        source_column, column_profile, target, already_taken, schema=BUILTIN_SCHEMA
    )


def describe_target_schema(**kwargs: Any) -> str:
    return tools_module.describe_target_schema(BUILTIN_SCHEMA, **kwargs)


def column(column_id: str, header: str, index: int = 0) -> SourceColumn:
    return SourceColumn(
        id=column_id,
        file_id="f1",
        file_name="f1.csv",
        header=header,
        normalized_header=normalize_header(header),
        index=index,
    )


def profile(column_id: str, header: str, samples: list[str]) -> ColumnProfile:
    return ColumnProfile(
        column_id=column_id,
        header=header,
        file_name="f1.csv",
        total_count=len(samples),
        non_empty_count=len(samples),
        distinct_count=len(set(samples)),
        unique_ratio=1.0,
        detected_kinds=tuple(detect_value_kinds(samples)),
        samples=tuple(samples),
    )


class TestModelFamilyCompatibility:
    """One adapter has to serve both configured model families."""

    @pytest.mark.parametrize(
        "model_id",
        [
            "openai/gpt-oss-20b",
            "nvidia/nemotron-3.5-lightning-30b-a3b",
            "deepseek-ai/deepseek-v4-flash",
        ],
    )
    def test_reasoning_models_get_output_headroom(self, model_id: str) -> None:
        # Measured: at 300 output tokens gpt-oss returned only its reasoning and
        # no answer at all, so a reasoning model needs room to finish thinking.
        assert is_reasoning_model(model_id)
        assert default_max_tokens(model_id) >= 1500

    def test_direct_models_do_not_reserve_reasoning_room(self) -> None:
        assert not is_reasoning_model("meta/llama-3.1-70b-instruct")
        assert default_max_tokens("meta/llama-3.1-70b-instruct") < 1500


class TestModelConfigurationHasOneHome:
    """Every LLM-facing value comes from `agent.config`, and nowhere else.

    The point of collecting them was that a parameter defined twice drifts: the
    prompt tells the model one policy while the verifier enforces another, or a
    ceiling is raised in one call site and not the other. A test is the only thing
    that keeps a copy from reappearing, since a duplicate is invisible until it
    disagrees.
    """

    def test_the_client_sends_what_the_config_declares(self) -> None:
        from schemabridge.agent import config, llm

        # Read through the client's own import, so a call site that reintroduced a
        # literal would fail here rather than passing by coincidence.
        assert llm.default_max_tokens is config.default_max_tokens
        assert llm.is_reasoning_model is config.is_reasoning_model
        # Mapping a column is not a creative task, and a retrying client turns one
        # budgeted request into three upstream calls.
        assert config.TEMPERATURE == 0.0
        assert config.MAX_RETRIES == 0

    def test_no_module_keeps_its_own_prompt(self) -> None:
        from pathlib import Path

        agent_dir = Path(config_module_file()).parent
        for module in sorted(agent_dir.glob("*.py")):
            if module.name == "config.py":
                continue
            source = module.read_text(encoding="utf-8")
            assert "_INSTRUCTIONS = " not in source, (
                f"{module.name} defines a prompt of its own; prompts belong in config.py "
                f"next to the policy they encode."
            )

    def test_both_prompts_state_that_file_content_is_untrusted(self) -> None:
        """The instruction that pairs with `agent.sanitize`.

        Scrubbing removes a value's structural power; this sentence is what tells
        the model to read what survives as data. Losing either half quietly weakens
        the other, so both prompts are checked rather than trusted.
        """
        from schemabridge.agent import config

        for prompt in (config.MAPPING_INSTRUCTIONS, config.RULE_INDUCTION_INSTRUCTIONS):
            assert "untrusted file" in prompt
            assert "is a value, not a request" in prompt


def config_module_file() -> str:
    from schemabridge.agent import config

    assert config.__file__
    return config.__file__


class TestVerificationGate:
    """The model proposes; deterministic checks decide."""

    def test_accepts_a_suggestion_the_evidence_supports(self) -> None:
        verdict = check_proposed_mapping(
            column("c1", "Exit Date"),
            profile("c1", "Exit Date", ["2026-08-31", "2026-09-15"]),
            "endDate",
            already_taken=set(),
        )
        assert verdict.accepted
        assert verdict.evidence

    def test_rejects_a_field_that_does_not_exist(self) -> None:
        verdict = check_proposed_mapping(
            column("c1", "Cost Centre"),
            profile("c1", "Cost Centre", ["CC-1"]),
            "costCentre",
            already_taken=set(),
        )
        assert not verdict.accepted
        assert "not a field" in verdict.evidence[0]

    def test_rejects_a_target_another_column_already_supplies(self) -> None:
        verdict = check_proposed_mapping(
            column("c1", "Cost Centre Ref"),
            profile("c1", "Cost Centre Ref", ["CC-4410"]),
            "employeeId",
            already_taken={"employeeId"},
        )
        assert not verdict.accepted
        assert "already supplied" in verdict.evidence[0]

    def test_rejects_a_suggestion_the_values_contradict(self) -> None:
        # Emails are not a start date, whatever the model says.
        verdict = check_proposed_mapping(
            column("c1", "Contact"),
            profile("c1", "Contact", ["a@b.com", "c@d.com"]),
            "startDate",
            already_taken=set(),
        )
        assert not verdict.accepted
        assert "not compatible" in verdict.evidence[0]

    def test_model_confidence_plays_no_part(self) -> None:
        """There is nowhere for the model to assert confidence.

        The schema has no score field, so a proposal cannot argue its way past
        the checks — it is accepted on evidence or not at all.
        """
        assert (
            "confidence"
            not in MappingProposal.model_json_schema()["$defs"]["ProposedMapping"]["properties"]
        )


class TestPromptBoundaries:
    def test_the_model_sees_a_summary_not_the_dataset(self) -> None:
        described = describe_columns(
            [column("c1", "Staff ID")],
            {"c1": profile("c1", "Staff ID", ["E-1", "E-2", "E-3", "E-4", "E-5", "E-6"])},
        )
        # Capped samples only, never the full column.
        assert described.count("E-") <= 3

    def test_only_real_target_fields_are_offered(self) -> None:
        described = describe_target_schema()
        for name in ("employeeId", "fullName", "workEmail", "startDate"):
            assert name in described
        assert "costCentre" not in described


class TestProposalSchema:
    def test_an_empty_proposal_is_valid(self) -> None:
        """Omitting a column is a legitimate answer, not an error."""
        proposal = MappingProposal()
        assert proposal.mappings == []

    def test_unexpected_fields_are_refused(self) -> None:
        with pytest.raises(ValidationError):
            ProposedMapping.model_validate(
                {"column_id": "c1", "target": "endDate", "reason": "x", "confidence": 0.9}
            )


class TestGracefulDegradation:
    def test_a_provider_failure_does_not_sink_the_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A congested endpoint must degrade, not break.

        Measured in practice: one configured model answered in 1.7s while another
        timed out at 60s. The deterministic mappings have to survive either way.
        """
        from schemabridge.agent import propose

        monkeypatch.setattr(propose, "reserve_model_request", lambda count=1: 1)

        def explode(*_args: Any, **_kwargs: Any) -> Any:
            raise TimeoutError("endpoint congested")

        monkeypatch.setattr(propose, "invoke_structured", explode)

        outcome = propose.propose_unresolved_mappings(
            [column("c1", "Cost Centre Ref")],
            {"c1": profile("c1", "Cost Centre Ref", ["CC-4410"])},
            ["c1"],
            set(),
            schema=BUILTIN_SCHEMA,
        )
        assert outcome.accepted == ()
        assert outcome.unavailable_reason is not None
        # The reviewer is told why, rather than shown a silent absence.
        assert "TimeoutError" in outcome.unavailable_reason
        assert outcome.requests_used == 1

    def test_an_exhausted_budget_spends_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from schemabridge.agent import propose
        from schemabridge.server.budget import BudgetExhaustedError

        def refuse(count: int = 1) -> int:
            raise BudgetExhaustedError("daily limit spent")

        monkeypatch.setattr(propose, "reserve_model_request", refuse)
        called = False

        def should_not_run(*_args: Any, **_kwargs: Any) -> Any:
            nonlocal called
            called = True
            raise AssertionError("no request should be made once the budget is spent")

        monkeypatch.setattr(propose, "invoke_structured", should_not_run)

        outcome = propose.propose_unresolved_mappings(
            [column("c1", "Cost Centre Ref")],
            {"c1": profile("c1", "Cost Centre Ref", ["CC-4410"])},
            ["c1"],
            set(),
            schema=BUILTIN_SCHEMA,
        )
        assert not called
        assert outcome.requests_used == 0
        assert outcome.unavailable_reason is not None

    def test_nothing_unresolved_means_no_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A clean upload must not spend any of the shared allowance."""
        from schemabridge.agent import propose

        def should_not_run(count: int = 1) -> int:
            raise AssertionError("budget must not be touched when there is nothing to ask")

        monkeypatch.setattr(propose, "reserve_model_request", should_not_run)
        outcome = propose.propose_unresolved_mappings([], {}, [], set(), schema=BUILTIN_SCHEMA)
        assert outcome.requests_used == 0
        assert outcome.unavailable_reason is None
