"""A stand-in for the client's destination system.

It behaves the way a real integration target does, because the interesting part
of delivery is not the happy path — it is what happens when a request fails
halfway. So this stub:

- requires a shared secret, so it is not an open write endpoint;
- enforces idempotency, returning the original receipt on a replay;
- refuses a reused key carrying different data;
- validates against the target schema and rejects what does not conform;
- fails one designated record once, then accepts it, to exercise retry;
- rejects another permanently, to exercise a failure a human must act on.

The failure behaviour is driven by an explicit header the engine never sends on
its own, rather than by magic employee ids, so production logic contains no
special cases for test data.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from schemabridge.domain.validate import validate_employee
from schemabridge.server.config import get_settings
from schemabridge.server.receipts import (
    PayloadConflictError,
    find_receipt,
    store_receipt,
)

router = APIRouter(prefix="/api/mock/destination", tags=["mock destination"])

#: Records whose first delivery attempt fails with a retryable error. Configured
#: per request by the demo, never inferred from the data.
_FAIL_ONCE_HEADER = "x-demo-fail-once"
_REJECT_HEADER = "x-demo-reject"

#: Keys already failed once, so the second attempt can succeed.
_failed_once: set[str] = set()


def _require_secret(provided: str | None) -> None:
    """Reject anything without the configured shared secret."""
    settings = get_settings()
    expected = settings.target_api_secret
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The destination connector is not configured.",
        )
    # Constant-time comparison: a timing side channel here would leak the secret.
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid connector credentials.",
        )


def payload_hash(payload: dict[str, Any]) -> str:
    """Stable hash of a payload, so a replay can be recognised as identical."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


@router.post("/employees", status_code=status.HTTP_201_CREATED)
async def create_employee(
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
    fail_once: Annotated[str | None, Header(alias=_FAIL_ONCE_HEADER)] = None,
    reject: Annotated[str | None, Header(alias=_REJECT_HEADER)] = None,
) -> JSONResponse:
    """Accept one employee record."""
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    _require_secret(token)

    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An Idempotency-Key header is required.",
        )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Body must be JSON."
        ) from None

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Body must be a JSON object."
        )

    # A permanent rejection, checked before idempotency so it never yields a
    # receipt for something the destination will not hold.
    if reject:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The destination rejected this record: it fails a downstream business rule.",
        )

    # A transient failure the first time only, so a retry demonstrably succeeds.
    if fail_once and idempotency_key not in _failed_once:
        _failed_once.add(idempotency_key)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "The destination is temporarily unavailable."},
            headers={"Retry-After": "1"},
        )

    # The destination enforces its own contract; it does not trust the caller.
    outcome = validate_employee(payload)
    if not outcome.valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "The record does not conform to the destination schema.",
                "errors": [
                    {"field": error.field_name, "message": error.message}
                    for error in outcome.errors
                ],
            },
        )

    digest = payload_hash(payload)
    target_id = f"DEST-{digest[:10].upper()}"

    try:
        receipt = store_receipt(idempotency_key, target_id, digest, payload)
    except PayloadConflictError as conflict:
        # Reusing a key for different data would let the destination hold two
        # versions of one identity. Refuse rather than guess which is correct.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(conflict)) from None

    return JSONResponse(
        # 200 rather than 201 on a replay, so the caller can tell a fresh
        # acceptance from a reconciled one.
        status_code=status.HTTP_201_CREATED if receipt.created else status.HTTP_200_OK,
        content={
            "targetId": receipt.target_id,
            "created": receipt.created,
            "receivedAt": receipt.created_at.isoformat(),
        },
    )


@router.get("/employees/{idempotency_key}")
async def read_receipt(
    idempotency_key: str,
    authorization: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """Look up whether a record was accepted.

    This is how the engine resolves an unknown outcome: if the response to a
    write was lost, asking the destination is more reliable than assuming.
    """
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    _require_secret(token)

    receipt = find_receipt(idempotency_key)
    if receipt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such record.")
    return JSONResponse(
        content={
            "targetId": receipt.target_id,
            "created": False,
            "receivedAt": receipt.created_at.isoformat(),
        }
    )
