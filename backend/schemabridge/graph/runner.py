"""Driving the workflow from a request.

One `advance` call runs the graph until it either finishes or pauses for a human.
Each call is bounded and returns a checkpoint, so a long migration progresses
across several requests rather than holding one open past the platform's limit.

The browser drives this loop, which is a real constraint worth stating plainly
rather than hiding: closing the tab pauses scheduling, not persistence. Reopening
the run resumes from the last checkpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.types import Command

from schemabridge.domain.models import RunPhase
from schemabridge.graph.builder import compile_graph
from schemabridge.graph.checkpointer import build_checkpointer


def _config(run_id: str) -> dict[str, Any]:
    """The graph's per-run configuration. `thread_id` is the run itself."""
    return {"configurable": {"thread_id": run_id}}


@dataclass(frozen=True, slots=True)
class AdvanceResult:
    """Where the run stands after one step."""

    phase: RunPhase
    paused: bool
    #: Escalation payloads awaiting a decision, if paused.
    pending: tuple[dict[str, Any], ...]
    state: dict[str, Any]
    #: Whether another advance would make progress.
    runnable: bool


def _graph() -> Any:
    return compile_graph(build_checkpointer())


def _pending_from(result: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Escalations the graph is waiting on."""
    payloads: list[dict[str, Any]] = []
    for pending in result.get("__interrupt__", ()) or ():
        value = getattr(pending, "value", None)
        if isinstance(value, dict):
            payloads.extend(value.get("issues", []))
    return tuple(payloads)


def _runnable(phase: RunPhase, paused: bool, state: dict[str, Any]) -> bool:
    """Whether calling advance again would achieve anything.

    A scheduled retry counts as work: the run is not finished, it is waiting.
    Reporting it as complete would leave a record permanently undelivered with
    nothing prompting anyone to notice.
    """
    if paused:
        return False
    return phase not in {
        RunPhase.COMPLETE,
        RunPhase.COMPLETE_WITH_FAILURES,
        RunPhase.BLOCKED,
    }


def start(initial_state: dict[str, Any], run_id: str) -> AdvanceResult:
    """Begin a run."""
    graph = _graph()
    result = graph.invoke(initial_state, _config(run_id))
    return _describe(graph, run_id, result)


def advance(run_id: str) -> AdvanceResult:
    """Continue a run that has work left, such as a scheduled retry."""
    graph = _graph()
    result = graph.invoke(None, _config(run_id))
    return _describe(graph, run_id, result)


def resolve(run_id: str, decisions: dict[str, Any]) -> AdvanceResult:
    """Supply the reviewer's decisions and carry on."""
    graph = _graph()
    result = graph.invoke(Command(resume=decisions), _config(run_id))
    return _describe(graph, run_id, result)


def read_state(run_id: str) -> dict[str, Any] | None:
    """The current state, without advancing anything.

    Used by polling, so it must never mutate: a GET that changes state would
    make the UI's refresh loop an accidental actor in the migration.
    """
    snapshot = _graph().get_state(_config(run_id))
    if not snapshot.values:
        return None
    values: dict[str, Any] = dict(snapshot.values)
    values["_paused"] = bool(snapshot.next)
    values["_pending"] = tuple(
        issue
        for task in snapshot.tasks
        for pending in task.interrupts
        if isinstance(getattr(pending, "value", None), dict)
        for issue in pending.value.get("issues", [])
    )
    return values


def _describe(graph: Any, run_id: str, result: dict[str, Any]) -> AdvanceResult:
    snapshot = graph.get_state(_config(run_id))
    state = dict(snapshot.values) if snapshot.values else dict(result)
    paused = bool(snapshot.next)
    phase = state.get("phase", RunPhase.INGESTED)
    if not isinstance(phase, RunPhase):
        phase = RunPhase(str(phase))
    pending = _pending_from(result)
    if paused and not pending:
        pending = tuple(
            issue
            for task in snapshot.tasks
            for interrupt in task.interrupts
            if isinstance(getattr(interrupt, "value", None), dict)
            for issue in interrupt.value.get("issues", [])
        )
    return AdvanceResult(
        phase=phase,
        paused=paused,
        pending=pending,
        state=state,
        runnable=_runnable(phase, paused, state),
    )
