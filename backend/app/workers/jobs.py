"""Background jobs (arq). Phase 1: the audit chain verifier and erasure runner are
callable directly (make audit-verify / DSR processing); Phase 5 adds the cervical
screening and follow-up reminder sweeps; Phase 8 adds the retention purge. Every
job opens its own session, records counts only in the audit trail, and never
writes condition-identifying text."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.audit.verifier import verify_chain
from app.config import get_settings
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.corridor.reminders import send_screening_reminders, send_tracker_reminders
from app.crypto.key_provider import DatabaseKeyProvider
from app.db import SessionLocal
from app.models import DiaryEntry, DiaryEntryVersion, RuleEvaluation, Voucher


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


def _purge_diary(db: Session, provider: DatabaseKeyProvider, cutoff: datetime) -> dict[str, int]:
    """Delete diary data whose newest version predates `cutoff`.

    An entry is stale when its newest version's `created_at` is older than the
    cutoff (an entry with no versions falls back to its own `created_at`). Stale
    entries are deleted with their versions and the owning user's evaluations
    older than the same cutoff. Data keys are NEVER destroyed here — the
    owner_type='user' key also wraps the user row's encrypted PII
    (phone/birth_date), so destroying it would make a live user's PII
    unrecoverable. Keys are removed only by the erasure path
    (`app/consent/erasure.py`); see assumptions A3 / CC-6.
    """
    newest_version = (
        select(func.max(DiaryEntryVersion.created_at))
        .where(DiaryEntryVersion.entry_id == DiaryEntry.id)
        .scalar_subquery()
    )
    stale_entries = (
        db.execute(
            select(DiaryEntry).where(
                func.coalesce(newest_version, DiaryEntry.created_at) < cutoff
            )
        )
        .scalars()
        .all()
    )
    counts = {
        "diary_entries_purged": len(stale_entries),
        "diary_versions_purged": 0,
        "rule_evaluations_purged": 0,
        "data_keys_purged": 0,
    }
    if not stale_entries:
        return counts

    entry_ids = [entry.id for entry in stale_entries]
    user_ids = sorted({entry.user_id for entry in stale_entries})
    counts["diary_versions_purged"] = db.execute(
        select(func.count())
        .select_from(DiaryEntryVersion)
        .where(DiaryEntryVersion.entry_id.in_(entry_ids))
    ).scalar_one()
    db.execute(
        delete(DiaryEntryVersion)
        .where(DiaryEntryVersion.entry_id.in_(entry_ids))
        .execution_options(synchronize_session=False)
    )
    db.execute(
        delete(DiaryEntry)
        .where(DiaryEntry.id.in_(entry_ids))
        .execution_options(synchronize_session=False)
    )

    stale_evaluations = [
        RuleEvaluation.user_id.in_(user_ids),
        RuleEvaluation.created_at < cutoff,
    ]
    counts["rule_evaluations_purged"] = db.execute(
        select(func.count()).select_from(RuleEvaluation).where(*stale_evaluations)
    ).scalar_one()
    db.execute(
        delete(RuleEvaluation)
        .where(*stale_evaluations)
        .execution_options(synchronize_session=False)
    )

    # Data keys are NEVER deleted here: the owner_type='user' key also wraps
    # core.users.phone_encrypted / birth_date_encrypted, so removing it would
    # make a live user's PII unrecoverable. Keys are removed only by the
    # erasure path (app/consent/erasure.py). See assumptions A3 / CC-6.
    return counts


def _expire_stale_vouchers(db: Session, cutoff: datetime) -> int:
    """Mark vouchers expired once they lapsed more than `retention_voucher_days` ago.

    Redeemed vouchers are terminal (a reconciliation record, not a live
    instrument) and already-expired rows are left alone, so the sweep is
    idempotent and never rewrites settled money.
    """
    stale = [
        Voucher.expires_at < cutoff,
        Voucher.status.not_in(("expired", "redeemed")),
    ]
    count = db.execute(select(func.count()).select_from(Voucher).where(*stale)).scalar_one()
    if count:
        db.execute(
            update(Voucher)
            .where(*stale)
            .values(status="expired")
            .execution_options(synchronize_session=False)
        )
    return count


async def purge_retention_job(ctx: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Retention purge (spec 6, assumption A3): diary data and vouchers only.

    The audit table is NEVER touched by this job. It is append-only and
    hash-chained (every row carries the previous row's hash), so deleting rows
    would break the chain the nightly verifier checks. `retention_audit_days`
    therefore has no automated effect: the audit-retention-schedule vs
    append-only-chain conflict is an **OPEN maintainer decision**,
    and audit rows are currently retained indefinitely
    (see docs/assumptions.md A3 and docs/contract-changes.md CC-6).
    """
    with SessionLocal() as db:
        settings = get_settings()
        provider = DatabaseKeyProvider(settings)
        now = utc_now_naive()
        report: dict[str, Any] = _purge_diary(
            db, provider, now - timedelta(days=settings.retention_diary_days)
        )
        report["vouchers_expired"] = _expire_stale_vouchers(
            db, now - timedelta(days=settings.retention_voucher_days)
        )
        record_event(
            db,
            event_type="retention_purge_run",
            actor_type="system",
            actor_id=None,
            actor_role=None,
            resource_type="retention",
            resource_id=uuid7(),
            payload={"counts": report},
        )
        db.commit()
        return report
