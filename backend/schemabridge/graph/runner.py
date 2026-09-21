"""Driving the workflow from a request.

Execution is deliberately **bounded**: one call runs a limited number of graph
supersteps and then stops, leaving a checkpoint behind. The browser calls again
to continue. Three things fall out of that, all of them requirements rather than
conveniences:

* **Creating a run returns immediately.** Parsing the files is enough to accept
  the upload; mapping and delivery happen in later calls. A clean migration used
  to finish inside the create request, so the run screen opened on a completed
  run and the person never saw it work.
* **A long migration cannot outlive the platform's request limit**, because no
  single call tries to run the whole thing.
* **Progress is observable**, since each call commits a checkpoint that the
  independent polling loop can read.

Stopping for scheduling and stopping for a person look the same in `snapshot.next`
— both leave it non-empty. They are told apart by whether any task carries an
`interrupt`, which is the only signal that someone is actually being asked
something. Confusing the two would either show "waiting for you" when nobody was
asked, or report a paused run as finished.

Closing the tab pauses scheduling, not persistence: the state is checkpointed, so
reopening the run continues from where it stopped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from langgraph.types import Command

from schemabridge.domain.models import ResolutionAction, RunPhase
from schemabridge.graph.builder import compile_graph
from schemabridge.graph.checkpointer import build_checkpointer

#: Supersteps per request. Small enough that each call returns quickly and the
#: next poll shows movement; large enough that a run does not need dozens of
#: round trips. Delivery loops one superstep per batch, so this also bounds how
#: much sending happens before the UI hears about it.
_STEPS_PER_CALL = 2

#: Supersteps allowed while accepting an upload. Zero: the files are parsed by
#: the caller, and the first real step belongs to the first advance so the run
#: screen can open before any work has happened.
_STEPS_ON_CREATE = 0


def _config(run_id: str, run_expires_at: datetime | None = None) -> dict[str, Any]:
    """The graph's per-run configuration and immutable persistence deadline."""
    configurable: dict[str, Any] = {"thread_id": run_id}
    if run_expires_at is not None:
        configurable["run_expires_at"] = run_expires_at
    return {"configurable": configurable}


class ReviewNotReadyError(RuntimeError):
    """A decision arrived before the graph reached a review interrupt."""


class InvalidReviewDecisionError(ValueError):
    """A decision does not apply to the checkpoint's pending review payload."""


@dataclass(frozen=True, slots=True)
class AdvanceResult:
    """Where the run stands after one bounded call."""

    phase: RunPhase
    #: True only when a person is genuinely being asked something.
    paused: bool
    #: Escalation payloads awaiting a decision, if paused.
    pending: tuple[dict[str, Any], ...]
    state: dict[str, Any]
    #: Whether calling again would make progress.
    runnable: bool


def _graph(workspace_kind: str = "legacy") -> Any:
    return compile_graph(build_checkpointer(workspace_kind))


def _interrupts(snapshot: Any) -> tuple[dict[str, Any], ...]:
    """Escalations the graph is actually waiting on, from the checkpoint."""
    return tuple(
        issue
        for task in snapshot.tasks
        for pending in task.interrupts
        if isinstance(getattr(pending, "value", None), dict)
        for issue in pending.value.get("issues", [])
    )


def _validate_pending_decisions(snapshot: Any, decisions: dict[str, Any]) -> None:
    """Refuse resume data unless this exact checkpoint is asking for it.

    LangGraph accepts a resume command before an ``interrupt()`` has been reached,
    then clears it when ordinary work completes. That looks like a successful save
    to the browser but loses the decision. The interrupt payload is therefore the
    authority for both readiness and which issue ids may be answered.
    """
    pending = {str(issue.get("id", "")): issue for issue in _interrupts(snapshot)}
    if not pending:
        raise ReviewNotReadyError("The migration is still preparing the next review question.")

    unknown = set(decisions) - set(pending)
    if unknown:
        raise InvalidReviewDecisionError("One or more decisions are no longer awaiting review.")

    actions = {action.value for action in ResolutionAction}
    for issue_id, choice in decisions.items():
        if not isinstance(choice, dict):
            raise InvalidReviewDecisionError("Each review decision must be an object.")
        action = choice.get("action", ResolutionAction.APPROVE.value)
        if action not in actions:
            raise InvalidReviewDecisionError("A review decision named an unknown action.")
        options = {str(option.get("id", "")) for option in pending[issue_id].get("options", [])}
        option_id = choice.get("option_id")
        if option_id is not None and option_id not in options:
            raise InvalidReviewDecisionError("A review decision selected an unavailable option.")


