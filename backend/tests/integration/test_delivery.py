"""Delivery against a real HTTP server.

These run over a live socket rather than calling the handler, because the
behaviour worth proving only exists across a network boundary: a lost response,
a replayed request, a key reused with different data. The destination's receipt
store is a real collection, so a run needs MONGODB_URI configured.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import uvicorn

from schemabridge.domain.models import CanonicalRecord, DeliveryOutcome, DeliveryState
from schemabridge.domain.target import BUILTIN_SCHEMA
from schemabridge.server.target_client import (
    build_client,
    idempotency_key,
)
from schemabridge.server.target_client import (
    build_payload as _build_payload,
)
from schemabridge.server.target_client import (
    deliver_record as _deliver_record,
)


def build_payload(record_: CanonicalRecord) -> dict[str, Any]:
    """Payload for the built-in template, which these deliveries target."""
    return _build_payload(record_, schema=BUILTIN_SCHEMA)


def deliver_record(*args: Any, **kwargs: Any) -> Any:
    """Deliver against the built-in template unless a case names another."""
    kwargs.setdefault("schema", BUILTIN_SCHEMA)
    return _deliver_record(*args, **kwargs)


pytestmark = pytest.mark.skipif(
    not os.environ.get("MONGODB_URI"),
    reason="needs MONGODB_URI; the destination stores receipts durably",
)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


@pytest.fixture(scope="module")
def origin() -> Iterator[str]:
    """A real server on a real port."""
    from main import app

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 20
    while time.time() < deadline and not server.started:
        time.sleep(0.05)
    if not server.started:  # pragma: no cover
        pytest.fail("the test server did not start")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=10)


def record(employee_id: str, *, revision: int = 1) -> CanonicalRecord:
    return CanonicalRecord(
        id=f"rec:{employee_id.lower()}",
        revision=revision,
        identity_key=employee_id.lower(),
        values={
            "employeeId": employee_id,
            "fullName": "Priya Sharma",
            "workEmail": f"{employee_id.lower()}@example.com",
            "startDate": "2026-01-15",
        },
    )


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    with build_client() as http_client:
        yield http_client


def unique(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000) % 1_000_000}"


class TestSuccessfulDelivery:
    def test_a_valid_record_is_accepted(self, client: httpx.Client, origin: str) -> None:
        result = deliver_record(client, unique("run"), record("E-2001"), request_origin=origin)
        assert result.outcome is DeliveryOutcome.SUCCEEDED
        assert result.state is DeliveryState.SUCCEEDED
        assert result.status_code == 201
        assert result.target_id


class TestIdempotency:
    def test_replaying_a_request_does_not_create_a_second_record(
        self, client: httpx.Client, origin: str
    ) -> None:
        """The crash-window case.

        If the engine sent a record and never saw the response, it must be able
        to send the identical request again. The destination has to recognise it
        and reconcile rather than duplicate.
        """
        run_id = unique("run")
        employee = record("E-2002")

        first = deliver_record(client, run_id, employee, request_origin=origin)
        second = deliver_record(client, run_id, employee, request_origin=origin)

        assert first.outcome is DeliveryOutcome.SUCCEEDED
        assert second.outcome is DeliveryOutcome.SUCCEEDED
        # Same destination identity, and the replay is distinguishable.
        assert second.target_id == first.target_id
        assert first.status_code == 201
        assert second.status_code == 200
        assert "reconciled" in second.detail.lower()

    def test_the_key_is_tied_to_the_revision(self, origin: str) -> None:
        """A corrected record is new data, not a replay of the old version."""
        run_id = unique("run")
        before = record("E-2003", revision=1)
        after = record("E-2003", revision=2)
        assert idempotency_key(run_id, before) != idempotency_key(run_id, after)

    def test_reusing_a_key_for_different_data_is_refused(
        self, client: httpx.Client, origin: str
    ) -> None:
        """Otherwise the destination would hold two versions of one identity."""
        run_id = unique("run")
        original = record("E-2004")
        deliver_record(client, run_id, original, request_origin=origin)

        # Same run, same record id and revision, but altered content.
        tampered = original.model_copy(
            update={"values": {**original.values, "fullName": "Someone Else"}}
        )
        result = deliver_record(client, run_id, tampered, request_origin=origin)

        assert result.outcome is DeliveryOutcome.FAILED
        assert result.status_code == 409


class TestTransientFailure:
    def test_a_transient_failure_schedules_a_retry(self, client: httpx.Client, origin: str) -> None:
        result = deliver_record(
            client,
            unique("run"),
            record("E-2005"),
            request_origin=origin,
            attempt_number=1,
            demo_headers={"x-demo-fail-once": "1"},
        )
        assert result.state is DeliveryState.RETRY_WAIT
        assert result.status_code == 503
        # The destination asked for a delay, and we honour it.
        assert result.next_attempt_at is not None

    def test_the_retry_then_succeeds(self, client: httpx.Client, origin: str) -> None:
        """The demo's headline recovery: fails once, then goes through."""
        run_id = unique("run")
        employee = record("E-2006")

        first = deliver_record(
            client,
            run_id,
            employee,
            request_origin=origin,
            attempt_number=1,
            demo_headers={"x-demo-fail-once": "1"},
        )
        assert first.state is DeliveryState.RETRY_WAIT

        # The retry carries no failure header, as the real second attempt would.
        second = deliver_record(client, run_id, employee, request_origin=origin, attempt_number=2)
        assert second.outcome is DeliveryOutcome.SUCCEEDED
        assert second.target_id

    def test_the_retry_budget_is_finite(self, client: httpx.Client, origin: str) -> None:
        """A record that keeps failing needs a person, not more attempts."""
        result = deliver_record(
            client,
            unique("run"),
            record("E-2007"),
            request_origin=origin,
            attempt_number=3,  # already at the cap
            demo_headers={"x-demo-fail-once": "1"},
        )
        assert result.state is DeliveryState.FAILED
        assert result.next_attempt_at is None


