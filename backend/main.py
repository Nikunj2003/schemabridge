"""FastAPI application entrypoint.

Every route is declared under `/api` because the platform routes the `/api/*`
prefix to this service without stripping it — a handler mounted at `/health`
would never be reached.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from schemabridge import __version__
from schemabridge.server.config import get_settings

app = FastAPI(
    title="SchemaBridge API",
    version=__version__,
    description=(
        "Migration engine that reconciles inconsistent source exports, transforms "
        "records safely, and escalates only genuine uncertainty to a human."
    ),
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    # Both of these default to paths outside /api, which the platform routes to
    # the frontend instead — they would 404. Redoc is not needed at all.
    swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
    redoc_url=None,
)


@app.get("/api/health")
def health() -> JSONResponse:
    """Readiness probe.

    Reports whether the external dependencies are configured without revealing
    any credential, so a misconfigured deployment is diagnosable from the
    browser.
    """
    settings = get_settings()
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "model_configured": settings.has_model_access,
            "database_configured": settings.has_database,
            "model": settings.nvidia_model if settings.has_model_access else None,
        }
    )
