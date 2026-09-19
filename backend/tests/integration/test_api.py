"""The migration API, exercised as the browser uses it.

A real client over the real app: upload, poll, resolve, deliver. These need a
database because the workflow's state and the destination's receipts are both
persisted.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn

pytestmark = pytest.mark.skipif(
    not os.environ.get("MONGODB_URI"),
    reason="needs MONGODB_URI; run state and receipts are persisted",
)

SAMPLES = Path(__file__).resolve().parents[2] / "fixtures" / "samples"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


@pytest.fixture(scope="module")
def origin() -> Iterator[str]:
    """A real server on a real port.

    The engine delivers to its own stub over HTTP, so an in-process test client
    is not enough: nothing would be listening on the origin it resolves. Running
    a real server means these tests exercise the same path production does.
    """
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


@pytest.fixture
def client(origin: str) -> Iterator[httpx.Client]:
    """A client that keeps cookies, so it behaves like one visitor's browser."""
    with httpx.Client(base_url=origin, timeout=90) as http_client:
        yield http_client


def upload(client: httpx.Client, *names: str) -> Any:
    files = [
        (
            "files",
            (
                name,
                (SAMPLES / name).read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                if name.endswith(".xlsx")
                else "text/csv",
            ),
        )
        for name in names
    ]
    return client.post("/api/runs", files=files)


#: Upper bound on advance calls in a test. Execution is bounded per request, so a
#: run needs several; a fixed ceiling keeps a stuck run from hanging the suite.
_MAX_ADVANCES = 40


def drive(client: httpx.Client, run: Any) -> Any:
    """Advance a run until it finishes or stops to ask a person something.

    The API executes a bounded number of graph supersteps per request, so that
    creating a run returns before any work has happened and progress is
    observable while it does. Every caller therefore has to drive the run, which
    is exactly what the browser does.
    """
    run_id = run["run_id"]
    for _ in range(_MAX_ADVANCES):
        if run["paused"] or not run["runnable"]:
            return run
        response = client.post(f"/api/runs/{run_id}/advance")
        assert response.status_code == 200, response.text
        run = response.json()
    raise AssertionError(f"run {run_id} did not settle within {_MAX_ADVANCES} advances")


def start(client: httpx.Client, *names: str) -> Any:
    """Upload and run until something needs a person, or it is done."""
    response = upload(client, *names)
    assert response.status_code == 201, response.text
    return drive(client, response.json())


def _any_decision(issue: Any) -> dict[str, Any]:
    """A decision that moves an issue forward, preferring a concrete value."""
    concrete = next(
        (o for o in issue["options"] if o.get("value") or o.get("target")), None
    )
    if concrete:
        return {"action": "approve", "option_id": concrete["id"], "value": concrete.get("value")}
    excluding = next((o for o in issue["options"] if o["id"].startswith("exclude:")), None)
    if excluding:
        return {"action": "exclude", "option_id": excluding["id"], "note": "Cannot be migrated."}
    return {"action": "approve", "option_id": issue["options"][0]["id"]}


class TestSchemaEndpoint:
    def test_publishes_the_target_contract(self, client: httpx.Client) -> None:
        body = client.get("/api/schema").json()
        names = {field["name"] for field in body["fields"]}
        assert {"employeeId", "fullName", "workEmail", "startDate"} <= names
        # The UI needs the limits to explain a rejection before uploading.
        assert body["limits"]["max_files"] >= 1


class TestAcceptance:
    def test_creating_a_run_returns_before_the_work_is_done(
        self, client: httpx.Client
    ) -> None:
        """The upload is accepted; nothing is migrated yet.

        Doing the whole migration inside the create request is what made the run
        screen open on an already-finished run, with no way to watch the agent
        work. The response must arrive with the sources parsed and no more.
        """
        response = upload(client, "employees-clean.csv")
        assert response.status_code == 201, response.text
        run = response.json()

        assert run["run_id"]
        assert run["counters"]["source_rows"] == 3
        # Accepted, not processed: no mapping, no delivery, and nobody asked.
        assert run["phase"] == "ingested"
        assert not run["paused"]
        assert run["counters"]["delivered"] == 0
        assert run["counters"]["auto_mapped"] == 0
        # There is work left, and the caller is told so.
        assert run["runnable"]

    def test_work_becomes_visible_before_the_run_finishes(
        self, client: httpx.Client
    ) -> None:
        """Progress is observable part-way through, not only at the end."""
        created = upload(client, "employees-clean.csv").json()
        run_id = created["run_id"]

        # One bounded step, then look. Something has happened, and it is not over.
        after_one = client.post(f"/api/runs/{run_id}/advance").json()
        assert after_one["events"], "no committed events after the first step"
        assert after_one["phase"] != "ingested"

        # A plain read sees the same committed state without advancing anything.
        observed = client.get(f"/api/runs/{run_id}").json()
        assert observed["phase"] == after_one["phase"]
        assert observed["counters"] == after_one["counters"]

        # And driving on reaches the end.
        final = drive(client, after_one)
        assert final["phase"] in {"complete", "complete_with_failures"}


