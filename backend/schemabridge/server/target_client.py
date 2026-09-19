"""Delivering records to the destination system.

Real HTTP, even though the stub lives in the same deployment. Calling the handler
directly would be faster and would prove nothing: the interesting failures —
timeouts, lost responses, partial success — only exist across a network boundary.

The important distinction here is between *failed* and *unknown*. If a request
times out, the destination may well have accepted the record; treating that as a
failure and retrying naively is how duplicates get created. So every request
carries an idempotency key derived from the record and its revision, and an
uncertain outcome is resolved by asking the destination what it holds rather than
by guessing.

This gives at-least-once delivery with idempotent effects. Not exactly-once —
that would require a transaction spanning our database and theirs, which no
integration target offers.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx

from schemabridge.domain.models import (
    CanonicalRecord,
    DeliveryAttempt,
    DeliveryOutcome,
    DeliveryState,
)
from schemabridge.domain.schema import TargetSchema
from schemabridge.server.config import get_settings

logger = logging.getLogger(__name__)

#: Attempts per record, including the first. Small on purpose: a record that
#: fails repeatedly needs a human, not more retries.
MAX_ATTEMPTS = 3

#: Status codes worth retrying. A 4xx other than 429 means the request itself is
#: wrong, so repeating it unchanged cannot help.
_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

#: Names the contract the destination validates against, so a run using a custom
#: schema is not checked against the built-in one.
SCHEMA_HEADER = "X-Target-Schema"


def build_payload(record: CanonicalRecord, *, schema: TargetSchema) -> dict[str, Any]:
    """The record as the destination expects it.

    The field list comes from the run's own schema rather than a constant here.
    A second hardcoded list was the bug waiting to happen: it was checked against
    nothing, so adding a field to the schema would have silently dropped it from
    every delivery.

    Absent optional fields are omitted rather than sent as null, so the
    destination sees "not supplied" instead of "explicitly empty". Values the
    schema does not define are dropped: sending them would invent data the
    destination never asked for, and its contract forbids extra properties.
    """
    payload: dict[str, Any] = {}
    for spec in schema.fields:
        value = record.values.get(spec.name)
        if value is None or value == "":
            continue
        payload[spec.name] = value
    return payload


def payload_hash(payload: dict[str, Any]) -> str:
    """Stable hash, so a replay of the same data is recognisable as such."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def idempotency_key(run_id: str, record: CanonicalRecord) -> str:
    """A key tied to the exact revision being delivered.

    Including the revision matters: if a reviewer corrects a record after a
    failed attempt, that is genuinely new data and must not be reconciled
    against the earlier version's receipt.
    """
    material = f"{run_id}:{record.id}:{record.revision}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """What one attempt achieved."""

    outcome: DeliveryOutcome
    state: DeliveryState
    status_code: int | None
    detail: str
    target_id: str | None = None
    next_attempt_at: datetime | None = None


def _resolve_origin(request_origin: str | None) -> str:
    """Where to send records.

    Configuration first, then the origin of the request being served, then
    loopback. Never a client-supplied header or anything from an uploaded file: a
    destination URL an attacker can influence turns this into a request-forgery
    tool.

    The request origin is only usable when this service serves the public origin
    itself. Behind a proxy — as in local development, where the browser talks to
    the web service on another port — that origin does not route to this
    service's own endpoints, so loopback is the correct fallback rather than a
    last resort.
    """
    settings = get_settings()
    if settings.target_api_origin:
        return settings.target_api_origin
    if request_origin and _is_reachable(request_origin):
        return request_origin.rstrip("/")
    return f"http://127.0.0.1:{settings.port}"


def _is_reachable(origin: str) -> bool:
    """Whether this service can plausibly answer requests on that origin.

    A loopback origin is only ours if it names the port we are listening on;
    anything else on localhost belongs to a different process.
    """
    settings = get_settings()
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return (parsed.port or (443 if parsed.scheme == "https" else 80)) == settings.port
    return bool(parsed.hostname)


def _retry_after(response: httpx.Response) -> datetime | None:
    """Honour the destination's own backoff request when it gives one."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return datetime.now(UTC) + timedelta(seconds=max(0, int(raw)))
    except ValueError:
        return None


