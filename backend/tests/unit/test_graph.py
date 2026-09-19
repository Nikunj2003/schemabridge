"""The workflow: automatic where evidence is clear, paused where it is not."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from schemabridge.domain.models import (
    ColumnProfile,
    Disposition,
    EventExecutionBasis,
    IssueStatus,
    MappingOutcome,
    RunPhase,
    SourceColumn,
    SourceFile,
    SourceRow,
)
from schemabridge.domain.target import BUILTIN_SCHEMA
from schemabridge.graph.builder import compile_graph
from schemabridge.graph.state import MigrationState
from schemabridge.ingest.csv_source import parse_csv
from schemabridge.ingest.profile import profile_columns
from schemabridge.ingest.xlsx_source import parse_xlsx

SAMPLES = Path(__file__).resolve().parents[2] / "fixtures" / "samples"


def initial_state(names: list[str]) -> dict[str, Any]:
    """Build the starting state from sample files, as ingestion will."""
    files: list[SourceFile] = []
    columns: list[SourceColumn] = []
    rows: list[SourceRow] = []
    profiles: list[ColumnProfile] = []
    for index, name in enumerate(names):
        file_id = f"f{index}"
        path = SAMPLES / name
        if name.endswith(".xlsx"):
            parsed = parse_xlsx(file_id, name, path.read_bytes())
        else:
            parsed = parse_csv(file_id, name, path.read_text(encoding="utf-8"))
        assert parsed.ok, parsed.error
        files.append(parsed.file)
        columns.extend(parsed.file.columns)
        rows.extend(parsed.rows)
        profiles.extend(profile_columns(parsed.file, parsed.rows))

    return {
        "run_id": "run-test",
        "owner_session_id": "session-test",
        "files": tuple(files),
        "columns": tuple(columns),
        "rows": tuple(rows),
        "profiles": tuple(profiles),
        "mappings": (),
        "events": (),
        "records": (),
        "issues": (),
        "deliveries": (),
        "resolutions": {},
        "model_requests": 0,
        "phase": RunPhase.INGESTED,
        # The contract this run maps onto, snapshotted exactly as the API does.
        "target_schema": BUILTIN_SCHEMA,
    }


@pytest.fixture
def graph(monkeypatch: pytest.MonkeyPatch) -> Any:
    """The workflow with delivery stubbed at the HTTP boundary.

    These tests are about the graph's routing and escalation behaviour, so the
    network is replaced by an in-process double. Delivery itself — idempotency,
    retries, lost responses — is covered against a real server in
    `tests/integration/test_delivery.py`, where it belongs.
    """
    from schemabridge.domain.models import DeliveryOutcome, DeliveryState
    from schemabridge.graph import nodes
    from schemabridge.server.target_client import DeliveryResult

    class _NoNetwork:
        def __enter__(self) -> _NoNetwork:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    def accept_everything(
        _client: object,
        _run_id: str,
        record: Any,
        **_kwargs: Any,
    ) -> DeliveryResult:
        return DeliveryResult(
            outcome=DeliveryOutcome.SUCCEEDED,
            state=DeliveryState.SUCCEEDED,
            status_code=201,
            detail="Accepted by the destination.",
            target_id=f"DEST-{record.id[-6:].upper()}",
        )

    monkeypatch.setattr(nodes, "build_client", lambda: _NoNetwork())
    monkeypatch.setattr(nodes, "deliver_record", accept_everything)
    return compile_graph(InMemorySaver())


class TestCleanRunNeedsNoHuman:
    def test_completes_without_pausing(self, graph: Any) -> None:
        config = {"configurable": {"thread_id": "clean-1"}}
        result = graph.invoke(initial_state(["employees-clean.csv"]), config)

        assert "__interrupt__" not in result
        # Reaching the end means delivery ran on its own: no second approval.
        assert result["phase"] is RunPhase.COMPLETE
        assert all(r.disposition is Disposition.DELIVERED for r in result["records"])
        assert result["issues"] == ()
        assert len(result["deliveries"]) == len(result["records"])

    def test_records_what_it_did(self, graph: Any) -> None:
        config = {"configurable": {"thread_id": "clean-2"}}
        result = graph.invoke(initial_state(["employees-clean.csv"]), config)

        actions = [e.action for e in result["events"]]
        assert "mapping_applied" in actions
        assert "records_reconciled" in actions
        assert "validation_summary" in actions
        assert "delivery_succeeded" in actions
        # Sequence numbers are the UI's polling cursor, so they must be unique.
        seqs = [e.seq for e in result["events"]]
        assert len(seqs) == len(set(seqs))
        # An agent actor does not imply model use: this run followed policy only.
        assert {e.execution_basis for e in result["events"]} == {EventExecutionBasis.DETERMINISTIC}

    def _assist(self, monkeypatch: pytest.MonkeyPatch, outcome: Any) -> tuple[Any, ...]:
        """Run the model-assistance node against a fixed proposal outcome."""
        from schemabridge.graph import nodes

        state = initial_state(["employees-clean.csv"])
        state["unresolved_columns"] = (state["columns"][0].id,)
        monkeypatch.setattr(nodes, "propose_unresolved_mappings", lambda *_a, **_k: outcome)
        result = nodes.assist_with_model(cast(MigrationState, state))
        return tuple(result["events"])

    def test_model_assistance_records_its_own_execution_basis(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from schemabridge.agent.propose import AcceptedMapping, ProposalOutcome

        state = initial_state(["employees-clean.csv"])
        column_id = state["columns"][0].id
        events = self._assist(
            monkeypatch,
            ProposalOutcome(
                accepted=(
                    AcceptedMapping(
                        column_id=column_id,
                        target="employeeId",
                        evidence=("Verified model suggestion.",),
                    ),
                ),
                requests_used=1,
                considered=(column_id,),
            ),
        )

        # The call itself is recorded first, then what it produced, so the trail
        # reads in the order the work actually happened.
        assert [e.action for e in events] == ["model_requested", "mapping_applied"]
        assert [e.seq for e in events] == sorted(e.seq for e in events)
        assert {e.execution_basis for e in events} == {EventExecutionBasis.MODEL_ASSISTED}

    def test_a_request_whose_suggestions_were_all_refused_is_still_marked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A model call must never be invisible just because nothing was applied."""
        from schemabridge.agent.propose import ProposalOutcome

        state = initial_state(["employees-clean.csv"])
        column_id = state["columns"][0].id
        events = self._assist(
            monkeypatch,
            ProposalOutcome(
                rejected=((column_id, "The values do not look like that field."),),
                requests_used=1,
                considered=(column_id,),
            ),
        )

        marked = [e for e in events if e.execution_basis is EventExecutionBasis.MODEL_ASSISTED]
        assert [e.action for e in marked] == ["model_requested"]
        # The refusal was the rule engine's, and says whose proposal it refused.
        refusal = next(e for e in events if e.action == "mapping_suggestion_rejected")
        assert refusal.execution_basis is EventExecutionBasis.DETERMINISTIC
        assert "model proposed" in refusal.reason

    def test_no_request_means_no_model_mark(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An exhausted budget never calls out, so nothing may claim it did."""
        from schemabridge.agent.propose import ProposalOutcome

        state = initial_state(["employees-clean.csv"])
        column_id = state["columns"][0].id
        events = self._assist(
            monkeypatch,
            ProposalOutcome(
                requests_used=0,
                unavailable_reason="The daily allowance is spent.",
                considered=(column_id,),
            ),
        )

        assert [e.action for e in events] == ["model_unavailable"]
        assert all(e.execution_basis is EventExecutionBasis.DETERMINISTIC for e in events)


class TestMessyRunPausesForAHuman:
    def test_stops_on_the_ambiguous_column(self, graph: Any) -> None:
        config = {"configurable": {"thread_id": "messy-1"}}
        result = graph.invoke(
            initial_state(["employees-legacy.csv", "employees-hr-export.csv"]), config
        )

        interrupts = result.get("__interrupt__", ())
        assert interrupts, "expected the run to pause for review"

        payload = interrupts[0].value
        assert payload["kind"] == "review_required"
        assert payload["count"] >= 1

        # Every escalation must carry enough context to decide at a glance.
        for issue in payload["issues"]:
            assert issue["reason"]
            assert issue["type"]

    def test_the_paused_state_is_inspectable(self, graph: Any) -> None:
        config = {"configurable": {"thread_id": "messy-2"}}
        graph.invoke(initial_state(["employees-legacy.csv", "employees-hr-export.csv"]), config)

        snapshot = graph.get_state(config)
        assert snapshot.next, "a paused run should name the node it stopped at"
        # Work completed before the pause is preserved, not discarded.
        assert snapshot.values["mappings"]
        assert any(d.outcome is MappingOutcome.AUTO_MAPPED for d in snapshot.values["mappings"])

    def test_resumes_and_finishes_once_resolved(self, graph: Any) -> None:
        config = {"configurable": {"thread_id": "messy-3"}}
        first = graph.invoke(
            initial_state(["employees-legacy.csv", "employees-hr-export.csv"]), config
        )
        interrupts = first.get("__interrupt__", ())
        assert interrupts

        # Resolve every blocking issue the way a reviewer would.
        decisions: dict[str, Any] = {}
        for issue in interrupts[0].value["issues"]:
            options = issue["options"]
            decisions[issue["id"]] = (
                {"action": "correct", "option_id": options[0]["id"]}
                if options
                else {"action": "exclude", "note": "Not migrating this record."}
            )

        resumed = graph.invoke(Command(resume=decisions), config)

        resolved = [i for i in resumed["issues"] if i.status is IssueStatus.RESOLVED]
        assert resolved, "the reviewer's decisions should be recorded on the issues"
        assert any(i.resolution is not None for i in resolved)

        # The decision is attributed to the reviewer, not the agent.
        reviewer_events = [e for e in resumed["events"] if e.actor == "reviewer"]
        assert reviewer_events
        assert {e.execution_basis for e in reviewer_events} == {EventExecutionBasis.HUMAN}

    def test_a_correction_is_revalidated_not_trusted(self, graph: Any) -> None:
        config = {"configurable": {"thread_id": "messy-4"}}
        first = graph.invoke(
            initial_state(["employees-legacy.csv", "employees-hr-export.csv"]), config
        )
        interrupts = first.get("__interrupt__", ())
        assert interrupts

        mapping_issues = [
            i for i in interrupts[0].value["issues"] if i["type"] == "AMBIGUOUS_MAPPING"
        ]
        if not mapping_issues:
            pytest.skip("no mapping ambiguity in this fixture run")

        issue = mapping_issues[0]
        target_option = next(o for o in issue["options"] if o["target"])
        resumed = graph.invoke(
            Command(resume={issue["id"]: {"action": "correct", "option_id": target_option["id"]}}),
            config,
        )

        # Validation ran again after the correction, so every record carries a
        # verdict rather than an assumption.
        assert all(
            r.validation for r in resumed["records"] if r.disposition != Disposition.EXCLUDED
        )


class TestEveryRowIsAccountedFor:
    def test_no_source_row_disappears(self, graph: Any) -> None:
        config = {"configurable": {"thread_id": "accounting-1"}}
        state = initial_state(["employees-legacy.csv", "employees-hr-export.csv"])
        result = graph.invoke(state, config)

        values = result if "records" in result else graph.get_state(config).values
        accounted = sum(len(r.provenance) for r in values["records"])
        assert accounted == len(state["rows"])


class TestResolutionsStick:
    """Nodes after review re-derive their issues on every pass.

    Without care the fresh copy overwrites the resolved one, the issue reopens,
    and the reviewer is asked the same question forever.
    """

    def test_one_pass_of_decisions_clears_the_queue(self, graph: Any) -> None:
        config = {"configurable": {"thread_id": "sticky-1"}}
        first = graph.invoke(
            initial_state(["employees-legacy.csv", "employees-hr-export.csv"]), config
        )
        interrupts = first.get("__interrupt__", ())
        assert interrupts

        decisions: dict[str, Any] = {}
        for issue in interrupts[0].value["issues"]:
            options = issue["options"]
            concrete = next((o for o in options if o.get("value") or o.get("target")), None)
            if concrete:
                decisions[issue["id"]] = {
                    "action": "correct",
                    "option_id": concrete["id"],
                }
            else:
                excluding = next((o for o in options if o["id"].startswith("exclude:")), None)
                decisions[issue["id"]] = {
                    "action": "exclude",
                    "option_id": excluding["id"] if excluding else None,
                    "note": "Cannot be migrated as supplied.",
                }

        resumed = graph.invoke(Command(resume=decisions), config)

        # One round of answers must be enough; nothing may reopen.
        assert not resumed.get("__interrupt__"), "issues reopened after being resolved"
        final = graph.get_state(config).values
        assert all(i.status is IssueStatus.RESOLVED for i in final["issues"])
        # Once nothing is blocking, the run finishes without further prompting.
        assert final["phase"] in {RunPhase.COMPLETE, RunPhase.COMPLETE_WITH_FAILURES}

    def test_excluded_records_are_still_accounted_for(self, graph: Any) -> None:
        config = {"configurable": {"thread_id": "sticky-2"}}
        state = initial_state(["employees-legacy.csv", "employees-hr-export.csv"])
        first = graph.invoke(state, config)

        decisions: dict[str, Any] = {}
        for issue in first.get("__interrupt__", ())[0].value["issues"]:
            options = issue["options"]
            concrete = next((o for o in options if o.get("value") or o.get("target")), None)
            excluding = next((o for o in options if o["id"].startswith("exclude:")), None)
            decisions[issue["id"]] = (
                {"action": "correct", "option_id": concrete["id"]}
                if concrete
                else {"action": "exclude", "option_id": excluding["id"] if excluding else None}
            )
        graph.invoke(Command(resume=decisions), config)

        final = graph.get_state(config).values
        excluded = [r for r in final["records"] if r.disposition is Disposition.EXCLUDED]
        assert excluded, "expected the unrepairable records to be excluded"
        # Excluded is a visible outcome, not a silent drop.
        assert all(r.exclusion_reason for r in excluded)
        assert sum(len(r.provenance) for r in final["records"]) == len(state["rows"])


class TestNoDeadEnds:
    def test_every_blocking_issue_offers_a_way_forward(self, graph: Any) -> None:
        """A reviewer must never be shown a problem with no available action."""
        config = {"configurable": {"thread_id": "deadend-1"}}
        result = graph.invoke(
            initial_state(["employees-legacy.csv", "employees-hr-export.csv"]), config
        )
        for issue in result.get("__interrupt__", ())[0].value["issues"]:
            assert issue["options"], f"{issue['type']} gives the reviewer nothing to do"