class TestPermanentFailure:
    def test_a_rejection_is_actionable_not_retried(self, client: httpx.Client, origin: str) -> None:
        result = deliver_record(
            client,
            unique("run"),
            record("E-2008"),
            request_origin=origin,
            demo_headers={"x-demo-reject": "1"},
        )
        assert result.state is DeliveryState.FAILED
        assert result.status_code == 422
        # The reviewer is told why, in words they can act on.
        assert "rejected" in result.detail.lower()

    def test_an_invalid_record_is_refused_by_the_destination(
        self, client: httpx.Client, origin: str
    ) -> None:
        """The destination enforces its own contract rather than trusting us."""
        broken = record("E-2009").model_copy(
            update={"values": {"employeeId": "E-2009", "fullName": "No Email"}}
        )
        result = deliver_record(client, unique("run"), broken, request_origin=origin)
        assert result.state is DeliveryState.FAILED
        assert result.status_code == 422


class TestSecurity:
    def test_the_endpoint_requires_the_connector_secret(self, origin: str) -> None:
        with httpx.Client(timeout=10) as raw:
            response = raw.post(
                f"{origin}/api/mock/destination/employees",
                json=build_payload(record("E-2010")),
                headers={"Idempotency-Key": "no-secret"},
            )
        assert response.status_code == 401

    def test_an_idempotency_key_is_mandatory(self, origin: str) -> None:
        from schemabridge.server.config import get_settings

        with httpx.Client(timeout=10) as raw:
            response = raw.post(
                f"{origin}/api/mock/destination/employees",
                json=build_payload(record("E-2011")),
                headers={"Authorization": f"Bearer {get_settings().target_api_secret}"},
            )
        assert response.status_code == 400


class TestUnknownOutcome:
    def test_a_timeout_is_unknown_rather_than_failed(self, origin: str) -> None:
        """A timed-out request may well have been accepted.

        Calling that a failure and retrying without an idempotency key is exactly
        how duplicates appear in a destination system.
        """
        with httpx.Client(timeout=httpx.Timeout(0.001)) as impatient:
            result = deliver_record(
                impatient, unique("run"), record("E-2012"), request_origin=origin
            )
        assert result.outcome is DeliveryOutcome.UNKNOWN
        assert result.state is DeliveryState.RETRY_WAIT
        assert "unknown" in result.detail.lower()

    def test_reconciling_after_an_unknown_outcome_finds_the_record(
        self, client: httpx.Client, origin: str
    ) -> None:
        """Ask the destination what it holds, rather than assuming."""
        from schemabridge.server.config import get_settings

        run_id = unique("run")
        employee = record("E-2013")
        deliver_record(client, run_id, employee, request_origin=origin)

        key = idempotency_key(run_id, employee)
        response = client.get(
            f"{origin}/api/mock/destination/employees/{key}",
            headers={"Authorization": f"Bearer {get_settings().target_api_secret}"},
        )
        assert response.status_code == 200
        assert response.json()["targetId"]


class TestPayloadShape:
    def test_absent_optional_fields_are_omitted(self) -> None:
        """ "Not supplied" and "explicitly empty" are different statements."""
        payload = build_payload(
            record("E-2014").model_copy(
                update={
                    "values": {
                        **record("E-2014").values,
                        "endDate": None,
                        "department": "",
                    }
                }
            )
        )
        assert "endDate" not in payload
        assert "department" not in payload
        assert payload["employeeId"] == "E-2014"


class TestConcurrency:
    def test_two_simultaneous_deliveries_create_one_record(
        self, client: httpx.Client, origin: str
    ) -> None:
        """Only one may win, and the other must reconcile to the same identity."""
        from concurrent.futures import ThreadPoolExecutor

        run_id = unique("run")
        employee = record("E-2015")

        def send() -> Any:
            with build_client() as own_client:
                return deliver_record(own_client, run_id, employee, request_origin=origin)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: send(), range(2)))

        assert all(r.outcome is DeliveryOutcome.SUCCEEDED for r in results)
        assert results[0].target_id == results[1].target_id
        # Exactly one call created it; the other reconciled.
        assert sorted(r.status_code or 0 for r in results) == [200, 201]
