"""Workflow nodes.

Each node is a thin adapter: it pulls what it needs from the state, calls the
pure domain functions, and returns the delta. Keeping the decisions in
`schemabridge.domain` means they stay testable without a graph, a database, or a
model — and it keeps the escalation policy in one place rather than scattered
across orchestration code.

The target schema is one of the things pulled from state. It was snapshotted when
the run was created, so editing a saved schema cannot retroactively change what a
paused migration is being validated against — a run's contract is fixed at the
moment it starts.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from schemabridge.agent.induce import propose_rule_from_decision
from schemabridge.agent.propose import propose_unresolved_mappings
from schemabridge.domain.identity import IncomingRow, reconcile_identities
from schemabridge.domain.mapping import POLICY_VERSION, decide_mappings
from schemabridge.domain.models import (
    Actor,
    AuditEvent,
    CanonicalRecord,
    DeliveryIntent,
    DeliveryState,
    Disposition,
    EventExecutionBasis,
    IssueOption,
    IssueResolution,
    IssueStatus,
    IssueType,
    MappingBasis,
    MappingDecision,
    MappingOutcome,
    Provenance,
    ResolutionAction,
    ReviewIssue,
    RunPhase,
    ValidationError,
)
from schemabridge.domain.rules import ProposedRule
from schemabridge.domain.schema import TargetSchema
from schemabridge.domain.validate import run_validation_passes
from schemabridge.graph.state import (
    MigrationState,
    next_sequence,
    run_rules,
    run_schema,
)
from schemabridge.server.target_client import (
    MAX_ATTEMPTS,
    attempt_record,
    build_client,
    build_payload,
    deliver_record,
    idempotency_key,
    payload_hash,
)


def _label(schema: TargetSchema, name: str | None) -> str:
    """A field's human name, falling back to the raw name."""
    if not name:
        return "this value"
    spec = schema.field(name)
    return spec.label if spec else name


def _subject_of(schema: TargetSchema, record: CanonicalRecord) -> str:
    """How to name a record in the audit trail.

    The schema's naming field rather than its identity field: a detected schema
    declares no identity, and "rec:row-3" is a handle the reviewer cannot find in
    their own file.
    """
    naming = schema.naming_field
    if naming and (value := record.values.get(naming)):
        return value
    return record.id


