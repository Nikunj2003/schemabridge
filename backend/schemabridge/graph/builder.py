"""Assembly of the migration workflow.

The shape encodes the autonomy boundary: work flows straight through when the
evidence is clear, and diverts to `await_review` only where a decision genuinely
needs a person. Reaching `ready` continues to delivery on its own — there is no
second "now push it" gate, because approving work the engine already judged safe
is the micromanagement the design is trying to avoid.
"""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from schemabridge.domain.models import DeliveryState, IssueStatus
from schemabridge.graph.nodes import (
    apply_resolutions,
    assist_with_model,
    await_review,
    clean_and_validate,
    deliver,
    induce_rules,
    propose_mappings,
    reconcile,
)
from schemabridge.graph.state import MigrationState


def route_after_validation(
    state: MigrationState,
) -> Literal["await_review", "deliver"]:
    """Send anything genuinely uncertain to a human; otherwise carry on."""
    blocking = any(
        issue.blocking and issue.status is IssueStatus.OPEN for issue in state.get("issues", ())
    )
    return "await_review" if blocking else "deliver"


def route_after_delivery(state: MigrationState) -> Literal["deliver", "induce_rules", "__end__"]:
    """Keep going while a retry is outstanding, then learn from what happened.

    A transient failure schedules another attempt, and the run is not finished
    until that has happened. Ending here would leave the record permanently
    undelivered with nothing prompting anyone to notice — the failure would look
    like completion.

    The retry budget is enforced per record in the delivery node, so this cannot
    spin: once every record has either succeeded, failed for good, or exhausted
    its attempts, nothing is left in `RETRY_WAIT` and the run ends.

    Rule drafting happens here, at the very end, and only when the reviewer
    actually decided something. Putting it anywhere earlier — in particular
    between a correction and the work that depends on it — makes a person wait for
    speculative work about their *next* migration while they are still doing this
    one. The proposals are shown on the results page either way, so nothing is lost
    by deferring them, and the decision they came from is already applied.
    """
    waiting = any(
        intent.state is DeliveryState.RETRY_WAIT for intent in state.get("deliveries", ())
    )
    if waiting:
        return "deliver"
    resolutions = state.get("resolutions", {})
    already = set(state.get("induced_for", ()))
    return "induce_rules" if resolutions and set(resolutions) - already else "__end__"


def route_after_review(
    state: MigrationState,
) -> Literal["apply_resolutions", "deliver"]:
    """A resolution that changes a mapping has to be re-applied and revalidated."""
    return "apply_resolutions" if state.get("resolutions") else "deliver"


def build_graph() -> StateGraph[MigrationState, None, MigrationState, MigrationState]:
    """Wire the nodes together. Compilation needs a checkpointer supplied."""
    graph: StateGraph[MigrationState, None, MigrationState, MigrationState] = StateGraph(
        MigrationState
    )

    graph.add_node("propose_mappings", propose_mappings)
    graph.add_node("assist_with_model", assist_with_model)
    graph.add_node("reconcile", reconcile)
    graph.add_node("clean_and_validate", clean_and_validate)
    graph.add_node("await_review", await_review)
    graph.add_node("apply_resolutions", apply_resolutions)
    graph.add_node("induce_rules", induce_rules)
    graph.add_node("deliver", deliver)

    graph.add_edge(START, "propose_mappings")
    graph.add_edge("propose_mappings", "assist_with_model")
    graph.add_edge("assist_with_model", "reconcile")
    graph.add_edge("reconcile", "clean_and_validate")

    graph.add_conditional_edges("clean_and_validate", route_after_validation)
    graph.add_conditional_edges("await_review", route_after_review)

    # A correction changes the mapping, so the affected rows are reconciled and
    # revalidated rather than trusted as-is. Nothing speculative comes between the
    # two: the reviewer is waiting on this path.
    graph.add_edge("apply_resolutions", "reconcile")
    graph.add_conditional_edges(
        "deliver",
        route_after_delivery,
        {
            "deliver": "deliver",
            "induce_rules": "induce_rules",
            "__end__": END,
        },
    )

    # Learning is the last thing the run does, after every record has been
    # delivered and the person is no longer blocked on it.
    graph.add_edge("induce_rules", END)

    return graph


def compile_graph(
    checkpointer: object | None = None,
) -> CompiledStateGraph[MigrationState, None, MigrationState, MigrationState]:
    """Compile the workflow.

    Without a checkpointer the graph cannot pause: `interrupt()` needs somewhere
    to persist state. Tests pass an in-memory saver; the application passes the
    MongoDB one so a paused run survives the process ending.
    """
    return build_graph().compile(checkpointer=checkpointer)  # type: ignore[arg-type]
