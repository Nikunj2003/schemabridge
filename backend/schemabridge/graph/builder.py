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


def route_after_delivery(state: MigrationState) -> Literal["deliver", "__end__"]:
    """Keep going while a retry is outstanding.

    A transient failure schedules another attempt, and the run is not finished
    until that has happened. Ending here would leave the record permanently
    undelivered with nothing prompting anyone to notice — the failure would look
    like completion.

    The retry budget is enforced per record in the delivery node, so this cannot
    spin: once every record has either succeeded, failed for good, or exhausted
    its attempts, nothing is left in `RETRY_WAIT` and the run ends.
    """
    waiting = any(
        intent.state is DeliveryState.RETRY_WAIT for intent in state.get("deliveries", ())
    )
    return "deliver" if waiting else "__end__"


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
    graph.add_node("deliver", deliver)

    graph.add_edge(START, "propose_mappings")
    graph.add_edge("propose_mappings", "assist_with_model")
    graph.add_edge("assist_with_model", "reconcile")
    graph.add_edge("reconcile", "clean_and_validate")

    graph.add_conditional_edges("clean_and_validate", route_after_validation)
    graph.add_conditional_edges("await_review", route_after_review)

    # A correction changes the mapping, so the affected rows are reconciled and
    # revalidated rather than trusted as-is.
    graph.add_edge("apply_resolutions", "reconcile")
    graph.add_conditional_edges(
        "deliver",
        route_after_delivery,
        {
            "deliver": "deliver",
            "__end__": END,
        },
    )

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
