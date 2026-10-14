"""Background jobs (arq). Phase 1: the audit chain verifier and erasure runner are
callable directly (make audit-verify / DSR processing); the arq worker wiring lands
with Phase 3 when Redis-backed jobs (SMS, USSD) arrive."""

import asyncio

from app.audit.verifier import verify_chain
from app.db import SessionLocal


async def verify_audit_chain_job(ctx: dict) -> dict:  # noqa: ARG001
    with SessionLocal() as db:
        return verify_chain(db)


async def worker_settings(ctx: dict) -> None:  # noqa: ARG001
    """arq startup hook (stub)."""
