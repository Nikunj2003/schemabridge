"""The migration API.

Four rules shape these routes.

Ownership is checked on every operation. A run id is not a credential — it appears
in URLs and screenshots — so the session cookie decides who may read or change a
run.

GET never mutates. The browser polls this API once or twice a second, and a GET
with side effects would make that refresh loop an actor in the migration.

Work happens in bounded steps. One `advance` runs the graph until it finishes or
pauses, then returns a checkpoint, so a long migration crosses several requests
instead of holding one open past the platform's limit.

And the workflow runs off the event loop. It is synchronous, and it makes an
outbound HTTP call to this same application to reach the destination stub. Left on
the event loop it would deadlock: the handler would hold the only worker while
waiting for a request that worker has to serve. `run_in_threadpool` keeps the loop
free to answer it.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status
from starlette.concurrency import run_in_threadpool

from schemabridge.api import rule_routes
from schemabridge.api.views import RunView, build_run_view, target_schema_view
from schemabridge.domain.infer import infer_schema
from schemabridge.domain.models import (
    TERMINAL_PHASES,
    ColumnProfile,
    RunPhase,
    SourceColumn,
    SourceFile,
    SourceRow,
)
from schemabridge.domain.rules import Rule
from schemabridge.domain.schema import TargetSchema
from schemabridge.domain.spec import SpecError, parse_spec
from schemabridge.domain.target import BUILTIN_SCHEMA
from schemabridge.graph import runner
from schemabridge.ingest.csv_source import parse_csv
from schemabridge.ingest.limits import INGEST_LIMITS
from schemabridge.ingest.profile import profile_columns
from schemabridge.ingest.xlsx_source import parse_xlsx
from schemabridge.server import migration_quota
from schemabridge.server import rules as rule_store
from schemabridge.server import runs as registry
from schemabridge.server import schemas as schema_store
from schemabridge.server.budget import usage_today
from schemabridge.server.sessions import ensure_session, read_session, require_same_origin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["migration"])

#: Employee ids the demo fixtures use to exercise delivery failures. Held here
#: rather than in the delivery path so production logic has no test branches.
_DEMO_DELIVERY = {"E-1007": "fail_once", "E-1008": "reject"}


def _owned_run(run_id: str, request: Request) -> registry.RunRecord:
    """Fetch a run the caller is entitled to see."""
    session_id = read_session(request)
    record = registry.find_run(run_id)
    # The same answer whether the run is absent or someone else's: revealing the
    # difference would confirm that a guessed id exists.
    if record is None or not session_id or record.owner_session_id != session_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such run.")
    return record


def _request_origin(request: Request) -> str:
    """Where outbound delivery should go when no origin is configured."""
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        scheme = request.headers.get("x-forwarded-proto", "https").split(",")[0].strip()
        return f"{scheme}://{forwarded_host}"
    return f"{request.url.scheme}://{request.url.netloc}"


@router.get("/schema")
def read_schema() -> dict[str, Any]:
    """The default target contract, and the ingest limits.

    The built-in template, so the tables have column headers before a run exists.
    A run's own contract travels on the run itself, since it may be a saved schema
    or one detected from the upload.
    """
    view = target_schema_view(BUILTIN_SCHEMA)
    # asdict, not vars: the limits are a slotted dataclass and have no __dict__.
    return {**view, "fields": view["fields"], "limits": asdict(INGEST_LIMITS)}


def _resolve_schema(
    schema_id: str | None,
    session_id: str,
    columns: list[SourceColumn],
    profiles: list[ColumnProfile],
    schema_spec: str | None = None,
) -> TargetSchema:
    """Which contract this run maps onto.

    Four ways in, matching the ways a consultant actually arrives: a spec file
    they already have, a contract they saved here, no contract at all (detect one
    from the file), or the shipped template as a default.

    A spec supplied inline is used for this run only and not saved — the migration
    is the thing being asked for, and a schema saved as a side effect of running
    one is clutter nobody asked for. It can be saved separately from the builder.
    """
    if schema_spec and schema_spec.strip():
        try:
            return parse_spec(schema_spec).schema
        except SpecError as problem:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(problem)
            ) from None
    if not schema_id or schema_id == BUILTIN_SCHEMA.schema_id:
        return BUILTIN_SCHEMA
    if schema_id == "detected":
        return infer_schema(columns, profiles)
    try:
        record = schema_store.find_schema(schema_id, session_id)
    except Exception as error:
        logger.warning("schema store unavailable: %s", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The chosen schema could not be loaded, so the migration did not start.",
        ) from None
    if record is None:
        # Refused rather than silently falling back: migrating against a
        # different contract than the one asked for is worse than not starting.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such schema.")
    return record.schema


@router.get("/usage")
def read_usage() -> dict[str, int]:
    """Shared inference allowance, so the UI can explain a refusal honestly."""
    try:
        used, limit = usage_today()
    except Exception:
        return {"used": 0, "limit": 0}
    return {"used": used, "limit": limit}


@router.get("/migration-usage")
def read_migration_usage(request: Request, response: Response) -> dict[str, str | int]:
    """Authoritative daily starts remaining for this anonymous browser session."""
    session_id = ensure_session(request, response)
    try:
        usage = migration_quota.usage_for_session(session_id)
    except Exception as error:
        logger.warning("migration quota unavailable: %s", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Migration allowance is unavailable.",
        ) from None
    return {
        "used": usage.used,
        "limit": usage.limit,
        "reset_at": usage.reset_at.isoformat(),
        "scope": "anonymous_browser_session",
    }


def _run_rules(session_id: str, schema: TargetSchema) -> tuple[Rule, ...]:
    """The rules this run should carry, or none if the store is unreachable.

    A rule store outage degrades the run to the shipped engine rather than refusing
    to start: the migration still works, it just knows less, and the trail shows no
    learned marks so nobody is misled about why.
    """
    try:
        resolved = rule_store.resolve_rules(session_id, schema)
    except Exception as error:
        logger.warning("rule store unavailable: %s", type(error).__name__)
        return ()
    return resolved.rules


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    request: Request,
    response: Response,
    files: Annotated[list[UploadFile], File()],
    schema_id: Annotated[str | None, Form()] = None,
    schema_spec: Annotated[str | None, Form()] = None,
) -> RunView:
    """Ingest source files and start a migration.

    `schema_id` picks the contract: a saved schema's id, "detected" to derive one
    from the uploaded headers, or omitted for the built-in template.
    `schema_spec` supplies a JSON or YAML spec inline for this run only, and takes
    precedence when both are given.
    """
    require_same_origin(request)
    session_id = ensure_session(request, response)

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Upload at least one file."
        )
    if len(files) > INGEST_LIMITS.max_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"At most {INGEST_LIMITS.max_files} files per migration.",
        )

    sources: list[SourceFile] = []
    columns: list[SourceColumn] = []
    rows: list[SourceRow] = []
    profiles: list[ColumnProfile] = []
    names: list[str] = []
    total_bytes = 0

    for index, upload in enumerate(files):
        content = await upload.read()
        total_bytes += len(content)
        # Checked against the real byte count, not a declared header.
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

        sources.append(parsed.file)
        columns.extend(parsed.file.columns)
        rows.extend(parsed.rows)
        profiles.extend(profile_columns(parsed.file, parsed.rows))
        names.append(name)

    if len(rows) > INGEST_LIMITS.max_total_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{len(rows)} rows exceeds the limit of {INGEST_LIMITS.max_total_rows}.",
        )

    schema = _resolve_schema(schema_id, session_id, columns, profiles, schema_spec)

    run_id = registry.new_run_id()
    try:
        migration_quota.reserve_migration_start(session_id, run_id)
    except migration_quota.MigrationQuotaExhaustedError as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(error)
        ) from None
    except Exception as error:
        logger.warning("migration quota unavailable: %s", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Migration allowance is unavailable, so a migration cannot be started.",
        ) from None

    try:
        registry.create_run(run_id, session_id, tuple(names), len(rows))
    except Exception as error:
        try:
            migration_quota.release_migration_start(session_id, run_id)
        except Exception:
            logger.warning("migration quota release failed after registry error")
        logger.warning("run registry unavailable: %s", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The database is unavailable, so a migration cannot be started.",
        ) from None

    initial: dict[str, Any] = {
        "run_id": run_id,
        "owner_session_id": session_id,
        "files": tuple(sources),
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
        # Snapshotted for the same reason as the schema, and with more force: this
        # run may add rules to the store partway through, and a run that re-read the
        # store on resume would apply rules to its second half that its first half
        # never saw.
        "rules": _run_rules(session_id, schema),
        "proposed_rules": (),
        "induced_for": (),
        "phase": RunPhase.INGESTED,
        "request_origin": _request_origin(request),
        "demo_delivery": _DEMO_DELIVERY,
        # Snapshotted, not referenced: editing the saved schema later must not
        # change what this run is validated against.
        "target_schema": schema,
    }

    # Off the event loop: the workflow delivers over HTTP to this same app.
    result = await run_in_threadpool(runner.start, initial, run_id)
    return build_run_view(run_id, result.state, paused=result.paused, runnable=result.runnable)


@router.get("/runs/{run_id}")
def read_run(run_id: str, request: Request, since: int = 0) -> RunView:
    """The current state. Safe to poll; never mutates."""
    _owned_run(run_id, request)
    state = runner.read_state(run_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such run.")
    return build_run_view(
        run_id,
        state,
        paused=bool(state.get("_paused")),
        # From the checkpoint, not inferred from `paused`: a finished run is
        # neither paused nor runnable, and deriving one from the other would have
        # the browser's advance loop calling forever after the run ended.
        runnable=bool(state.get("_runnable")),
        since=since,
    )


def _record_rule_hits(state: dict[str, Any]) -> None:
    """Credit the rules that answered, once the run has finished.

    Counted from the run's own mapping decisions rather than from the `RuleSet`,
    because the set that did the counting lived inside a graph node in another
    process and is gone by now. Deliberately not written during mapping: a hit is a
    display number, and a database round trip per column would put a network call
    between a column and its answer.

    Best effort, and swallowed: losing a count must never turn a finished migration
    into an error.
    """
    phase = state.get("phase")
    if phase not in TERMINAL_PHASES:
        return
    hits: dict[str, int] = {}
    for event in state.get("events", ()):
        detail = getattr(event, "detail", None)
        if not isinstance(detail, dict):
            continue
        rule_id = detail.get("rule_id")
        if isinstance(rule_id, str) and rule_id.startswith("rule_"):
            hits[rule_id] = hits.get(rule_id, 0) + 1
    if hits:
        rule_store.record_hits(hits)


@router.post("/runs/{run_id}/advance")
async def advance_run(run_id: str, request: Request) -> RunView:
    """Do the next bounded piece of work."""
    require_same_origin(request)
    _owned_run(run_id, request)
    try:
        result = await run_in_threadpool(runner.advance, run_id)
    except Exception as error:
        logger.exception("advance failed for %s", run_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"The migration could not continue ({type(error).__name__}).",
        ) from None
    _record_rule_hits(result.state)
    return build_run_view(run_id, result.state, paused=result.paused, runnable=result.runnable)


@router.post("/runs/{run_id}/resolve")
async def resolve_run(run_id: str, request: Request, decisions: dict[str, Any]) -> RunView:
    """Apply the reviewer's decisions and continue.

    Each decision names an issue and an action. Nothing here trusts the browser
    to have applied anything: the graph re-derives records from the decision and
    revalidates.
    """
    require_same_origin(request)
    _owned_run(run_id, request)

    if not decisions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No decisions supplied."
        )

    try:
        result = await run_in_threadpool(runner.resolve, run_id, decisions)
    except Exception as error:
        logger.exception("resolve failed for %s", run_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"The decisions could not be applied ({type(error).__name__}).",
        ) from None
    return build_run_view(run_id, result.state, paused=result.paused, runnable=result.runnable)


@router.get("/runs")
def list_runs(request: Request) -> dict[str, Any]:
    """The caller's own runs."""
    session_id = read_session(request)
    if not session_id:
        return {"runs": []}
    return {
        "runs": [
            {
                "run_id": record.run_id,
                "created_at": record.created_at.isoformat(),
                "files": list(record.file_names),
                "source_rows": record.source_rows,
            }
            for record in registry.list_runs(session_id)
        ]
    }


