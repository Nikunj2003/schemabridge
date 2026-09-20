"""The rules API.

A rule's own store enforces ownership and version-guarded writes; this module
adds only what an HTTP boundary needs on top of that: a request shape that
cannot set server-owned fields, the shipped layer projected alongside the
caller's own rules, and a preview that answers "what would this do" without
writing anything.

Two routes are declared before `/{rule_id}` for the same reason `schema_routes`
orders `/import` ahead of `/{schema_id}`: FastAPI matches path templates in
declaration order, so a literal path has to come first or `/preview` would be
swallowed as a rule id.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, ValidationError

from schemabridge.domain.mapping import decide_mappings
from schemabridge.domain.normalize import DateStatus, normalize_header, parse_calendar_date
from schemabridge.domain.rules import (
    MAX_RULES_PER_SESSION,
    DateOrder,
    Rule,
    RuleKind,
    RuleOrigin,
    RuleRejectedError,
    RuleSet,
    builtin_rules,
    check_against_schema,
)
from schemabridge.domain.schema import TargetSchema
from schemabridge.domain.target import BUILTIN_SCHEMA
from schemabridge.ingest.csv_source import parse_csv
from schemabridge.ingest.limits import INGEST_LIMITS
from schemabridge.ingest.profile import profile_columns
from schemabridge.ingest.xlsx_source import parse_xlsx
from schemabridge.server import rules as rule_store
from schemabridge.server import schemas as schema_store
from schemabridge.server.auth import principal_from_request
from schemabridge.server.sessions import require_same_origin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rules", tags=["rules"])


class RuleInput(BaseModel):
    """A rule as the rules page submits it.

    Mirrors `Rule` rather than reusing it, so a request cannot set fields the
    caller has no business setting: `rule_id` and `hits` are assigned and
    tracked by the store, and `origin` is decided by which route created the
    rule rather than by what the request claims to be.
    """

    kind: RuleKind
    enabled: bool = True
    header: str = ""
    field_name: str = ""
    value: str = ""
    canonical: str = ""
    date_order: DateOrder | None = None
    schema_id: str = ""
    rationale: str = ""
    #: The version the caller last read. Required on a save so a concurrent
    #: edit cannot be silently discarded.
    if_version: int | None = None


class ToggleInput(BaseModel):
    enabled: bool
    #: Which schema's shipped rule to disable. Only read when toggling a `builtin:`
    #: id, since one of the caller's own rules already knows its schema.
    schema_id: str = ""


def _require_session(request: Request) -> str:
    """Compatibility name for the resolved workspace id."""
    return principal_from_request(request).owner_id


def _build(payload: RuleInput, *, origin: RuleOrigin) -> Rule:
    """Turn a submission into a rule, or explain why it is not one.

    Validation is delegated entirely to `Rule`'s own model validators: there is
    no second set of rules here to disagree with the first.
    """
    try:
        return Rule(
            kind=payload.kind,
            origin=origin,
            header=payload.header,
            field_name=payload.field_name,
            value=payload.value,
            canonical=payload.canonical,
            date_order=payload.date_order,
            schema_id=payload.schema_id,
            rationale=payload.rationale,
        )
    except ValidationError as error:
        # The model's own message is the useful one: it says which kind and why.
        first = error.errors()[0]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(first.get("msg", "That rule is not valid.")).removeprefix("Value error, "),
        ) from None


def _checked(rule: Rule, schema: TargetSchema) -> Rule:
    """A rule the schema can support, or a 400 explaining why not.

    A hand-written rule faces exactly the checks a drafted one does. Without this a
    person could type the rule the model is forbidden to propose — resolving a header
    two fields claim — which would make the manual path the dangerous one.
    """
    try:
        check_against_schema(rule, schema)
    except RuleRejectedError as rejected:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(rejected)) from None
    return rule


def _unavailable(error: Exception) -> HTTPException:
    logger.warning("rule store unavailable: %s", type(error).__name__)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Rules are unavailable right now.",
    )


def rule_view(
    rule: Rule, *, version: int, editable: bool, overridden: bool = False
) -> dict[str, Any]:
    """A rule as the browser needs it: the fields, plus what it may do with them."""
    return {
        "rule_id": rule.rule_id,
        "kind": rule.kind.value,
        "origin": rule.origin.value,
        "enabled": rule.enabled,
        "header": rule.header,
        "field_name": rule.field_name,
        "value": rule.value,
        "canonical": rule.canonical,
        "date_order": rule.date_order.value if rule.date_order else None,
        "targets_rule_id": rule.targets_rule_id,
        "schema_id": rule.schema_id,
        "rationale": rule.rationale,
        # The decision this rule came from, so the page can show the question rather
        # than asserting that one existed.
        "provenance": (
            rule.provenance.model_dump(mode="json") if rule.provenance is not None else None
        ),
        "hits": rule.hits,
        "version": version,
        "editable": editable,
        "overridden": overridden,
    }


def _resolve_schema_for_projection(schema_id: str | None, session_id: str) -> TargetSchema:
    """Which schema's shipped layer to project.

    Falls back to the built-in template rather than refusing outright when the
    requested schema cannot be loaded: the shipped layer is informational, and a
    caller browsing rules should not be blocked by an unrelated schema problem.
    """
    if not schema_id or schema_id == BUILTIN_SCHEMA.schema_id:
        return BUILTIN_SCHEMA
    try:
        record = schema_store.find_schema(schema_id, session_id)
    except Exception as error:
        logger.warning("schema store unavailable while projecting rules: %s", type(error).__name__)
        return BUILTIN_SCHEMA
    return record.schema if record is not None else BUILTIN_SCHEMA


@router.get("")
def list_rules(request: Request, schema_id: str | None = None) -> dict[str, Any]:
    """The shipped layer for one schema, plus the caller's own rules.

    The shipped layer is computed here, never stored: it is derived from the
    schema's own fields, so it cannot drift from what the engine actually
    consults.

    Readable without a session, unlike every write on this router. A first-time
    visitor has no cookie yet and has saved nothing, so demanding one would greet
    them with an error on a page whose whole purpose is to explain what the engine
    already knows. They see the shipped layer and an empty list of their own, which
    is the truth.
    """
    session_id = _require_session(request)
    schema = _resolve_schema_for_projection(schema_id, session_id)

    mine: list[Any] = []
    try:
        mine = rule_store.list_rules(session_id)
    except Exception as error:
        raise _unavailable(error) from None

    overridden_targets = {
        record.rule.targets_rule_id
        for record in mine
        if record.rule.kind is RuleKind.OVERRIDE and record.rule.enabled
    }

    builtin_view = [
        rule_view(
            rule,
            version=0,
            editable=False,
            overridden=rule.rule_id in overridden_targets,
        )
        for rule in builtin_rules(schema)
    ]
    mine_view = [rule_view(record.rule, version=record.version, editable=True) for record in mine]

    return {
        "builtin": builtin_view,
        "mine": mine_view,
        "limits": {"max_rules": MAX_RULES_PER_SESSION},
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_rule(request: Request, payload: RuleInput) -> dict[str, Any]:
    """Store a new rule for this visitor."""
    require_same_origin(request)
    session_id = _require_session(request)
    schema = _resolve_schema_for_projection(payload.schema_id or None, session_id)
    rule = _checked(_build(payload, origin=RuleOrigin.HANDWRITTEN), schema)
    try:
        record = rule_store.create_rule(session_id, rule)
    except rule_store.RuleLimitError as limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(limit)
        ) from None
    except HTTPException:
        raise
    except Exception as error:
        raise _unavailable(error) from None
    return rule_view(record.rule, version=record.version, editable=True)


@router.post("/preview")
async def preview_rule(
    request: Request,
    files: Annotated[list[UploadFile], File()],
    rule: Annotated[str, Form()],
) -> dict[str, Any]:
    """What a draft rule would do, without storing it or the files.

    Parses the uploaded files exactly as starting a run does, builds the draft
    rule, and compares `decide_mappings` with and without it. That is the honest
    way to answer "what would this do": it reuses the real mapping engine rather
    than a second, hand-rolled notion of what a rule matches.
    """
    require_same_origin(request)
    session_id = _require_session(request)

    try:
        payload = RuleInput.model_validate_json(rule)
    except ValidationError as error:
        first = error.errors()[0]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(first.get("msg", "That rule is not valid.")).removeprefix("Value error, "),
        ) from None
    draft_schema = _resolve_schema_for_projection(payload.schema_id or None, session_id)
    draft = _checked(_build(payload, origin=RuleOrigin.HANDWRITTEN), draft_schema)

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Upload at least one file."
        )
    if len(files) > INGEST_LIMITS.max_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"At most {INGEST_LIMITS.max_files} files per preview.",
        )

    columns: list[Any] = []
    rows: list[Any] = []
    profiles: list[Any] = []
    total_bytes = 0

    for index, upload in enumerate(files):
        content = await upload.read()
        total_bytes += len(content)
        if total_bytes > INGEST_LIMITS.max_total_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"The files total more than {INGEST_LIMITS.max_total_bytes // (1024 * 1024)}MB."
                ),
            )

        name = upload.filename or f"file-{index + 1}"
        file_id = f"f{index}"
        lowered = name.lower()

        if lowered.endswith(".xlsx"):
            parsed = parse_xlsx(file_id, name, content)
        elif lowered.endswith((".csv", ".txt")):
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{name}: not valid UTF-8 text.",
                ) from None
            parsed = parse_csv(file_id, name, text)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{name}: only .csv and .xlsx files are supported.",
            )

        if not parsed.ok:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=parsed.error)

        columns.extend(parsed.file.columns)
        rows.extend(parsed.rows)
        profiles.extend(profile_columns(parsed.file, parsed.rows))

    if len(rows) > INGEST_LIMITS.max_total_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{len(rows)} rows exceeds the limit of {INGEST_LIMITS.max_total_rows}.",
        )

    schema = _resolve_schema_for_projection(payload.schema_id or None, session_id)

    matched_columns: list[dict[str, Any]] = []
    matched_values: list[dict[str, Any]] = []

    # What the engine would decide with no rules at all, so a value or date rule
    # can be scoped to whichever column actually feeds the field it names —
    # without the draft rule influencing that mapping itself.
    baseline = decide_mappings(columns, profiles, schema=schema)

    if draft.kind in {RuleKind.HEADER_ALIAS, RuleKind.COLUMN_IGNORE}:
        # Scoped to the schema being previewed against, or the rule set would
        # filter the draft out as belonging elsewhere and the preview would report
        # that a working rule changes nothing.
        with_rule = decide_mappings(
            columns,
            profiles,
            schema=schema,
            rules=RuleSet((draft,), schema_id=schema.schema_id),
        )
        before_by_column = {decision.column_id: decision for decision in baseline.decisions}
        for decision in with_rule.decisions:
            before = before_by_column.get(decision.column_id)
            if before is None:
                continue
            # Compared on outcome as well as target, because an ignored column has
            # no target either way: its target is None before and after, so a
            # target-only diff would report that an ignore rule changes nothing.
            if (before.target, before.outcome) == (decision.target, decision.outcome):
                continue
            column = next((c for c in columns if c.id == decision.column_id), None)
            if column is None:
                continue
            matched_columns.append(
                {
                    "file_name": column.file_name,
                    "header": column.header,
                    # Empty rather than null when the column is left out, so the page
                    # can say "left out" instead of rendering a missing field name.
                    "target_field": decision.target or "",
                }
            )
    elif draft.kind is RuleKind.VALUE_ALIAS:
        mapped_columns = {
            decision.column_id
            for decision in baseline.decisions
            if decision.target == draft.field_name
        }
        for column in columns:
            if column.id not in mapped_columns:
                continue
            profile = next((p for p in profiles if p.column_id == column.id), None)
            if profile is None:
                continue
            for sample in profile.samples:
                if normalize_header(sample) == draft.value:
                    matched_values.append(
                        {
                            "field_name": draft.field_name,
                            "before": sample,
                            "after": draft.canonical,
                        }
                    )
    elif draft.kind is RuleKind.DATE_ORDER:
        field_mapped_columns: set[str] | None = (
            {
                decision.column_id
                for decision in baseline.decisions
                if decision.target == draft.field_name
            }
            if draft.field_name and not draft.header
            else None
        )
        for column in columns:
            if draft.header and column.header != draft.header:
                continue
            if field_mapped_columns is not None and column.id not in field_mapped_columns:
                continue
            profile = next((p for p in profiles if p.column_id == column.id), None)
            if profile is None:
                continue
            for sample in profile.samples:
                result = parse_calendar_date(sample)
                if result.status is not DateStatus.AMBIGUOUS:
                    continue
                settled = next(
                    (
                        interpretation.value
                        for interpretation in result.interpretations
                        if (
                            (
                                draft.date_order is DateOrder.DAY_FIRST
                                and interpretation.format == "DD/MM/YYYY"
                            )
                            or (
                                draft.date_order is DateOrder.MONTH_FIRST
                                and interpretation.format == "MM/DD/YYYY"
                            )
                        )
                    ),
                    None,
                )
                if settled is not None:
                    matched_values.append(
                        {
                            "field_name": draft.field_name or column.header,
                            "before": sample,
                            "after": settled,
                        }
                    )

    return {
        "matched_columns": matched_columns,
        "matched_values": matched_values,
        "would_change": len(matched_columns) + len(matched_values),
    }


@router.get("/{rule_id}")
def read_rule(rule_id: str, request: Request) -> dict[str, Any]:
    """One rule the caller owns."""
    session_id = _require_session(request)
    try:
        record = rule_store.find_rule(rule_id, session_id)
    except Exception as error:
        raise _unavailable(error) from None
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such rule.")
    return rule_view(record.rule, version=record.version, editable=True)


@router.put("/{rule_id}")
def replace_rule(rule_id: str, request: Request, payload: RuleInput) -> dict[str, Any]:
    """Save changes to a rule the caller owns."""
    require_same_origin(request)
    session_id = _require_session(request)
    if payload.if_version is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Saving needs the version the page last read.",
        )
    schema = _resolve_schema_for_projection(payload.schema_id or None, session_id)
    rule = _checked(_build(payload, origin=RuleOrigin.HANDWRITTEN), schema)
    try:
        record = rule_store.update_rule(rule_id, session_id, rule, if_version=payload.if_version)
    except rule_store.StaleWriteError as stale:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(stale)) from None
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such rule.") from None
    except HTTPException:
        raise
    except Exception as error:
        raise _unavailable(error) from None
    return rule_view(record.rule, version=record.version, editable=True)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_rule(rule_id: str, request: Request) -> Response:
    """Forget a rule. Runs that used it keep their own snapshot."""
    require_same_origin(request)
    session_id = _require_session(request)
    try:
        deleted = rule_store.delete_rule(rule_id, session_id)
    except Exception as error:
        raise _unavailable(error) from None
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such rule.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{rule_id}/toggle")
def toggle_rule(rule_id: str, request: Request, payload: ToggleInput) -> dict[str, Any]:
    """Turn a rule on or off.

    A `rule_*` id is the caller's own and is toggled directly. A `builtin:*` id
    has no row of its own — disabling it is expressed as an override, and
    re-enabling it turns that override back off, which is exactly what
    `override_builtin` already does when called twice.
    """
    require_same_origin(request)
    session_id = _require_session(request)

    if rule_id.startswith("builtin:"):
        try:
            if payload.enabled:
                existing = next(
                    (
                        record
                        for record in rule_store.list_rules(session_id)
                        if record.rule.kind is RuleKind.OVERRIDE
                        and record.rule.targets_rule_id == rule_id
                    ),
                    None,
                )
                if existing is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND, detail="No such rule."
                    )
                record = rule_store.set_enabled(existing.rule_id, session_id, enabled=False)
            else:
                # A shipped rule id carries the schema it belongs to, so the
                # override lands on the same contract rather than everywhere.
                record = rule_store.override_builtin(
                    session_id,
                    rule_id,
                    schema_id=payload.schema_id or BUILTIN_SCHEMA.schema_id,
                )
        except HTTPException:
            raise
        except Exception as error:
            raise _unavailable(error) from None
        return rule_view(record.rule, version=record.version, editable=True)

    try:
        record = rule_store.set_enabled(rule_id, session_id, enabled=payload.enabled)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such rule.") from None
    except Exception as error:
        raise _unavailable(error) from None
    return rule_view(record.rule, version=record.version, editable=True)


__all__ = ["router", "rule_view"]