class TestCleanRun:
    def test_a_clean_file_completes_without_asking(self, client: httpx.Client) -> None:
        run = start(client, "employees-clean.csv")

        # No human input needed, and delivery happened on its own.
        assert not run["paused"]
        assert run["counters"]["awaiting_review"] == 0
        assert run["phase"] in {"complete", "complete_with_failures"}
        assert run["counters"]["delivered"] == 3
        assert run["counters"]["escalated"] == 0

    def test_the_activity_feed_explains_what_happened(self, client: httpx.Client) -> None:
        run = start(client, "employees-clean.csv")
        actions = {event["action"] for event in run["events"]}
        assert "mapping_applied" in actions
        assert "records_reconciled" in actions
        assert "delivery_succeeded" in actions
        # Every event carries a reason a non-technical reader can follow.
        assert all(event["reason"] for event in run["events"])


class TestMessyRun:
    def test_it_pauses_with_actionable_escalations(self, client: httpx.Client) -> None:
        run = start(client, "employees-legacy.csv", "employees-hr-export.csv")

        assert run["paused"]
        blocking = [i for i in run["issues"] if i["blocking"] and i["status"] == "open"]
        assert blocking
        for issue in blocking:
            assert issue["reason"]
            # No dead ends: the reviewer always has a way forward.
            assert issue["options"]

    def test_automatic_work_outnumbers_escalations(self, client: httpx.Client) -> None:
        run = start(client, "employees-legacy.csv", "employees-hr-export.csv")
        counters = run["counters"]
        assert counters["auto_mapped"] > counters["escalated"]
        # Safe fixes were applied without asking.
        assert counters["repairs"] > 0

    def test_resolving_the_queue_finishes_the_run(self, client: httpx.Client) -> None:
        created = start(client, "employees-legacy.csv", "employees-hr-export.csv")
        run_id = created["run_id"]

        decisions: dict[str, Any] = {}
        for issue in created["issues"]:
            if not (issue["blocking"] and issue["status"] == "open"):
                continue
            concrete = next(
                (o for o in issue["options"] if o.get("value") or o.get("target")), None
            )
            if concrete:
                decisions[issue["id"]] = {"action": "correct", "option_id": concrete["id"]}
            else:
                excluding = next(
                    (o for o in issue["options"] if o["id"].startswith("exclude:")), None
                )
                decisions[issue["id"]] = {
                    "action": "exclude",
                    "option_id": excluding["id"] if excluding else None,
                    "note": "Cannot be migrated as supplied.",
                }

        # Decisions can arrive one at a time or together; either way the run
        # then has to be driven on, and may stop again for something new.
        resolved = client.post(f"/api/runs/{run_id}/resolve", json=decisions)
        assert resolved.status_code == 200, resolved.text
        final = drive(client, resolved.json())

        # Anything still open is a question the earlier decisions uncovered.
        while final["paused"]:
            remaining = {
                issue["id"]: _any_decision(issue)
                for issue in final["issues"]
                if issue["blocking"] and issue["status"] == "open"
            }
            assert remaining, "paused with nothing open to answer"
            final = drive(
                client, client.post(f"/api/runs/{run_id}/resolve", json=remaining).json()
            )

        assert final["counters"]["awaiting_review"] == 0
        assert final["phase"] in {"complete", "complete_with_failures"}
        assert final["counters"]["delivered"] > 0
        # Every record reaches a terminal state, and nothing vanishes silently.
        counters = final["counters"]
        accounted = counters["delivered"] + counters["failed"] + counters["excluded"]
        assert counters["retrying"] == 0, "a retry was left pending"
        assert accounted == counters["records"]

    def test_the_decision_is_attributed_to_the_reviewer(self, client: httpx.Client) -> None:
        created = start(client, "employees-legacy.csv", "employees-hr-export.csv")
        run_id = created["run_id"]
        issue = next(i for i in created["issues"] if i["blocking"] and i["options"])
        option = next((o for o in issue["options"] if o.get("target") or o.get("value")), None)
        if option is None:
            pytest.skip("no concrete option in this fixture run")

        final = client.post(
            f"/api/runs/{run_id}/resolve",
            json={issue["id"]: {"action": "correct", "option_id": option["id"]}},
        ).json()

        reviewer_events = [e for e in final["events"] if e["actor"] == "reviewer"]
        assert reviewer_events
        resolved = [i for i in final["issues"] if i["resolution"]]
        assert resolved


