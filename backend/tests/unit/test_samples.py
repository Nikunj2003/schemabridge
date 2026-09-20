"""The sample-export downloads.

The demo dialog offers these by name, so a file quietly disappearing or the
allowlist drifting would leave broken links in the interface. The traversal cases
matter because the requested name reaches a path join.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from schemabridge.api.samples import _AVAILABLE, _SAMPLES

client = TestClient(app)


class TestListing:
    def test_every_advertised_sample_exists_on_disk(self) -> None:
        """The dialog trusts this listing, so it must not name a missing file."""
        missing = [name for name in _AVAILABLE if not (_SAMPLES / name).is_file()]
        assert missing == []

    def test_the_listing_reports_each_file_with_its_size(self) -> None:
        body = client.get("/api/samples").json()
        names = {entry["name"] for entry in body["files"]}
        assert names == set(_AVAILABLE)
        assert all(entry["bytes"] > 0 for entry in body["files"])


class TestDownload:
    def test_each_sample_downloads_with_its_own_media_type(self) -> None:
        for name, media_type in _AVAILABLE.items():
            response = client.get(f"/api/samples/{name}")
            assert response.status_code == 200, name
            assert response.headers["content-type"].startswith(media_type), name
            assert len(response.content) == (_SAMPLES / name).stat().st_size

    def test_the_response_is_offered_as_a_download(self) -> None:
        response = client.get("/api/samples/employees-clean.csv")
        assert "attachment" in response.headers["content-disposition"]
        assert "employees-clean.csv" in response.headers["content-disposition"]


class TestOnlyTheAllowlistIsServed:
    def test_an_unknown_name_is_not_found(self) -> None:
        assert client.get("/api/samples/nothing-here.csv").status_code == 404

    def test_a_traversal_attempt_is_refused(self) -> None:
        """The name reaches a path join, so membership is the only gate.

        A sanitising pass would be the wrong shape here: it invites an encoding
        nobody thought of. Anything not named in the allowlist is simply absent.
        """
        for attempt in (
            "../../../etc/passwd",
            "..%2f..%2f..%2fetc%2fpasswd",
            "....//....//etc/passwd",
            ".env",
            "../config.py",
        ):
            assert client.get(f"/api/samples/{attempt}").status_code in {404, 400}, attempt

    def test_no_python_source_is_reachable(self) -> None:
        assert client.get("/api/samples/samples.py").status_code == 404
