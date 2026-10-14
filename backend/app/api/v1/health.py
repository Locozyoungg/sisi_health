"""Liveness endpoint. No data, no auth."""

from fastapi import APIRouter

from app.api.envelope import ok

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return ok({"status": "ok", "version": "0.1.0"})
