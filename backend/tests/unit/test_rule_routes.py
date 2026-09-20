"""The rules API, exercised through the app rather than the store directly.

No database is available in this suite, so the rule store's module-level
functions are replaced with an in-memory fake that reproduces the two
behaviours these routes depend on: ownership scoped to a session, and a
version-guarded write that fails when the version has moved on. Everything
else — request validation, status codes, routing order — is exercised for
real, against the real app.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from main import app
from schemabridge.api import rule_routes
from schemabridge.domain.rules import Rule, RuleKind, RuleOrigin
from schemabridge.domain.target import BUILTIN_SCHEMA
from schemabridge.server import rules as rule_store
from schemabridge.server.sessions import SESSION_COOKIE

#: Every rule now has to name the schema it applies to. Tests that are not
#: exercising that requirement itself just want a schema that exists.
_SCHEMA_ID = BUILTIN_SCHEMA.schema_id


def _rule(**overrides: object) -> Rule:
    """A `Rule` with a valid `schema_id`, so tests exercising something else
    do not have to repeat it."""
    return Rule(**{"schema_id": _SCHEMA_ID, **overrides})


@dataclass
class _FakeStore:
    """Reproduces `server.rules`'s ownership and version-guard contract."""

    rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0

    def _next_id(self) -> str:
        self._seq += 1
        return f"rule_test{self._seq}"

    def create_rule(self, owner_session_id: str, rule: Rule) -> rule_store.RuleRecord:
        from schemabridge.domain.rules import MAX_RULES_PER_SESSION

        if self.count_for_session(owner_session_id) >= MAX_RULES_PER_SESSION:
            raise rule_store.RuleLimitError("limit reached")
        rule_id = self._next_id()
        now = datetime.now(UTC)
        self.rows[rule_id] = {
            "owner_session_id": owner_session_id,
            "rule": rule,
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        return rule_store.RuleRecord(
            rule_id,
            owner_session_id,
            rule.model_copy(update={"rule_id": rule_id}),
            1,
            now,
            now,
        )

    def find_rule(self, rule_id: str, owner_session_id: str) -> rule_store.RuleRecord | None:
        row = self.rows.get(rule_id)
        if row is None or row["owner_session_id"] != owner_session_id:
            return None
        return rule_store.RuleRecord(
            rule_id,
            owner_session_id,
            row["rule"].model_copy(update={"rule_id": rule_id}),
            row["version"],
            row["created_at"],
            row["updated_at"],
        )

    def list_rules(self, owner_session_id: str, limit: int = 200) -> list[rule_store.RuleRecord]:
        return [
            rule_store.RuleRecord(
                rule_id,
                owner_session_id,
                row["rule"].model_copy(update={"rule_id": rule_id}),
                row["version"],
                row["created_at"],
                row["updated_at"],
            )
            for rule_id, row in self.rows.items()
            if row["owner_session_id"] == owner_session_id
        ]

    def count_for_session(self, owner_session_id: str) -> int:
        return sum(1 for row in self.rows.values() if row["owner_session_id"] == owner_session_id)

    def update_rule(
        self, rule_id: str, owner_session_id: str, rule: Rule, *, if_version: int
    ) -> rule_store.RuleRecord:
        row = self.rows.get(rule_id)
        if row is None or row["owner_session_id"] != owner_session_id:
            raise KeyError(rule_id)
        if row["version"] != if_version:
            raise rule_store.StaleWriteError("stale")
        row["rule"] = rule
        row["version"] += 1
        row["updated_at"] = datetime.now(UTC)
        result = self.find_rule(rule_id, owner_session_id)
        assert result is not None
        return result

    def delete_rule(self, rule_id: str, owner_session_id: str) -> bool:
        row = self.rows.get(rule_id)
        if row is None or row["owner_session_id"] != owner_session_id:
            return False
        del self.rows[rule_id]
        return True

    def set_enabled(
        self, rule_id: str, owner_session_id: str, *, enabled: bool
    ) -> rule_store.RuleRecord:
        row = self.rows.get(rule_id)
        if row is None or row["owner_session_id"] != owner_session_id:
            raise KeyError(rule_id)
        row["rule"] = row["rule"].model_copy(update={"enabled": enabled})
        row["version"] += 1
        result = self.find_rule(rule_id, owner_session_id)
        assert result is not None
        return result

    def override_builtin(
        self, owner_session_id: str, builtin_rule_id: str, *, schema_id: str, rationale: str = ""
    ) -> rule_store.RuleRecord:
        existing = next(
            (
                rule_id
                for rule_id, row in self.rows.items()
                if row["owner_session_id"] == owner_session_id
                and row["rule"].kind is RuleKind.OVERRIDE
                and row["rule"].targets_rule_id == builtin_rule_id
            ),
            None,
        )
        if existing is not None:
            return self.set_enabled(existing, owner_session_id, enabled=True)
        return self.create_rule(
            owner_session_id,
            _rule(
                kind=RuleKind.OVERRIDE,
                origin=RuleOrigin.OVERRIDE,
                targets_rule_id=builtin_rule_id,
                schema_id=schema_id,
                rationale=rationale,
            ),
        )


@pytest.fixture
def fake_store(monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    store = _FakeStore()
    for name in (
        "create_rule",
        "find_rule",
        "list_rules",
        "update_rule",
        "delete_rule",
        "set_enabled",
        "override_builtin",
    ):
        monkeypatch.setattr(rule_store, name, getattr(store, name))
        # `rule_routes` imported these as `rule_store.<name>`, so patching the
        # shared module object (above) is what both call sites see.
    return store


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _session_client(
    client: TestClient, session_id: str = "session-a-XXXXXXXXXXXXXXX"
) -> TestClient:
    # `read_session` refuses anything under 20 characters, so a realistic id is
    # used rather than a short readable stub.
    client.cookies.set(SESSION_COOKIE, session_id)
    return client


class TestBuiltinLayer:
    def test_builtin_rules_are_projected_and_not_editable(
        self, client: TestClient, fake_store: _FakeStore
    ) -> None:
        response = _session_client(client).get("/api/rules")
        assert response.status_code == 200
        body = response.json()
        assert body["mine"] == []
        assert body["builtin"]
        assert all(entry["editable"] is False for entry in body["builtin"])
        assert all(entry["version"] == 0 for entry in body["builtin"])

    def test_a_header_two_fields_share_has_no_builtin_rule(
        self, client: TestClient, fake_store: _FakeStore
    ) -> None:
        """ "Date", shared by startDate and endDate, must not appear as a rule.

        A rule settling it would convert the escalation that protects an
        ambiguous header into a silent mapping.
        """
        response = _session_client(client).get("/api/rules")
        headers = {entry["header"] for entry in response.json()["builtin"]}
        assert "dates" not in headers
        assert "effectivedate" not in headers

    def test_an_active_override_marks_the_shipped_rule_overridden(
        self, client: TestClient, fake_store: _FakeStore
    ) -> None:
        session = _session_client(client)
        builtin = session.get("/api/rules").json()["builtin"]
        target = next(entry for entry in builtin if entry["kind"] == "header_alias")

        toggled = session.post(f"/api/rules/{target['rule_id']}/toggle", json={"enabled": False})
        assert toggled.status_code == 200

        refreshed = session.get("/api/rules").json()["builtin"]
        same = next(entry for entry in refreshed if entry["rule_id"] == target["rule_id"])
        assert same["overridden"] is True


class TestCreate:
    def test_missing_required_field_is_a_400(
        self, client: TestClient, fake_store: _FakeStore
    ) -> None:
        response = _session_client(client).post(
            "/api/rules",
            json={"kind": "header_alias", "header": "Cost Centre Ref", "schema_id": _SCHEMA_ID},
        )
        assert response.status_code == 400
        assert "value error" not in response.json()["detail"].lower()

    def test_a_complete_rule_is_created(self, client: TestClient, fake_store: _FakeStore) -> None:
        response = _session_client(client).post(
            "/api/rules",
            json={
                "kind": "header_alias",
                "header": "Cost Centre Ref",
                "field_name": "department",
                "schema_id": _SCHEMA_ID,
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["editable"] is True
        assert body["version"] == 1
        assert body["header"] == "costcentreref"

    def test_no_session_is_unauthorized(self, client: TestClient, fake_store: _FakeStore) -> None:
        response = client.post(
            "/api/rules",
            json={
                "kind": "header_alias",
                "header": "x",
                "field_name": "department",
                "schema_id": _SCHEMA_ID,
            },
        )
        assert response.status_code == 401

    def test_an_empty_schema_id_is_a_400(self, client: TestClient, fake_store: _FakeStore) -> None:
        """`schema_id` is required for every kind now, not only header_alias and
        value_alias: a rule that names no schema is one nobody can say applies
        (or does not apply) to their next migration."""
        response = _session_client(client).post(
            "/api/rules",
            json={
                "kind": "header_alias",
                "header": "Cost Centre Ref",
                "field_name": "department",
                "schema_id": "",
            },
        )
        assert response.status_code == 400
        assert "schema" in response.json()["detail"].lower()

    def test_an_ambiguous_header_alias_is_a_400(
        self, client: TestClient, fake_store: _FakeStore
    ) -> None:
        """ "Date" is claimed by both startDate and endDate. A rule settling it
        would silently resolve the exact ambiguity the engine is supposed to
        escalate, so it has to be refused here and not only when the model drafts
        one."""
        response = _session_client(client).post(
            "/api/rules",
            json={
                "kind": "header_alias",
                "header": "Date",
                "field_name": "startDate",
                "schema_id": _SCHEMA_ID,
            },
        )
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "asked about" in detail


class TestUpdate:
    def test_put_without_if_version_is_refused(
        self, client: TestClient, fake_store: _FakeStore
    ) -> None:
        session = _session_client(client)
        created = session.post(
            "/api/rules",
            json={
                "kind": "header_alias",
                "header": "Cost Centre Ref",
                "field_name": "department",
                "schema_id": _SCHEMA_ID,
            },
        ).json()

        response = session.put(
            f"/api/rules/{created['rule_id']}",
            json={
                "kind": "header_alias",
                "header": "New Header",
                "field_name": "department",
                "schema_id": _SCHEMA_ID,
            },
        )
        assert response.status_code == 400

    def test_a_stale_version_is_a_409(self, client: TestClient, fake_store: _FakeStore) -> None:
        session = _session_client(client)
        created = session.post(
            "/api/rules",
            json={
                "kind": "header_alias",
                "header": "Cost Centre Ref",
                "field_name": "department",
                "schema_id": _SCHEMA_ID,
            },
        ).json()

        response = session.put(
            f"/api/rules/{created['rule_id']}",
            json={
                "kind": "header_alias",
                "header": "New Header",
                "field_name": "department",
                "schema_id": _SCHEMA_ID,
                "if_version": created["version"] + 1,
            },
        )
        assert response.status_code == 409

    def test_a_current_version_saves(self, client: TestClient, fake_store: _FakeStore) -> None:
        session = _session_client(client)
        created = session.post(
            "/api/rules",
            json={
                "kind": "header_alias",
                "header": "Cost Centre Ref",
                "field_name": "department",
                "schema_id": _SCHEMA_ID,
            },
        ).json()

        response = session.put(
            f"/api/rules/{created['rule_id']}",
            json={
                "kind": "header_alias",
                "header": "Cost Centre Reference",
                "field_name": "department",
                "schema_id": _SCHEMA_ID,
                "if_version": created["version"],
            },
        )
        assert response.status_code == 200
        assert response.json()["version"] == created["version"] + 1


class TestOwnership:
    def test_one_session_cannot_read_anothers_rule(
        self, client: TestClient, fake_store: _FakeStore
    ) -> None:
        owner = _session_client(TestClient(app), "session-owner-XXXXXXXXXXXXXX")
        created = owner.post(
            "/api/rules",
            json={
                "kind": "header_alias",
                "header": "Cost Centre Ref",
                "field_name": "department",
                "schema_id": _SCHEMA_ID,
            },
        ).json()

        stranger = _session_client(TestClient(app), "session-stranger-XXXXXXXXXXX")
        response = stranger.get(f"/api/rules/{created['rule_id']}")
        assert response.status_code == 404

    def test_one_session_cannot_modify_anothers_rule(
        self, client: TestClient, fake_store: _FakeStore
    ) -> None:
        owner = _session_client(TestClient(app), "session-owner-XXXXXXXXXXXXXX")
        created = owner.post(
            "/api/rules",
            json={
                "kind": "header_alias",
                "header": "Cost Centre Ref",
                "field_name": "department",
                "schema_id": _SCHEMA_ID,
            },
        ).json()

        stranger = _session_client(TestClient(app), "session-stranger-XXXXXXXXXXX")
        response = stranger.put(
            f"/api/rules/{created['rule_id']}",
            json={
                "kind": "header_alias",
                "header": "Hijacked",
                "field_name": "department",
                "schema_id": _SCHEMA_ID,
                "if_version": created["version"],
            },
        )
        assert response.status_code == 404

        deleted = stranger.delete(f"/api/rules/{created['rule_id']}")
        assert deleted.status_code == 404

    def test_absent_and_someone_elses_rule_look_identical(
        self, client: TestClient, fake_store: _FakeStore
    ) -> None:
        owner = _session_client(TestClient(app), "session-owner-XXXXXXXXXXXXXX")
        created = owner.post(
            "/api/rules",
            json={
                "kind": "header_alias",
                "header": "Cost Centre Ref",
                "field_name": "department",
                "schema_id": _SCHEMA_ID,
            },
        ).json()

        stranger = _session_client(TestClient(app), "session-stranger-XXXXXXXXXXX")
        theirs = stranger.get(f"/api/rules/{created['rule_id']}")
        absent = stranger.get("/api/rules/rule_does_not_exist")
        assert theirs.status_code == absent.status_code == 404
        assert theirs.json() == absent.json()


def _csv_file(name: str, text: str) -> tuple[str, tuple[str, bytes, str]]:
    return "files", (name, text.encode("utf-8"), "text/csv")


_HEADER_ALIAS_DRAFT = (
    '{"kind": "header_alias", "header": "Cost Centre Ref", '
    f'"field_name": "department", "schema_id": "{_SCHEMA_ID}"}}'
)


class TestPreview:
    def test_preview_writes_nothing(self, client: TestClient, fake_store: _FakeStore) -> None:
        session = _session_client(client)
        csv_text = "Cost Centre Ref,Full Name\n1001,Alice Example\n"
        response = session.post(
            "/api/rules/preview",
            files=[_csv_file("employees.csv", csv_text)],
            data={"rule": _HEADER_ALIAS_DRAFT},
        )
        assert response.status_code == 200
        assert fake_store.rows == {}

    def test_preview_reports_a_header_alias_match(
        self, client: TestClient, fake_store: _FakeStore
    ) -> None:
        session = _session_client(client)
        csv_text = "Cost Centre Ref,Full Name\n1001,Alice Example\n"
        response = session.post(
            "/api/rules/preview",
            files=[_csv_file("employees.csv", csv_text)],
            data={"rule": _HEADER_ALIAS_DRAFT},
        )
        body = response.json()
        assert body["would_change"] >= 1
        assert any(m["header"] == "Cost Centre Ref" for m in body["matched_columns"])

    def test_preview_reports_a_column_the_rule_would_leave_out(
        self, client: TestClient, fake_store: _FakeStore
    ) -> None:
        """An ignored column has no target before or after the rule.

        So a preview diffing targets alone reports that an ignore rule changes
        nothing, and a person declines a rule that in fact works. Worth its own test
        because the bug is invisible: the endpoint answers successfully either way.
        """
        session = _session_client(client)
        csv_text = "Cost Centre Ref,Full Name\n1001,Alice Example\n"
        response = session.post(
            "/api/rules/preview",
            files=[_csv_file("employees.csv", csv_text)],
            data={
                "rule": json.dumps(
                    {
                        "kind": "column_ignore",
                        "header": "Cost Centre Ref",
                        "schema_id": _SCHEMA_ID,
                    }
                )
            },
        )
        body = response.json()
        assert body["would_change"] >= 1
        assert any(m["header"] == "Cost Centre Ref" for m in body["matched_columns"])
        assert fake_store.rows == {}

    def test_preview_needs_a_session(self, client: TestClient, fake_store: _FakeStore) -> None:
        csv_text = "Cost Centre Ref\n1001\n"
        response = client.post(
            "/api/rules/preview",
            files=[_csv_file("employees.csv", csv_text)],
            data={"rule": _HEADER_ALIAS_DRAFT},
        )
        assert response.status_code == 401


class TestToggle:
    def test_toggling_off_a_builtin_rule_creates_an_override(
        self, client: TestClient, fake_store: _FakeStore
    ) -> None:
        session = _session_client(client)
        builtin = session.get("/api/rules").json()["builtin"]
        target = next(entry for entry in builtin if entry["kind"] == "header_alias")

        response = session.post(f"/api/rules/{target['rule_id']}/toggle", json={"enabled": False})
        assert response.status_code == 200
        assert any(row["rule"].kind is RuleKind.OVERRIDE for row in fake_store.rows.values())

    def test_toggling_a_builtin_rule_back_on_disables_the_override(
        self, client: TestClient, fake_store: _FakeStore
    ) -> None:
        session = _session_client(client)
        builtin = session.get("/api/rules").json()["builtin"]
        target = next(entry for entry in builtin if entry["kind"] == "header_alias")

        session.post(f"/api/rules/{target['rule_id']}/toggle", json={"enabled": False})
        response = session.post(f"/api/rules/{target['rule_id']}/toggle", json={"enabled": True})
        assert response.status_code == 200

        refreshed = session.get("/api/rules").json()["builtin"]
        same = next(entry for entry in refreshed if entry["rule_id"] == target["rule_id"])
        assert same["overridden"] is False

    def test_toggling_ones_own_rule_flips_enabled(
        self, client: TestClient, fake_store: _FakeStore
    ) -> None:
        session = _session_client(client)
        created = session.post(
            "/api/rules",
            json={
                "kind": "header_alias",
                "header": "Cost Centre Ref",
                "field_name": "department",
                "schema_id": _SCHEMA_ID,
            },
        ).json()

        response = session.post(f"/api/rules/{created['rule_id']}/toggle", json={"enabled": False})
        assert response.status_code == 200
        assert response.json()["enabled"] is False


class TestRuleView:
    def test_rule_view_names_the_fields_the_ui_needs(self) -> None:
        rule = _rule(
            rule_id="rule_x",
            kind=RuleKind.HEADER_ALIAS,
            header="Cost Centre Ref",
            field_name="department",
        )
        view = rule_routes.rule_view(rule, version=3, editable=True)
        assert view["rule_id"] == "rule_x"
        assert view["version"] == 3
        assert view["editable"] is True
        assert view["overridden"] is False
        assert view["provenance"] is None
