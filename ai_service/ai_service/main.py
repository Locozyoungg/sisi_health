"""FastAPI app for the AI service (port 8002). Internal-only: every /v1/ai route
requires the shared bearer token (A35), and interactive docs exist in dev/demo only.

Settings are read at import time so a staging/prod misconfiguration (stub provider,
default internal token) fails the boot rather than serving traffic (§ config)."""

from app.api.envelope import err
from app.core.errors import AppError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ai_service import __version__
from ai_service.api import router as ai_router
from ai_service.config import get_ai_settings


def create_app() -> FastAPI:
    settings = get_ai_settings()
    app = FastAPI(
        title="SISI Health AI Service",
        version=__version__,
        description=(
            "AI conversation layer (Phase 6): education and next-step guidance over "
            "approved content. The deterministic rules engine assigns every risk band "
            "and red-flag routing; SISI supports you and your doctor - it does not "
            "diagnose."
        ),
        docs_url="/docs" if settings.env in {"dev", "demo"} else None,
        openapi_url="/openapi.json",
    )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:  # noqa: ARG001
        return JSONResponse(
            status_code=exc.status_code,
            content=err(exc.code, exc.message, exc.status_code),
        )

    app.include_router(ai_router, prefix="/v1/ai")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
