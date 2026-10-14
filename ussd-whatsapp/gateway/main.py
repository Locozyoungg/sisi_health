"""Gateway FastAPI app: USSD callback + WhatsApp webhook. Served by the same
dev stack as the backend (separate port 8001)."""

from fastapi import FastAPI

from gateway.api import ussd, whatsapp
from gateway.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="SISI Health Gateway",
        version="0.1.0",
        description="USSD + WhatsApp assessment flows (Phase 3). "
        "SISI supports you and your doctor - it does not diagnose.",
        docs_url="/docs" if settings.env in {"dev", "demo"} else None,
    )
    app.include_router(ussd.router, prefix="/ussd", tags=["ussd"])
    app.include_router(whatsapp.router, prefix="/whatsapp", tags=["whatsapp"])

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