@router.get("/runs/{run_id}/proposed-rules")
def read_proposed_rules(run_id: str, request: Request) -> dict[str, Any]:
    """Rules the model drafted from this run's decisions, awaiting approval.

    A GET, so it never mutates: declining a proposal is simply not accepting it,
    and needs no route of its own.
    """
    _owned_run(run_id, request)
    state = runner.read_state(run_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such run.")
    return {
        "proposals": [
            {
                "proposal_id": proposal.proposal_id,
                "rule": rule_routes.rule_view(proposal.rule, version=0, editable=False),
                "scope": proposal.scope.value,
                "rationale": proposal.rationale,
                "pre_approved": proposal.pre_approved,
            }
            for proposal in state.get("proposed_rules", ())
        ]
    }


@router.post("/runs/{run_id}/proposed-rules/{proposal_id}/accept")
def accept_proposed_rule(run_id: str, proposal_id: str, request: Request) -> dict[str, Any]:
    """Turn one drafted proposal into a rule the caller owns.

    Idempotent by content rather than by proposal id: accepting the same
    proposal twice, or two proposals that happened to draft the same rule, must
    store it once. Checking the caller's existing rules for an identical one is
    simpler than tracking which proposals were already accepted, and it is the
    same guarantee either way.
    """
    require_same_origin(request)
    record = _owned_run(run_id, request)
    session_id = record.owner_session_id
    state = runner.read_state(run_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such run.")

    proposal = next(
        (p for p in state.get("proposed_rules", ()) if p.proposal_id == proposal_id),
        None,
    )
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such proposal.")

    try:
        existing = next(
            (
                candidate
                for candidate in rule_store.list_rules(session_id)
                if _same_rule(candidate.rule, proposal.rule)
            ),
            None,
        )
        stored = (
            existing if existing is not None else rule_store.create_rule(session_id, proposal.rule)
        )
    except rule_store.RuleLimitError as limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(limit)
        ) from None
    except Exception as error:
        logger.warning("rule store unavailable: %s", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rules are unavailable right now.",
        ) from None

    return rule_routes.rule_view(stored.rule, version=stored.version, editable=True)


def _same_rule(a: Rule, b: Rule) -> bool:
    """Whether two rules would behave identically, ignoring identity and provenance.

    Used to recognise a proposal already accepted, so approving it twice — or
    approving two proposals that happened to draft the same rule — cannot create
    a duplicate.
    """
    fields = ("kind", "header", "field_name", "value", "canonical", "date_order", "schema_id")
    return all(getattr(a, name) == getattr(b, name) for name in fields)