def _run_bounded(
    graph: Any, run_id: str, payload: Any, limit: int, run_expires_at: datetime | None = None
) -> None:
    """Run at most `limit` supersteps, then leave the rest for the next call.

    Breaking out of the stream stops before the next task is started; the
    checkpoint written by the last completed superstep is what the following call
    resumes from. A limit of zero still submits the input, so the initial state is
    persisted without executing a node.
    """
    config = _config(run_id, run_expires_at)
    stream = graph.stream(payload, config, stream_mode="updates")
    if limit <= 0:
        # Nothing to execute, but the input must still be checkpointed. Closing
        # the generator without consuming it would discard the state entirely.
        graph.update_state(config, payload) if payload is not None else None
        stream.close()
        return

    completed = 0
    try:
        for _ in stream:
            completed += 1
            if completed >= limit:
                break
    finally:
        stream.close()


def start(
    initial_state: dict[str, Any],
    run_id: str,
    workspace_kind: str = "legacy",
    run_expires_at: datetime | None = None,
) -> AdvanceResult:
    """Accept a run: persist the parsed sources, execute nothing yet."""
    graph = _graph(workspace_kind)
    _run_bounded(graph, run_id, initial_state, _STEPS_ON_CREATE, run_expires_at)
    return _describe(graph, run_id)


def advance(
    run_id: str, workspace_kind: str = "legacy", run_expires_at: datetime | None = None
) -> AdvanceResult:
    """Do the next bounded piece of work."""
    graph = _graph(workspace_kind)
    _run_bounded(graph, run_id, None, _STEPS_PER_CALL, run_expires_at)
    return _describe(graph, run_id)


def resolve(
    run_id: str,
    decisions: dict[str, Any],
    workspace_kind: str = "legacy",
    run_expires_at: datetime | None = None,
) -> AdvanceResult:
    """Supply decisions only to the interrupt that is currently pending."""
    graph = _graph(workspace_kind)
    config = _config(run_id, run_expires_at)
    _validate_pending_decisions(graph.get_state(config), decisions)
    _run_bounded(graph, run_id, Command(resume=decisions), _STEPS_PER_CALL, run_expires_at)
    return _describe(graph, run_id)


def read_state(run_id: str, workspace_kind: str = "legacy") -> dict[str, Any] | None:
    """The current state, without advancing anything.

    Used by polling, so it must never mutate: a GET that changes state would
    make the UI's refresh loop an accidental actor in the migration.
    """
    snapshot = _graph(workspace_kind).get_state(_config(run_id))
    if not snapshot.values:
        return None
    pending = _interrupts(snapshot)
    values: dict[str, Any] = dict(snapshot.values)
    # Paused means "a person is being asked", not merely "more work remains".
    values["_paused"] = bool(pending)
    values["_pending"] = pending
    values["_runnable"] = bool(snapshot.next) and not pending
    return values


def _describe(graph: Any, run_id: str) -> AdvanceResult:
    """Read the committed checkpoint, rather than trusting the stream's output."""
    snapshot = graph.get_state(_config(run_id))
    state = dict(snapshot.values) if snapshot.values else {}
    pending = _interrupts(snapshot)
    paused = bool(pending)

    phase = state.get("phase", RunPhase.INGESTED)
    if not isinstance(phase, RunPhase):
        phase = RunPhase(str(phase))

    return AdvanceResult(
        phase=phase,
        paused=paused,
        pending=pending,
        # More work exists whenever the graph has a next task and nobody is being
        # asked anything. A terminal phase with no next task is genuinely done.
        runnable=bool(snapshot.next) and not paused,
        state=state,
    )
