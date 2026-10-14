"""Liveness endpoint. No data, no auth."""

from typing import Any

from fastapi import APIRouter

from app.api.envelope import ok

router = APIRouter()


@router.get("/health")
def health() -> dict[str, Any]:
    return ok({"status": "ok", "version": "0.1.0"})
