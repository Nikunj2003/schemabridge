"""Operator-only migration and LLM evidence endpoints."""

from __future__ import annotations

import hmac
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from schemabridge.graph import runner
from schemabridge.server import model_exchanges, runs
from schemabridge.server.config import get_settings

router = APIRouter(prefix="/api/observability", tags=["observability"])


def _require_operator(request: Request) -> None:
    configured = get_settings().observability_api_secret
    supplied = request.headers.get("x-schemabridge-operator-secret", "")
    if not configured or not hmac.compare_digest(supplied, configured):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authorized.")


@router.get("/status")
def read_status(request: Request) -> dict[str, Any]:
    _require_operator(request)
    settings = get_settings()
    return {
        "langfuse_enabled": settings.langfuse_enabled,
        "langfuse_configured": settings.langfuse_configured,
        "nvidia_requests_per_minute": settings.nvidia_requests_per_minute,
        "model_exchange_capture": True,
    }


@router.get("/runs")
def list_observable_runs(request: Request, limit: int = 50) -> dict[str, Any]:
    _require_operator(request)
    capped = min(max(limit, 1), 100)
    rows = model_exchanges.list_recent(limit=capped)
    return {"model_exchanges": [_summary(row) for row in rows]}


@router.get("/runs/{run_id}")
def read_observable_run(run_id: str, request: Request) -> dict[str, Any]:
    _require_operator(request)
    manifest = runs.find_run(run_id)
    if manifest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such run.")
    state = runner.read_state(run_id, manifest.workspace_kind)
    return {
        "run": {
            "run_id": manifest.run_id,
            "workspace_kind": manifest.workspace_kind,
            "created_at": manifest.created_at.isoformat(),
            "expires_at": manifest.expires_at.isoformat(),
            "files": list(manifest.file_names),
            "source_rows": manifest.source_rows,
        },
        "audit": [
            event.model_dump(mode="json") if hasattr(event, "model_dump") else event
            for event in (state or {}).get("events", ())
        ],
        "model_exchanges": [_detail(row) for row in model_exchanges.list_for_run(run_id)],
    }


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    created_at = row.get("created_at")
    return {
        "exchange_id": str(row.get("_id", "")),
        "run_id": str(row.get("run_id", "")),
        "operation": str(row.get("operation", "")),
        "model": str(row.get("model", "")),
        "status": str(row.get("status", "")),
        "attempts": int(row.get("attempts", 0)),
        "created_at": created_at.isoformat() if isinstance(created_at, datetime) else None,
        "latency_ms": row.get("latency_ms"),
    }


def _detail(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **_summary(row),
        "request": row.get("request"),
        "response": row.get("response"),
        "error": row.get("error"),
    }
