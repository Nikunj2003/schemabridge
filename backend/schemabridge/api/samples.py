"""The sample exports, served from the fixtures the tests themselves use.

Read from `backend/fixtures/samples` rather than copied into the web app's static
assets deliberately: those files are what the test suite pins its assertions to,
so a second copy could drift and the demo would stop demonstrating the behaviour
that is actually verified.

Only an explicit allowlist is served. The filename reaches a path join, so
accepting an arbitrary name would be a directory traversal — `..%2f` and friends
are why this is a membership test and never a sanitising pass.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/samples", tags=["samples"])

_SAMPLES = Path(__file__).resolve().parents[2] / "fixtures" / "samples"

#: The files offered, with the media type each should download as. A closed set:
#: anything not named here is not served, whatever the request asks for.
_AVAILABLE: dict[str, str] = {
    "employees-legacy.csv": "text/csv",
    "employees-hr-export.csv": "text/csv",
    "employees-clean.csv": "text/csv",
    "employees-directory.xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
}


@router.get("")
def list_samples() -> dict[str, list[dict[str, object]]]:
    """Which sample files exist, so the UI never offers a missing download."""
    files: list[dict[str, object]] = []
    for name in _AVAILABLE:
        path = _SAMPLES / name
        if not path.is_file():
            continue
        files.append({"name": name, "bytes": path.stat().st_size})
    return {"files": files}


@router.get("/{name}")
def read_sample(name: str) -> FileResponse:
    """One sample export, as a download."""
    media_type = _AVAILABLE.get(name)
    if media_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such sample.")
    path = _SAMPLES / name
    if not path.is_file():
        # Present in the allowlist but absent from the deployment, which is a
        # packaging problem rather than a bad request.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="That sample is not available in this deployment.",
        )
    return FileResponse(
        path,
        media_type=media_type,
        filename=name,
        headers={"Cache-Control": "public, max-age=3600"},
    )
