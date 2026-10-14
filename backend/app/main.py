"""FastAPI application: routers, error envelope, CORS."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import v1
from app.api.envelope import err
from app.config import get_settings
from app.core.errors import AppError


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="SISI Health API",
        version="0.1.0",
        description=(
            "SISI Health backend (Phase 1): deterministic rules engine, audit trail, "
            "consent and erasure. SISI supports you and your doctor - it does not diagnose."
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

    if settings.env in {"dev", "demo"}:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # dev/demo only; staging/prod origins are explicit (Phase 8)
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=False,
        )

    app.include_router(v1.router, prefix="/v1")
    return app


app = create_app()