def _event(
    seq: int,
    action: str,
    reason: str,
    *,
    execution_basis: EventExecutionBasis,
    actor: Actor = Actor.AGENT,
    subject: str | None = None,
    before: str | None = None,
    after: str | None = None,
    **detail: str | int | float | bool | None,
) -> AuditEvent:
    return AuditEvent(
        seq=seq,
        actor=actor,
        execution_basis=execution_basis,
        action=action,
        reason=reason,
        subject=subject,
        before=before,
        after=after,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------


def propose_mappings(state: MigrationState) -> dict[str, Any]:
    """Decide which source column becomes which target field."""
    columns = state.get("columns", ())
    profiles = state.get("profiles", ())
    schema = run_schema(state)
    seq = next_sequence(state)

    rules = run_rules(state)
    result = decide_mappings(columns, profiles, schema=schema, rules=rules)

    events: list[AuditEvent] = []
    for decision in result.decisions:
        column = next((c for c in columns if c.id == decision.column_id), None)
        header = column.header if column else decision.column_id

        # Which rule answered, when one did, so the trail can distinguish a match the
        # engine shipped knowing from one this person taught it. Read back from the
        # overlay rather than from the decision, because the decision records the
        # basis but not the rule's identity — and from the index that actually
        # answered: an excluded column was decided by an ignore rule, and asking the
        # alias index about it would find nothing and silently drop the attribution.
        matched = None
        if decision.basis is MappingBasis.LEARNED_ALIAS:
            matched = (
                rules.ignores(header)
                if decision.outcome is MappingOutcome.EXCLUDED
                else rules.alias_for(header)
            )
        rule_id = matched.rule_id if matched else None
        rule_origin = matched.origin.value if matched else None

        if decision.outcome is MappingOutcome.EXCLUDED:
            events.append(
                _event(
                    seq,
                    "column_skipped",
                    decision.evidence[0] if decision.evidence else "Left out by a rule.",
                    execution_basis=EventExecutionBasis.DETERMINISTIC,
                    subject=header,
                    rule_id=rule_id,
                    rule_origin=rule_origin,
                )
            )
        elif decision.outcome is MappingOutcome.AUTO_MAPPED and decision.target:
            events.append(
                _event(
                    seq,
                    "mapping_applied",
                    decision.evidence[0] if decision.evidence else "Deterministic match.",
                    execution_basis=EventExecutionBasis.DETERMINISTIC,
                    subject=header,
                    after=_label(schema, decision.target),
                    basis=decision.basis.value,
                    rule_id=rule_id,
                    rule_origin=rule_origin,
                )
            )
        else:
            events.append(
                _event(
                    seq,
                    "mapping_escalated",
                    decision.evidence[0] if decision.evidence else "No confident match.",
                    execution_basis=EventExecutionBasis.DETERMINISTIC,
                    subject=header,
                )
            )
        seq += 1

    automatic = sum(1 for d in result.decisions if d.outcome is MappingOutcome.AUTO_MAPPED)
    learned = sum(1 for d in result.decisions if d.basis is MappingBasis.LEARNED_ALIAS)
    events.append(
        _event(
            seq,
            "mapping_summary",
            (
                f"{automatic} of {len(result.decisions)} columns mapped without asking"
                + (f", {learned} of them by a rule you approved." if learned else ".")
            ),
            execution_basis=EventExecutionBasis.DETERMINISTIC,
            automatic=automatic,
            escalated=len(result.decisions) - automatic,
            learned=learned,
        )
    )

    return {
        "mappings": result.decisions,
        "issues": result.issues,
        "unresolved_columns": result.unresolved,
        "events": tuple(events),
        "phase": RunPhase.ANALYZING,
        "policy_version": POLICY_VERSION,
    }


def assist_with_model(state: MigrationState) -> dict[str, Any]:
    """Ask the model about columns the alias tables could not place.

    Runs only when there is something genuinely unfamiliar, so a clean upload
    never spends a request. Whatever comes back is verified before it is applied,
    and failure degrades to review rather than stopping the run.
    """
    unresolved = list(state.get("unresolved_columns", ()))
    if not unresolved:
        return {}

    columns = list(state.get("columns", ()))
    profiles = {profile.column_id: profile for profile in state.get("profiles", ())}
    schema = run_schema(state)
    taken = {
        decision.target
        for decision in state.get("mappings", ())
        if decision.outcome is MappingOutcome.AUTO_MAPPED and decision.target
    }

    outcome = propose_unresolved_mappings(
        columns,
        profiles,
        unresolved,
        taken,
        schema=schema,
        # The committed counter, not a local tally: this node can be reached again
        # after a pause, in a different process, and the checkpoint is the only
        # place that remembers what the run has already spent.
        requests_used_in_run=int(state.get("model_requests", 0)),
    )

    seq = next_sequence(state)
    by_id = {column.id: column for column in columns}
    added: list[MappingDecision] = []
    events: list[AuditEvent] = []

    # The call itself, recorded where it happened. Without this a request whose
    # every suggestion the verifier then refused would leave no trace of the model
    # in the trail at all, while the run's model_requests counter said otherwise.
    # Keyed on requests_used, so an exhausted budget — which never calls out —
    # records nothing, and a provider timeout still records that a call was made.
    if outcome.requests_used > 0:
        events.append(
            _event(
                seq,
                "model_requested",
                (
                    f"Asked the model about {len(outcome.considered)} column(s) the "
                    f"rules could not place. Every reply is verified before it is used."
                ),
                execution_basis=EventExecutionBasis.MODEL_ASSISTED,
                columns=len(outcome.considered),
                requests=outcome.requests_used,
            )
        )
        seq += 1

    for accepted in outcome.accepted:
        # No enum reconstruction here: the name came from the run's schema, which
        # is chosen per run, so TargetField(...) would raise for anything outside
        # the built-in template. The verification gate in `check_proposed_mapping`
        # is what guarantees the name is real.
        header = by_id[accepted.column_id].header
        added.append(
            MappingDecision(
                column_id=accepted.column_id,
                target=accepted.target,
                outcome=MappingOutcome.AUTO_MAPPED,
                basis=MappingBasis.MODEL_ASSISTED,
                evidence=accepted.evidence,
            )
        )
        events.append(
            _event(
                seq,
                "mapping_applied",
                accepted.evidence[-1] if accepted.evidence else "Model suggestion, verified.",
                execution_basis=EventExecutionBasis.MODEL_ASSISTED,
                subject=header,
                after=_label(schema, accepted.target),
                basis=MappingBasis.MODEL_ASSISTED.value,
            )
        )
        seq += 1

    for column_id, why in outcome.rejected:
        header = by_id[column_id].header if column_id in by_id else column_id
        events.append(
            _event(
                seq,
                "mapping_suggestion_rejected",
                f"The model proposed a field for this column and it was refused. {why}",
                # The verifier rejected the proposal, so this recorded action is
                # deterministic—not an accepted model-assisted decision.
                execution_basis=EventExecutionBasis.DETERMINISTIC,
                subject=header,
            )
        )
        seq += 1

    if outcome.unavailable_reason:
        events.append(
            _event(
                seq,
                "model_unavailable",
                outcome.unavailable_reason,
                execution_basis=EventExecutionBasis.DETERMINISTIC,
                actor=Actor.SYSTEM,
                columns=len(outcome.considered),
            )
        )
        seq += 1

    # Columns the model also could not place stay unresolved, and are escalated
    # as "no target field matches" rather than quietly dropped.
    resolved_ids = {accepted.column_id for accepted in outcome.accepted}
    still_unresolved = tuple(cid for cid in unresolved if cid not in resolved_ids)

    issues: list[ReviewIssue] = []
    for column_id in still_unresolved:
        column = by_id.get(column_id)
        if column is None:
            continue
        issues.append(
            ReviewIssue(
                id=f"issue:unknown:{column_id}",
                type=IssueType.AMBIGUOUS_MAPPING,
                reason=(
                    f'"{column.header}" in {column.file_name} does not match any target '
                    f"field, and could not be placed confidently. Choose a field for it "
                    f"or leave it out."
                ),
                # Optional information we cannot place should not block delivery.
                blocking=False,
                column_id=column_id,
                options=(
                    *[
                        IssueOption(
                            id=f"map:{spec.name}",
                            label=f"Map to {spec.label}",
                            detail=(
                                f'Treat "{column.header}" as {spec.description}'
                                if spec.description
                                else f'Treat "{column.header}" as {spec.label}.'
                            ),
                            target=spec.name,
                        )
                        for spec in schema.fields
                        if spec.name not in taken
                    ],
                    IssueOption(
                        id="ignore",
                        label="Ignore this column",
                        detail=f'Leave "{column.header}" out of the migration.',
                    ),
                ),
            )
        )

    return {
        "mappings": tuple(added),
        "issues": tuple(issues),
        "unresolved_columns": still_unresolved,
        "events": tuple(events),
        "model_requests": state.get("model_requests", 0) + outcome.requests_used,
    }


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------


def _issue_payload(issue: ReviewIssue) -> dict[str, Any]:
    """What the reviewer sees. Enough context to decide in one glance."""
    return {
        "id": issue.id,
        "type": issue.type.value,
        "reason": issue.reason,
        "field": issue.field_name,
        "column_id": issue.column_id,
        "current_value": issue.current_value,
        "affected_records": len(issue.record_ids),
        "options": [
            {
                "id": option.id,
                "label": option.label,
                "detail": option.detail,
                "target": option.target,
                "value": option.value,
            }
            for option in issue.options
        ],
        "errors": [{"field": e.field_name, "message": e.message} for e in issue.detected_errors],
    }


def await_review(state: MigrationState) -> dict[str, Any]:
    """Pause for the reviewer, but only on issues that genuinely block progress.

    `interrupt()` suspends the run with its state checkpointed, so the decision
    can arrive in a later request — or a different process. Non-blocking issues
    are surfaced in the UI without stopping the migration.
    """
    issues = state.get("issues", ())
    blocking = [issue for issue in issues if issue.blocking and issue.status is IssueStatus.OPEN]

    if not blocking:
        return {"phase": RunPhase.READY}

    # The payload is what the caller receives; the return value is whatever the
    # reviewer sends back via Command(resume=...).
    decisions: dict[str, Any] = interrupt(
        {
            "kind": "review_required",
            "count": len(blocking),
            "issues": [_issue_payload(issue) for issue in blocking],
        }
    )

    seq = next_sequence(state)
    resolved: list[ReviewIssue] = []
    events: list[AuditEvent] = []

    for issue in blocking:
        choice = decisions.get(issue.id) if isinstance(decisions, dict) else None
        if not isinstance(choice, dict):
            continue  # Left unresolved; it stays blocking.

        action = ResolutionAction(choice.get("action", "approve"))
        option_id = choice.get("option_id")
        value = choice.get("value")
        note = choice.get("note")

        resolved.append(
            issue.model_copy(
                update={
                    "status": IssueStatus.RESOLVED,
                    "resolution": IssueResolution(
                        action=action,
                        option_id=option_id,
                        value=value,
                        note=note,
                        resolved_by=Actor.REVIEWER,
                    ),
                }
            )
        )
        events.append(
            _event(
                seq,
                f"issue_{action.value}",
                note or f"Reviewer chose to {action.value} this case.",
                execution_basis=EventExecutionBasis.HUMAN,
                actor=Actor.REVIEWER,
                subject=issue.field_name or issue.column_id,
                after=option_id or value,
            )
        )
        seq += 1

    return {
        "issues": tuple(resolved),
        "resolutions": {**state.get("resolutions", {}), **(decisions or {})},
        "events": tuple(events),
    }


def apply_resolutions(state: MigrationState) -> dict[str, Any]:
    """Turn reviewer decisions into mappings the pipeline can use.

    A correction is a new decision attributed to the reviewer, not a silent
    overwrite of the agent's — the audit trail has to show who decided what.
    """
    resolutions = state.get("resolutions", {})
    if not resolutions:
        return {}

    issues = {issue.id: issue for issue in state.get("issues", ())}
    columns = {column.id: column for column in state.get("columns", ())}
    schema = run_schema(state)

    added: list[MappingDecision] = []
    events: list[AuditEvent] = []
    seq = next_sequence(state)

    for issue_id, choice in resolutions.items():
        issue = issues.get(issue_id)
        if issue is None or not isinstance(choice, dict):
            continue

        action = ResolutionAction(choice.get("action", "approve"))
        if action in {ResolutionAction.REJECT, ResolutionAction.EXCLUDE}:
            continue  # Nothing to map; handled as a disposition instead.

        option_id = choice.get("option_id") or ""
        option = next((o for o in issue.options if o.id == option_id), None)

        # A mapping decision: either "map this column to that field", or
        # "use this column for a field nothing supplied".
        if option and option.target:
            column_id = issue.column_id or option_id.removeprefix("use:")
            if column_id in columns:
                label = _label(schema, option.target)
                added.append(
                    MappingDecision(
                        column_id=column_id,
                        target=option.target,
                        outcome=MappingOutcome.AUTO_MAPPED,
                        basis=MappingBasis.HUMAN_CORRECTION,
                        evidence=(f"Reviewer chose {label}.",),
                        decided_by=Actor.REVIEWER,
                    )
                )
                events.append(
                    _event(
                        seq,
                        "mapping_corrected",
                        f"Reviewer mapped this column to {label}.",
                        execution_basis=EventExecutionBasis.HUMAN,
                        actor=Actor.REVIEWER,
                        subject=columns[column_id].header,
                        after=option.target,
                    )
                )
                seq += 1

    return {"mappings": tuple(added), "events": tuple(events)}


# ---------------------------------------------------------------------------
# Reconciliation and validation
# ---------------------------------------------------------------------------


def induce_rules(state: MigrationState) -> dict[str, Any]:
    """Draft rules from the decisions the reviewer just made.

    Placed after `apply_resolutions` because it needs the answer, and gated on
    `induced_for` because the graph re-enters that path once per correction cycle:
    without the gate, every decision a reviewer made would re-draft a rule for every
    decision before it, and the budget would go on repeats.

    Nothing here changes the migration. The reviewer's decision has already been
    applied by the time this runs; a proposal is an offer about *future* runs, and a
    value-scope proposal only touches this run once it is approved. That separation
    is what makes it safe for the drafting step to be the least reliable part of the
    system.
    """
    resolutions = state.get("resolutions", {})
    if not resolutions:
        return {}

    already = set(state.get("induced_for", ()))
    pending = [issue_id for issue_id in resolutions if issue_id not in already]
    if not pending:
        return {}

    issues = {issue.id: issue for issue in state.get("issues", ())}
    schema = run_schema(state)
    run_id = str(state.get("run_id", ""))
    spent = int(state.get("model_requests", 0))

    proposals: list[ProposedRule] = []
    events: list[AuditEvent] = []
    seq = next_sequence(state)

    for issue_id in pending:
        issue = issues.get(issue_id)
        choice = resolutions.get(issue_id)
        if issue is None or not isinstance(choice, dict):
            continue

        action = str(choice.get("action", "approve"))
        chosen = str(choice.get("value") or choice.get("option_id") or action)
        # The reviewer can pre-authorise on the question itself, which is what lets a
        # value rule apply to the rest of the run without interrupting them twice.
        pre_approved = bool(choice.get("remember"))

        proposal, used, unavailable = propose_rule_from_decision(
            issue,
            action,
            chosen,
            schema=schema,
            run_id=run_id,
            requests_used_in_run=spent,
            pre_approved=pre_approved,
        )
        spent += used

        if used > 0:
            events.append(
                _event(
                    seq,
                    "rule_induction_requested",
                    (
                        "Asked the model whether this decision generalises into a rule "
                        "worth keeping. Any draft is checked against the schema first."
                    ),
                    execution_basis=EventExecutionBasis.MODEL_ASSISTED,
                    subject=issue.id,
                )
            )
            seq += 1

        if unavailable:
            events.append(
                _event(
                    seq,
                    "rule_induction_unavailable",
                    unavailable,
                    execution_basis=EventExecutionBasis.DETERMINISTIC,
                    actor=Actor.SYSTEM,
                )
            )
            seq += 1
            continue

        if proposal is None:
            continue

        proposals.append(proposal)
        events.append(
            _event(
                seq,
                "rule_proposed",
                (
                    f"{proposal.rationale} Nothing changes until you approve it."
                    if proposal.rationale
                    else "A rule was drafted from your decision. Nothing changes "
                    "until you approve it."
                ),
                execution_basis=EventExecutionBasis.MODEL_ASSISTED,
                subject=issue.id,
                scope=proposal.scope.value,
                rule_kind=proposal.rule.kind.value,
            )
        )
        seq += 1

    return {
        "proposed_rules": tuple(proposals),
        # Recorded for every pending issue, including those that produced nothing:
        # a decision that did not generalise must not be reconsidered on the next
        # pass, or the refusal would be paid for repeatedly.
        "induced_for": tuple(already | set(pending)),
        "events": tuple(events),
        "model_requests": spent,
    }


def _accepted_targets(state: MigrationState) -> dict[str, str]:
    """Column to target field name, with reviewer corrections taking precedence."""
    accepted: dict[str, str] = {}
    for decision in state.get("mappings", ()):
        if decision.outcome is MappingOutcome.AUTO_MAPPED and decision.target:
            accepted[decision.column_id] = decision.target
    return accepted


def reconcile(state: MigrationState) -> dict[str, Any]:
    """Project rows onto the target shape, then merge them into one record each."""
    targets = _accepted_targets(state)
    files = {source.id: source for source in state.get("files", ())}
    schema = run_schema(state)
    seq = next_sequence(state)

    incoming: list[IncomingRow] = []
    for row in state.get("rows", ()):
        values: dict[str, str | None] = {}
        for column_id, raw in row.values.items():
            if target := targets.get(column_id):
                values[target] = raw
        source = files.get(row.file_id)
        incoming.append(
            IncomingRow(
                values=values,
                provenance=Provenance(
                    file_id=row.file_id,
                    file_name=source.name if source else row.file_id,
                    sheet=source.sheet if source else None,
                    row=row.row,
                ),
            )
        )

    result = reconcile_identities(incoming, schema=schema, rules=run_rules(state))
    events = [
        _event(
            seq,
            "records_reconciled",
            (
                f"{len(incoming)} source rows became {len(result.records)} records; "
                f"{result.merged_rows} were merged as the same record."
            ),
            execution_basis=EventExecutionBasis.DETERMINISTIC,
            source_rows=len(incoming),
            records=len(result.records),
            merged=result.merged_rows,
        )
    ]

    return {
        "records": result.records,
        "issues": result.issues,
        "events": tuple(events),
    }


def _record_resolutions(state: MigrationState) -> tuple[set[str], dict[str, dict[str, str]]]:
    """Reviewer decisions that act on records rather than mappings.

    Returns the records to exclude, and per-record field corrections to apply
    before validation runs again.
    """
    excluded: set[str] = set()
    corrections: dict[str, dict[str, str]] = {}
    issues = {issue.id: issue for issue in state.get("issues", ())}

    for issue_id, choice in state.get("resolutions", {}).items():
        issue = issues.get(issue_id)
        if issue is None or not isinstance(choice, dict) or not issue.record_ids:
            continue

        action = ResolutionAction(choice.get("action", "approve"))
        option_id = str(choice.get("option_id") or "")

        if action is ResolutionAction.EXCLUDE or option_id.startswith("exclude:"):
            target_id = option_id.removeprefix("exclude:") if ":" in option_id else None
            excluded.update({target_id} if target_id else set(issue.record_ids))
            continue

        # A chosen value settles a conflict or replaces an invalid one.
        value: str | None = choice.get("value")
        if value is None and option_id:
            option = next((o for o in issue.options if o.id == option_id), None)
            value = option.value if option else None
        if value is not None and issue.field_name:
            for record_id in issue.record_ids:
                corrections.setdefault(record_id, {})[issue.field_name] = str(value)

    return excluded, corrections


def clean_and_validate(state: MigrationState) -> dict[str, Any]:
    """Apply safe repairs and validate, escalating anything that fails twice."""
    seq = next_sequence(state)
    schema = run_schema(state)
    rules = run_rules(state)
    # Which source header supplied each field, so a date rule scoped to one column
    # is not applied to another column feeding the same field.
    headers_by_field = {
        decision.target: column.header
        for decision in state.get("mappings", ())
        if decision.target
        for column in state.get("columns", ())
        if column.id == decision.column_id
    }
    excluded_ids, corrections = _record_resolutions(state)
    validated: list[CanonicalRecord] = []
    issues: list[ReviewIssue] = []
    events: list[AuditEvent] = []
    repair_count = 0

    for record in state.get("records", ()):
        if record.disposition is Disposition.EXCLUDED or record.id in excluded_ids:
            validated.append(
                record.model_copy(
                    update={
                        "disposition": Disposition.EXCLUDED,
                        "exclusion_reason": record.exclusion_reason or "Excluded by the reviewer.",
                    }
                )
            )
            continue

        values = dict(record.values)
        applied = corrections.get(record.id, {})
        if applied:
            values.update(applied)

        outcome = run_validation_passes(
            values, schema=schema, rules=rules, headers=headers_by_field
        )
        repair_count += len(outcome.repairs)

        for repair in outcome.repairs:
            rule = repair.rule.replace("_", " ")
            events.append(
                _event(
                    seq,
                    "value_repaired",
                    f"{_label(schema, repair.field_name)}: {rule}.",
                    execution_basis=EventExecutionBasis.DETERMINISTIC,
                    subject=_subject_of(schema, record),
                    before=repair.before,
                    after=repair.after,
                )
            )
            seq += 1

        for field_name, new_value in applied.items():
            events.append(
                _event(
                    seq,
                    "value_corrected",
                    f"Reviewer supplied a {_label(schema, field_name)}.",
                    execution_basis=EventExecutionBasis.HUMAN,
                    actor=Actor.REVIEWER,
                    subject=_subject_of(schema, record),
                    before=record.values.get(field_name),
                    after=new_value,
                )
            )
            seq += 1

        disposition = Disposition.READY if outcome.valid else Disposition.NEEDS_REVIEW
        validated.append(
            record.model_copy(
                update={
                    "values": outcome.values,
                    # A human edit produces a new revision, so delivery is bound
                    # to what was actually reviewed.
                    "revision": record.revision + 1 if applied else record.revision,
                    "repairs": outcome.repairs,
                    "validation": outcome.passes,
                    "disposition": disposition,
                }
            )
        )

        if outcome.failed_twice and record.id not in excluded_ids:
            errors: tuple[ValidationError, ...] = outcome.passes[-1].errors
            explanation = (
                "No safe automatic repair existed for this value."
                if outcome.no_repair_available
                else "Safe repairs were applied and it is still invalid."
            )
            invalid_field = errors[0].field_name if errors else None
            label = _label(schema, invalid_field)
            issues.append(
                ReviewIssue(
                    id=f"issue:invalid:{record.id}",
                    type=IssueType.VALIDATION_FAILED_TWICE,
                    reason=(
                        f"{_subject_of(schema, record)} failed validation twice. {explanation}"
                    ),
                    blocking=True,
                    record_ids=(record.id,),
                    field_name=invalid_field,
                    current_value=(record.values.get(invalid_field) if invalid_field else None),
                    detected_errors=errors,
                    # Never leave a reviewer at a dead end: correcting the value
                    # and excluding the record are the two real ways forward.
                    options=(
                        IssueOption(
                            id="correct_value",
                            label=f"Correct {label}",
                            detail=(
                                f"Supply a valid {label} for this record. "
                                f"It will be validated again."
                            ),
                            value=None,
                        ),
                        IssueOption(
                            id=f"exclude:{record.id}",
                            label="Exclude this record",
                            detail=(
                                "Leave it out of the migration. It stays visible in the "
                                "totals and the audit trail."
                            ),
                        ),
                    ),
                )
            )
            events.append(
                _event(
                    seq,
                    "validation_failed_twice",
                    explanation,
                    execution_basis=EventExecutionBasis.DETERMINISTIC,
                    subject=_subject_of(schema, record),
                    errors=len(errors),
                )
            )
            seq += 1

    ready = sum(1 for r in validated if r.disposition is Disposition.READY)
    events.append(
        _event(
            seq,
            "validation_summary",
            f"{ready} of {len(validated)} records are valid and ready to deliver.",
            execution_basis=EventExecutionBasis.DETERMINISTIC,
            ready=ready,
            needs_review=len(validated) - ready,
            repairs=repair_count,
        )
    )

    return {"records": tuple(validated), "issues": tuple(issues), "events": tuple(events)}


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def deliver(state: MigrationState) -> dict[str, Any]:
    """Push validated records to the destination over real HTTP.

    Records are delivered one at a time so a failure is attributable to a
    specific record rather than a batch. Each attempt is recorded before the
    outcome is known, which is what makes recovery possible: if this process dies
    mid-flight, the persisted intent tells the next one what was already in
    progress, and the idempotency key ensures replaying it cannot duplicate.
    """
    run_id = state.get("run_id", "run")
    records = state.get("records", ())
    schema = run_schema(state)
    existing = {intent.record_id: intent for intent in state.get("deliveries", ())}
    demo_config = state.get("demo_delivery", {}) or {}

    deliverable = [
        record
        for record in records
        if record.disposition in {Disposition.READY, Disposition.RETRY_WAIT}
        or (
            record.disposition is Disposition.FAILED
            and existing.get(record.id) is not None
            and existing[record.id].state is DeliveryState.RETRY_WAIT
        )
    ]

    if not deliverable:
        return {"phase": _final_phase(records, tuple(existing.values()))}

    seq = next_sequence(state)
    intents: list[DeliveryIntent] = []
    events: list[AuditEvent] = []
    updated: dict[str, CanonicalRecord] = {}

    with build_client() as client:
        for record in deliverable:
            prior = existing.get(record.id)
            attempt_number = len(prior.attempts) + 1 if prior else 1
            if attempt_number > MAX_ATTEMPTS:
                continue

            subject = _subject_of(schema, record)
            payload = build_payload(record, schema=schema)
            digest = payload_hash(payload)
            key = idempotency_key(run_id, record)

            events.append(
                _event(
                    seq,
                    "delivery_attempted",
                    f"Sending to the destination (attempt {attempt_number}).",
                    execution_basis=EventExecutionBasis.DETERMINISTIC,
                    subject=subject,
                    attempt=attempt_number,
                )
            )
            seq += 1

            # Per-record demo behaviour, configured by the run rather than
            # inferred from the data, so production logic has no test branches.
            #
            # Keyed on the record's *identity*, not the name shown in the audit
            # trail: those diverged once display started preferring a person's
            # name, and looking the behaviour up by "Asha Rao" silently matched
            # nothing.
            demo_headers: dict[str, str] = {}
            identity = schema.identity_field
            demo_key = (identity and record.values.get(identity)) or record.id
            behaviour = demo_config.get(demo_key)
            if behaviour == "fail_once" and attempt_number == 1:
                demo_headers["x-demo-fail-once"] = "1"
            elif behaviour == "reject":
                demo_headers["x-demo-reject"] = "1"

            result = deliver_record(
                client,
                run_id,
                record,
                schema=schema,
                request_origin=state.get("request_origin"),
                attempt_number=attempt_number,
                demo_headers=demo_headers or None,
            )

            attempts = (*(prior.attempts if prior else ()), attempt_record(result, attempt_number))
            intents.append(
                DeliveryIntent(
                    record_id=record.id,
                    revision=record.revision,
                    idempotency_key=key,
                    payload_hash=digest,
                    attempts=attempts,
                    state=result.state,
                    target_id=result.target_id,
                    next_attempt_at=result.next_attempt_at,
                )
            )

            if result.state is DeliveryState.SUCCEEDED:
                disposition = Disposition.DELIVERED
                action = "delivery_succeeded"
            elif result.state is DeliveryState.RETRY_WAIT:
                disposition = Disposition.RETRY_WAIT
                action = "delivery_retry_scheduled"
            else:
                disposition = Disposition.FAILED
                action = "delivery_failed"

            updated[record.id] = record.model_copy(update={"disposition": disposition})
            events.append(
                _event(
                    seq,
                    action,
                    result.detail,
                    execution_basis=EventExecutionBasis.DETERMINISTIC,
                    subject=subject,
                    after=result.target_id,
                    status=result.status_code,
                    attempt=attempt_number,
                )
            )
            seq += 1

    merged_records = tuple(updated.get(record.id, record) for record in records)
    all_intents = tuple({**existing, **{i.record_id: i for i in intents}}.values())

    delivered = sum(1 for i in all_intents if i.state is DeliveryState.SUCCEEDED)
    failed = sum(1 for i in all_intents if i.state is DeliveryState.FAILED)
    waiting = sum(1 for i in all_intents if i.state is DeliveryState.RETRY_WAIT)

    summary = f"{delivered} delivered, {failed} failed"
    if waiting:
        summary += f", {waiting} awaiting retry"
    events.append(
        _event(
            seq,
            "delivery_summary",
            summary + ".",
            execution_basis=EventExecutionBasis.DETERMINISTIC,
            delivered=delivered,
            failed=failed,
            retrying=waiting,
        )
    )

    return {
        "records": merged_records,
        "deliveries": tuple(intents),
        "events": tuple(events),
        "phase": _final_phase(merged_records, all_intents),
    }


def _final_phase(
    records: tuple[CanonicalRecord, ...], intents: tuple[DeliveryIntent, ...]
) -> RunPhase:
    """Where the run stands once delivery has run."""
    if any(intent.state is DeliveryState.RETRY_WAIT for intent in intents):
        return RunPhase.DELIVERING
    if any(intent.state is DeliveryState.FAILED for intent in intents):
        return RunPhase.COMPLETE_WITH_FAILURES
    if any(record.disposition is Disposition.NEEDS_REVIEW for record in records):
        return RunPhase.REVIEW
    return RunPhase.COMPLETE
