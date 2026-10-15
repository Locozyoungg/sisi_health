"""Background jobs (arq). Phase 1: the audit chain verifier and erasure runner are
callable directly (make audit-verify / DSR processing); Phase 5 adds the cervical
screening and follow-up reminder sweeps. Every job opens its own session, records
counts only in the audit trail, and never writes condition-identifying text."""

from typing import Any

from app.audit.service import record_event
from app.audit.verifier import verify_chain
from app.config import get_settings
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.corridor.reminders import send_screening_reminders, send_tracker_reminders
from app.crypto.key_provider import DatabaseKeyProvider
from app.db import SessionLocal


async def verify_audit_chain_job(ctx: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    with SessionLocal() as db:
        return verify_chain(db)


def noop_sms(phone: str, message: str) -> None:
    """Delivery stub: real delivery goes through the gateway provider at pilot time
    (phone resolution is a human task). The wording is always generic
    (non-negotiable 4); the backend records delivery status either way."""
    return None


def _status_counts(report: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in report:
        status = str(row["status"])
        counts[status] = counts.get(status, 0) + 1
    return counts


async def send_screening_reminders_job(ctx: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Age-based screening prompt sweep (spec 5.4.1). Idempotent per
    (user, kind, due_at) via the reminders unique constraint."""
    with SessionLocal() as db:
        provider = DatabaseKeyProvider(get_settings())
        report = send_screening_reminders(db, provider, noop_sms, utc_now_naive())
        counts = _status_counts(report)
        record_event(
            db,
            event_type="reminders_run",
            actor_type="system",
            actor_id=None,
            actor_role=None,
            resource_type="reminders",
            resource_id=uuid7(),
            payload={"kind": "screening", "count": len(report), "statuses": counts},
        )
        db.commit()
        return {"kind": "screening", "dispatched": len(report), "statuses": counts}


async def send_tracker_reminders_job(ctx: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Follow-up nudge sweep; also derives `lost_to_follow_up` after the configured
    missed-reminder threshold (status only — never results detail)."""
    with SessionLocal() as db:
        report = send_tracker_reminders(db, noop_sms, utc_now_naive())
        counts = _status_counts(report)
        lost = sum(1 for row in report if row["lost_to_follow_up"])
        record_event(
            db,
            event_type="reminders_run",
            actor_type="system",
            actor_id=None,
            actor_role=None,
            resource_type="reminders",
            resource_id=uuid7(),
            payload={
                "kind": "follow_up",
                "count": len(report),
                "statuses": counts,
                "lost_to_follow_up": lost,
            },
        )
        db.commit()
        return {
            "kind": "follow_up",
            "dispatched": len(report),
            "statuses": counts,
            "lost_to_follow_up": lost,
        }


async def worker_settings(ctx: dict[str, Any]) -> None:  # noqa: ARG001
    """arq startup hook (stub)."""