class TestDeliveryOutcomes:
    def test_a_transient_failure_is_retried_and_a_rejection_reported(
        self, client: httpx.Client
    ) -> None:
        """The legacy fixture contains one record that fails once and one rejected."""
        created = start(client, "employees-legacy.csv")
        run_id = created["run_id"]

        while created["paused"]:
            decisions = {}
            for issue in created["issues"]:
                if not (issue["blocking"] and issue["status"] == "open"):
                    continue
                excluding = next(
                    (o for o in issue["options"] if o["id"].startswith("exclude:")), None
                )
                concrete = next(
                    (o for o in issue["options"] if o.get("value") or o.get("target")), None
                )
                decisions[issue["id"]] = (
                    {"action": "correct", "option_id": concrete["id"]}
                    if concrete
                    else {"action": "exclude", "option_id": excluding["id"] if excluding else None}
                )
            created = drive(
                client, client.post(f"/api/runs/{run_id}/resolve", json=decisions).json()
            )

        actions = [e["action"] for e in created["events"]]
        assert "delivery_attempted" in actions
        # One record is rejected permanently by the destination.
        assert created["counters"]["failed"] >= 1
        assert created["counters"]["delivered"] >= 1

        failed = [r for r in created["records"] if r["disposition"] == "failed"]
        assert failed
        delivered = [r for r in created["records"] if r["disposition"] == "delivered"]
        # A delivered record carries the destination's own identifier.
        assert all(record["target_id"] for record in delivered)


class TestOwnership:
    def test_another_visitor_cannot_read_a_run(self, client: httpx.Client, origin: str) -> None:
        run_id = upload(client, "employees-clean.csv").json()["run_id"]

        # A fresh client means a fresh session: the run id alone must not grant
        # access.
        with httpx.Client(base_url=origin, timeout=30) as stranger:
            response = stranger.get(f"/api/runs/{run_id}")
        assert response.status_code == 404

    def test_another_visitor_cannot_resolve_a_run(self, client: httpx.Client, origin: str) -> None:
        created = start(client, "employees-legacy.csv", "employees-hr-export.csv")
        run_id = created["run_id"]
        issue_id = created["issues"][0]["id"]

        with httpx.Client(base_url=origin, timeout=30) as stranger:
            response = stranger.post(
                f"/api/runs/{run_id}/resolve",
                json={issue_id: {"action": "approve"}},
            )
        assert response.status_code == 404

    def test_a_session_sees_only_its_own_runs(self, client: httpx.Client, origin: str) -> None:
        upload(client, "employees-clean.csv")
        mine = {run["run_id"] for run in client.get("/api/runs").json()["runs"]}
        assert mine

        with httpx.Client(base_url=origin, timeout=30) as stranger:
            theirs = {run["run_id"] for run in stranger.get("/api/runs").json()["runs"]}
        assert not (mine & theirs)


class TestUploadValidation:
    def test_an_unsupported_file_type_is_refused(self, client: httpx.Client) -> None:
        response = client.post(
            "/api/runs", files=[("files", ("notes.pdf", b"%PDF-1.4", "application/pdf"))]
        )
        assert response.status_code == 400
        assert "csv" in response.json()["detail"].lower()

    def test_an_empty_upload_is_refused(self, client: httpx.Client) -> None:
        response = client.post("/api/runs", files=[("files", ("empty.csv", b"", "text/csv"))])
        assert response.status_code == 400

    def test_too_many_files_are_refused(self, client: httpx.Client) -> None:
        payload = b"employeeId\nE-1\n"
        response = client.post(
            "/api/runs",
            files=[("files", (f"f{i}.csv", payload, "text/csv")) for i in range(5)],
        )
        assert response.status_code == 400

    def test_a_file_with_no_data_rows_explains_itself(self, client: httpx.Client) -> None:
        response = client.post(
            "/api/runs",
            files=[("files", ("headers.csv", b"employeeId,fullName\n", "text/csv"))],
        )
        assert response.status_code == 400
        assert "no data rows" in response.json()["detail"].lower()


class TestPollingIsSafe:
    def test_reading_a_run_does_not_change_it(self, client: httpx.Client) -> None:
        """The UI polls constantly; a GET with side effects would be a bug."""
        created = upload(client, "employees-legacy.csv", "employees-hr-export.csv").json()
        run_id = created["run_id"]

        first = client.get(f"/api/runs/{run_id}").json()
        second = client.get(f"/api/runs/{run_id}").json()

        assert first["phase"] == second["phase"]
        assert first["latest_seq"] == second["latest_seq"]
        assert len(first["issues"]) == len(second["issues"])

    def test_events_can_be_fetched_incrementally(self, client: httpx.Client) -> None:
        created = start(client, "employees-clean.csv")
        run_id = created["run_id"]

        everything = client.get(f"/api/runs/{run_id}").json()
        assert everything["events"]

        cursor = everything["events"][2]["seq"]
        later = client.get(f"/api/runs/{run_id}?since={cursor}").json()
        assert all(event["seq"] > cursor for event in later["events"])
        assert len(later["events"]) < len(everything["events"])
