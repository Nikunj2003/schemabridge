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
from typing import Any

from langgraph.types import Command

from schemabridge.domain.models import RunPhase
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


def _config(run_id: str) -> dict[str, Any]:
    """The graph's per-run configuration. `thread_id` is the run itself."""
    return {"configurable": {"thread_id": run_id}}


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


def _graph() -> Any:
    return compile_graph(build_checkpointer())


def _interrupts(snapshot: Any) -> tuple[dict[str, Any], ...]:
    """Escalations the graph is actually waiting on, from the checkpoint."""
    return tuple(
        issue
        for task in snapshot.tasks
        for pending in task.interrupts
        if isinstance(getattr(pending, "value", None), dict)
        for issue in pending.value.get("issues", [])
    )


def _run_bounded(graph: Any, run_id: str, payload: Any, limit: int) -> None:
    """Run at most `limit` supersteps, then leave the rest for the next call.

    Breaking out of the stream stops before the next task is started; the
    checkpoint written by the last completed superstep is what the following call
    resumes from. A limit of zero still submits the input, so the initial state is
    persisted without executing a node.
    """
    stream = graph.stream(payload, _config(run_id), stream_mode="updates")
    if limit <= 0:
        # Nothing to execute, but the input must still be checkpointed. Closing
        # the generator without consuming it would discard the state entirely.
        graph.update_state(_config(run_id), payload) if payload is not None else None
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


def start(initial_state: dict[str, Any], run_id: str) -> AdvanceResult:
    """Accept a run: persist the parsed sources, execute nothing yet."""
    graph = _graph()
    _run_bounded(graph, run_id, initial_state, _STEPS_ON_CREATE)
    return _describe(graph, run_id)


def advance(run_id: str) -> AdvanceResult:
    """Do the next bounded piece of work."""
    graph = _graph()
    _run_bounded(graph, run_id, None, _STEPS_PER_CALL)
    return _describe(graph, run_id)


def resolve(run_id: str, decisions: dict[str, Any]) -> AdvanceResult:
    """Supply the reviewer's decisions and carry on, still bounded."""
    graph = _graph()
    _run_bounded(graph, run_id, Command(resume=decisions), _STEPS_PER_CALL)
    return _describe(graph, run_id)


def read_state(run_id: str) -> dict[str, Any] | None:
    """The current state, without advancing anything.

    Used by polling, so it must never mutate: a GET that changes state would
    make the UI's refresh loop an accidental actor in the migration.
    """
    snapshot = _graph().get_state(_config(run_id))
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
