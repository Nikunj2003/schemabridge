"""Workspace identity, quota policy, retention, and operator observability.

These cover the boundaries that decide who sees what: an absent bearer token
selects the deliberately shared guest workspace, a supplied-but-invalid one is
refused rather than downgraded, and the operator endpoint is reachable only with
its own server-side secret.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from main import app
from schemabridge.server import auth, migration_quota
from schemabridge.server.config import get_settings


def _request(headers: dict[str, str] | None = None) -> Request:
    raw = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    return Request({"type": "http", "method": "GET", "path": "/api/runs", "headers": raw})


class TestPrincipalResolution:
    def test_no_bearer_token_is_the_shared_guest_workspace(self) -> None:
        principal = auth.principal_from_request(_request())
        assert principal.kind == "anonymous"
        # One fixed id, so every guest deliberately shares the same workspace.
        assert principal.owner_id == auth.anonymous_principal().owner_id

    def test_a_malformed_bearer_token_is_refused_not_downgraded(self) -> None:
        """The dangerous failure is silently answering as the shared workspace."""
        with pytest.raises(HTTPException) as refused:
            auth.principal_from_request(_request({"Authorization": "Bearer not-a-jwt"}))
        assert refused.value.status_code in {401, 503}

    def test_a_non_bearer_scheme_is_refused(self) -> None:
        with pytest.raises(HTTPException) as refused:
            auth.principal_from_request(_request({"Authorization": "Basic abc"}))
        assert refused.value.status_code == 401

    def test_two_subjects_get_different_opaque_owner_ids(self) -> None:
        one = auth._authenticated_principal("auth0|aaa")
        two = auth._authenticated_principal("auth0|bbb")
        assert one.owner_id != two.owner_id
        assert one.kind == "authenticated"
        # The Auth0 subject itself never reaches storage, URLs or telemetry.
        assert "auth0|" not in one.owner_id

    def test_the_same_subject_is_stable_across_requests(self) -> None:
        assert (
            auth._authenticated_principal("auth0|aaa").owner_id
            == auth._authenticated_principal("auth0|aaa").owner_id
        )


class TestWorkspacePolicy:
    def test_a_signed_in_user_gets_the_private_policy(self) -> None:
        settings = get_settings()
        principal = auth._authenticated_principal("auth0|aaa")
        assert principal.daily_run_limit == settings.authenticated_migration_starts_per_day
        assert principal.retention_hours == settings.authenticated_retention_hours
        assert principal.usage_scope == "authenticated_user"

    def test_a_guest_gets_the_larger_but_shared_policy(self) -> None:
        settings = get_settings()
        guest = auth.anonymous_principal()
        assert guest.daily_run_limit == settings.anonymous_migration_starts_per_day
        assert guest.retention_hours == settings.anonymous_retention_hours
        assert guest.usage_scope == "shared_anonymous"

    def test_the_guest_allowance_is_larger_and_its_retention_shorter(self) -> None:
        guest = auth.anonymous_principal()
        user = auth._authenticated_principal("auth0|aaa")
        assert guest.daily_run_limit > user.daily_run_limit
        assert guest.retention < user.retention

    def test_expiry_is_the_workspace_retention_from_the_start(self) -> None:
        now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
        user = auth._authenticated_principal("auth0|aaa")
        assert user.expires_at(now) == now + user.retention


class TestQuotaWindow:
    def test_a_reservation_keeps_its_own_india_day(self) -> None:
        """A failure that crosses midnight must release the day it claimed.

        Recomputing the day at release time would leave the original day's counter
        permanently short by one.
        """
        before = migration_quota._window(datetime(2026, 9, 20, 18, 25, tzinfo=UTC))
        after = migration_quota._window(datetime(2026, 9, 20, 18, 35, tzinfo=UTC))
        assert before.day != after.day

        reservation = migration_quota.Reservation("user:abc", before.day, "run_x")
        assert reservation.day == before.day

    def test_the_quota_key_separates_workspaces_and_days(self) -> None:
        assert migration_quota._quota_id("user:a", "2026-09-20") != migration_quota._quota_id(
            "user:b", "2026-09-20"
        )
        assert migration_quota._quota_id("user:a", "2026-09-20") != migration_quota._quota_id(
            "user:a", "2026-09-21"
        )

    def test_a_naive_timestamp_is_refused(self) -> None:
        with pytest.raises(ValueError):
            migration_quota._window(datetime(2026, 9, 20, 12, 0))


class TestObservabilityEndpoint:
    """Cross-workspace telemetry needs its own server-side secret."""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_an_absent_secret_fails_closed(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "observability_api_secret", "", raising=False)
        assert client.get("/api/observability/status").status_code == 401

    def test_a_wrong_secret_is_refused(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "observability_api_secret", "right", raising=False)
        response = client.get(
            "/api/observability/status",
            headers={"X-SchemaBridge-Operator-Secret": "wrong"},
        )
        assert response.status_code == 401

    def test_an_end_user_token_is_not_an_operator_credential(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "observability_api_secret", "right", raising=False)
        response = client.get(
            "/api/observability/status", headers={"Authorization": "Bearer some-user-token"}
        )
        assert response.status_code == 401

    def test_the_right_secret_reports_configuration_only(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "observability_api_secret", "right", raising=False)
        response = client.get(
            "/api/observability/status",
            headers={"X-SchemaBridge-Operator-Secret": "right"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["langfuse_enabled"] is False
        # Booleans and counters only: never a credential.
        assert "langfuse_secret_key" not in body
        assert "right" not in response.text


class TestLangfuseIsOffByDefault:
    def test_the_shipped_configuration_exports_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from schemabridge.server import observability

        settings = get_settings()
        assert settings.langfuse_enabled is False
        assert settings.langfuse_configured is False

        def explode(*_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("no client may be constructed while disabled")

        monkeypatch.setattr(observability, "Langfuse", explode)
        observability.export_generation({"_id": "llm_1", "run_id": "run_1"})

    def test_an_exporter_failure_never_reaches_the_caller(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Telemetry is not allowed to fail a migration."""
        from schemabridge.server import observability

        settings = get_settings()
        monkeypatch.setattr(settings, "langfuse_enabled", True, raising=False)
        monkeypatch.setattr(settings, "langfuse_public_key", "pk", raising=False)
        monkeypatch.setattr(settings, "langfuse_secret_key", "sk", raising=False)

        def explode(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("langfuse unreachable")

        monkeypatch.setattr(observability, "Langfuse", explode)
        observability.export_generation({"_id": "llm_1", "run_id": "run_1"})

    def test_masking_redacts_secret_shaped_keys(self) -> None:
        from schemabridge.server import observability

        masked = observability._mask(
            {"api_key": "nvapi-1", "nested": {"authorization": "Bearer x"}, "model": "gpt"}
        )
        assert masked["api_key"] == "[redacted]"
        assert masked["nested"]["authorization"] == "[redacted]"
        assert masked["model"] == "gpt"


class TestRateGateSpacing:
    def test_the_interval_matches_the_configured_rate(self) -> None:
        """45 requests per minute means one start no sooner than every 4/3 s."""
        settings = get_settings()
        assert settings.nvidia_requests_per_minute == 45
        interval = timedelta(seconds=60 / settings.nvidia_requests_per_minute)
        assert interval.total_seconds() == pytest.approx(1.3333, rel=1e-3)


class TestCheckpointExpiry:
    """A run's checkpoints must expire on its own immutable deadline.

    LangGraph's own TTL is written relative to each checkpoint's creation, so a
    run that is still being advanced keeps renewing it. That is the wrong clock
    for a retention promise, so the deadline travels on the graph config instead.
    """

    @staticmethod
    def _saver() -> Any:
        from schemabridge.graph.checkpointer import FixedExpiryMongoDBSaver

        # No connection needed: only the config-reading helper is under test.
        return FixedExpiryMongoDBSaver.__new__(FixedExpiryMongoDBSaver)

    def test_a_datetime_deadline_is_used_as_given(self) -> None:
        deadline = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
        saver = self._saver()
        assert saver._expires_at({"configurable": {"run_expires_at": deadline}}) == deadline

    def test_a_serialised_deadline_is_revived(self) -> None:
        """A resumed run's config may arrive with the deadline as a string."""
        deadline = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
        saver = self._saver()
        revived = saver._expires_at({"configurable": {"run_expires_at": deadline.isoformat()}})
        assert revived == deadline

    def test_an_absent_or_unreadable_deadline_stamps_nothing(self) -> None:
        saver = self._saver()
        assert saver._expires_at({"configurable": {"thread_id": "run_1"}}) is None
        assert saver._expires_at({"configurable": {"run_expires_at": "nonsense"}}) is None

    def test_the_two_retention_classes_are_stored_apart(self) -> None:
        """One collection-wide TTL cannot express two policies, so they split."""
        from schemabridge.graph import checkpointer

        names: list[str] = []

        class _Fake:
            def __init__(self, _client: Any, **kwargs: Any) -> None:
                names.append(str(kwargs["db_name"]))
                self.checkpoint_collection = _Collection()
                self.writes_collection = _Collection()

        class _Collection:
            def create_index(self, *_args: Any, **_kwargs: Any) -> None:
                return None

            def list_indexes(self) -> list[dict[str, Any]]:
                return []

        original = checkpointer.FixedExpiryMongoDBSaver
        checkpointer.FixedExpiryMongoDBSaver = _Fake  # type: ignore[misc]
        try:
            checkpointer.build_checkpointer("anonymous")
            checkpointer.build_checkpointer("authenticated")
        finally:
            checkpointer.FixedExpiryMongoDBSaver = original  # type: ignore[misc]

        assert names[0] != names[1]
        assert names[0].endswith("_anonymous")
        assert names[1].endswith("_authenticated")