def deliver_record(
    client: httpx.Client,
    run_id: str,
    record: CanonicalRecord,
    *,
    schema: TargetSchema,
    request_origin: str | None = None,
    attempt_number: int = 1,
    demo_headers: dict[str, str] | None = None,
) -> DeliveryResult:
    """Send one record, classifying the outcome honestly."""
    settings = get_settings()
    payload = build_payload(record, schema=schema)
    key = idempotency_key(run_id, record)

    headers = {
        "Authorization": f"Bearer {settings.target_api_secret}",
        "Idempotency-Key": key,
        "Content-Type": "application/json",
        # Which contract the destination should enforce. Safe as a header only
        # because this endpoint is authenticated with a server-side shared secret
        # — unlike the delivery origin, which is never taken from a header.
        SCHEMA_HEADER: schema.schema_id,
    }
    if demo_headers:
        headers.update(demo_headers)

    url = f"{_resolve_origin(request_origin)}/api/mock/destination/employees"

    try:
        response = client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException:
        # The request may have been processed. Unknown, not failed.
        return DeliveryResult(
            outcome=DeliveryOutcome.UNKNOWN,
            state=(
                DeliveryState.RETRY_WAIT if attempt_number < MAX_ATTEMPTS else DeliveryState.FAILED
            ),
            status_code=None,
            detail=(
                "The request timed out, so it is unknown whether the destination "
                "accepted the record. The next attempt reuses the same key, which "
                "cannot create a duplicate."
            ),
            next_attempt_at=datetime.now(UTC) + timedelta(seconds=2),
        )
    except httpx.HTTPError as error:
        return DeliveryResult(
            outcome=DeliveryOutcome.UNKNOWN,
            state=(
                DeliveryState.RETRY_WAIT if attempt_number < MAX_ATTEMPTS else DeliveryState.FAILED
            ),
            status_code=None,
            detail=f"The destination could not be reached ({type(error).__name__}).",
            next_attempt_at=datetime.now(UTC) + timedelta(seconds=2),
        )

    if response.status_code in (200, 201):
        body = response.json()
        replayed = response.status_code == 200
        return DeliveryResult(
            outcome=DeliveryOutcome.SUCCEEDED,
            state=DeliveryState.SUCCEEDED,
            status_code=response.status_code,
            detail=(
                "Already present at the destination; reconciled rather than duplicated."
                if replayed
                else "Accepted by the destination."
            ),
            target_id=str(body.get("targetId")),
        )

    if response.status_code in _RETRYABLE_STATUS and attempt_number < MAX_ATTEMPTS:
        return DeliveryResult(
            outcome=DeliveryOutcome.FAILED,
            state=DeliveryState.RETRY_WAIT,
            status_code=response.status_code,
            detail=(
                f"The destination returned {response.status_code}, which is transient. "
                f"Attempt {attempt_number} of {MAX_ATTEMPTS}."
            ),
            next_attempt_at=_retry_after(response)
            or datetime.now(UTC) + timedelta(seconds=2**attempt_number),
        )

    # Everything else needs a person: either the data is wrong, or the retry
    # budget is spent.
    detail = _describe_failure(response, attempt_number)
    return DeliveryResult(
        outcome=DeliveryOutcome.FAILED,
        state=DeliveryState.FAILED,
        status_code=response.status_code,
        detail=detail,
    )


def _describe_failure(response: httpx.Response, attempt_number: int) -> str:
    """A failure message a non-technical reviewer can act on."""
    try:
        body = response.json()
        raw_detail = body.get("detail", body)
    except Exception:
        raw_detail = response.text[:200]

    if isinstance(raw_detail, dict):
        message = str(raw_detail.get("message", "The destination rejected the record."))
        errors = raw_detail.get("errors") or []
        if errors:
            listed = "; ".join(
                str(error.get("message", "")) for error in errors[:3] if isinstance(error, dict)
            )
            return f"{message} {listed}".strip()
        return message

    if response.status_code in _RETRYABLE_STATUS:
        return (
            f"The destination returned {response.status_code} on every one of "
            f"{attempt_number} attempts. It may need checking before retrying."
        )
    return str(raw_detail)


def attempt_record(outcome: DeliveryResult, attempt_number: int) -> DeliveryAttempt:
    """Turn a result into the audit record of that attempt."""
    return DeliveryAttempt(
        attempt=attempt_number,
        status=outcome.status_code,
        outcome=outcome.outcome,
        detail=outcome.detail,
    )


def build_client(timeout_seconds: float = 10.0) -> httpx.Client:
    """An HTTP client for delivery.

    Redirects are disabled: a redirect could move a request carrying the
    connector secret to somewhere it was never meant to go.
    """
    return httpx.Client(
        timeout=httpx.Timeout(timeout_seconds),
        follow_redirects=False,
    )
