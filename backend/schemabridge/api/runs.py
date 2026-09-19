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

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile, status
from starlette.concurrency import run_in_threadpool

from schemabridge.api.views import RunView, build_run_view, target_schema_view
from schemabridge.domain.models import (
    ColumnProfile,
    RunPhase,
    SourceColumn,
    SourceFile,
    SourceRow,
)
from schemabridge.graph import runner
from schemabridge.ingest.csv_source import parse_csv
from schemabridge.ingest.limits import INGEST_LIMITS
from schemabridge.ingest.profile import profile_columns
from schemabridge.ingest.xlsx_source import parse_xlsx
from schemabridge.server import runs as registry
from schemabridge.server.budget import usage_today
from schemabridge.server.sessions import ensure_session, read_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["migration"])

#: Runs one visitor may start per day. Generous for a demo, bounded enough that
#: the shared cluster and inference allowance survive an enthusiastic visitor.
_MAX_RUNS_PER_SESSION = 25

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


def _same_origin(request: Request) -> None:
    """Reject cross-site mutations.

    The session cookie is SameSite=Lax, which covers most of this; checking the
    Origin header closes the gap for requests that arrive with one.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return
    expected = f"{request.url.scheme}://{request.url.netloc}"
    forwarded_host = request.headers.get("x-forwarded-host")
    allowed = {expected}
    if forwarded_host:
        allowed.add(f"https://{forwarded_host}")
        allowed.add(f"http://{forwarded_host}")
    if origin.rstrip("/") not in {value.rstrip("/") for value in allowed}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Cross-origin request refused."
        )


def _request_origin(request: Request) -> str:
    """Where outbound delivery should go when no origin is configured."""
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        scheme = request.headers.get("x-forwarded-proto", "https").split(",")[0].strip()
        return f"{scheme}://{forwarded_host}"
    return f"{request.url.scheme}://{request.url.netloc}"


@router.get("/schema")
def read_schema() -> dict[str, Any]:
    """The target contract the migration maps onto."""
    # asdict, not vars: the limits are a slotted dataclass and have no __dict__.
    return {"fields": target_schema_view(), "limits": asdict(INGEST_LIMITS)}


@router.get("/usage")
def read_usage() -> dict[str, int]:
    """Shared inference allowance, so the UI can explain a refusal honestly."""
    try:
        used, limit = usage_today()
    except Exception:
        return {"used": 0, "limit": 0}
    return {"used": used, "limit": limit}


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    request: Request,
    response: Response,
    files: Annotated[list[UploadFile], File()],
) -> RunView:
    """Ingest source files and start a migration."""
    _same_origin(request)
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

    try:
        if registry.count_runs_for_session(session_id) >= _MAX_RUNS_PER_SESSION:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="You have started a lot of migrations today. Try again tomorrow.",
            )
    except HTTPException:
        raise
    except Exception as error:
        logger.warning("run registry unavailable: %s", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The database is unavailable, so a migration cannot be started.",
        ) from None

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

    run_id = registry.new_run_id()
    registry.create_run(run_id, session_id, tuple(names), len(rows))

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
        "phase": RunPhase.INGESTED,
        "request_origin": _request_origin(request),
        "demo_delivery": _DEMO_DELIVERY,
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
        runnable=not state.get("_paused"),
        since=since,
    )


@router.post("/runs/{run_id}/advance")
async def advance_run(run_id: str, request: Request) -> RunView:
    """Do the next bounded piece of work."""
    _same_origin(request)
    _owned_run(run_id, request)
    try:
        result = await run_in_threadpool(runner.advance, run_id)
    except Exception as error:
        logger.exception("advance failed for %s", run_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"The migration could not continue ({type(error).__name__}).",
        ) from None
    return build_run_view(run_id, result.state, paused=result.paused, runnable=result.runnable)


@router.post("/runs/{run_id}/resolve")
async def resolve_run(run_id: str, request: Request, decisions: dict[str, Any]) -> RunView:
    """Apply the reviewer's decisions and continue.

    Each decision names an issue and an action. Nothing here trusts the browser
    to have applied anything: the graph re-derives records from the decision and
    revalidates.
    """
    _same_origin(request)
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
