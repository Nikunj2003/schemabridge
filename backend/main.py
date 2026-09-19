"""FastAPI application entrypoint.

Every route is declared under `/api` because the platform routes the `/api/*`
prefix to this service without stripping it — a handler mounted at `/health`
would never be reached.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from schemabridge import __version__
from schemabridge.api.mock_target import router as mock_target_router
from schemabridge.api.runs import router as runs_router
from schemabridge.api.schema_routes import router as schemas_router
from schemabridge.server.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Create indexes once per cold start rather than per request.

    Index creation is idempotent, so this is safe to repeat; a failure here must
    not stop the application, since the health endpoint is what diagnoses a
    misconfigured deployment.
    """
    if get_settings().has_database:
        try:
            from schemabridge.server import budget, receipts, runs, schemas

            runs.ensure_indexes()
            receipts.ensure_indexes()
            budget.ensure_indexes()
            schemas.ensure_indexes()
        except Exception:
            logger.warning("could not create indexes at startup", exc_info=False)
    yield


logger = logging.getLogger(__name__)


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
    lifespan=lifespan,
)


app.include_router(runs_router)
app.include_router(schemas_router)
app.include_router(mock_target_router)


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
