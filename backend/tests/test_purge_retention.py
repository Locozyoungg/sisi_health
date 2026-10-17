"""Retention purge (CC-6, Phase 8): diary data past the window, data keys only
when nothing is left to decrypt, lapsed vouchers, and the untouched audit chain.

Run this file alone: the session fixture rebuilds the shared `sisi_test`
database, so a concurrent pytest process would collide with it.
"""

import asyncio
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.audit.service import record_event
from app.audit.verifier import verify_chain
from app.config import get_settings
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.diary.service import SyncEntry, sync_entries
from app.models import (
    AuditEvent,
    DataKey,
    DiaryEntry,
    DiaryEntryVersion,
    RuleEvaluation,
    School,
    Voucher,
)
from app.workers.jobs import purge_retention_job

DIARY_PAYLOAD = {"date": "2020-01-01", "pain": 3}


def _old() -> datetime:
    """Comfortably past the diary retention window (default 2555 days)."""
    return utc_now_naive() - timedelta(days=get_settings().retention_diary_days + 45)


def _sync_entry(db, provider, user, when: datetime) -> uuid.UUID:
    """One diary entry with one version stamped `when`; returns the entry id."""
    client_id = uuid7()
    sync_entries(
        db,
        provider,
        user,
        [
            SyncEntry(
                client_id=client_id,
                idempotency_key=f"purge-{uuid.uuid4().hex}",
                version=1,
                payload=DIARY_PAYLOAD,
                created_at=when,
            )
        ],
    )
    return db.execute(
        select(DiaryEntry.id).where(DiaryEntry.client_id == client_id)
    ).scalar_one()


def _add_evaluation(db, provider, user, when: datetime) -> uuid.UUID:
    data_key = provider.get_or_create_data_key(db, "user", user.id)
    row = RuleEvaluation(
        id=uuid7(),
        user_id=user.id,
        rule_set_version="ontology-1.1",
        payload_ciphertext=b"synthetic-ciphertext",
        key_id=data_key.id,
        created_at=when,
    )
    db.add(row)
    db.flush()
    return row.id


def _add_voucher(db, *, expires_at: datetime, status: str, redeemed_at=None) -> uuid.UUID:
    school = db.execute(select(School)).scalars().first()
    if school is None:
        school = School(id=uuid7(), name="Purge Retention Test School")
        db.add(school)
        db.flush()
    voucher = Voucher(
        id=uuid7(),
        code=f"PRG-{uuid.uuid4().hex[:12]}",
        school_id=school.id,
        category="otc_pain",
        otc_item="paracetamol",
        amount_ksh=200,
        status=status,
        expires_at=expires_at,
        redeemed_at=redeemed_at,
    )
    db.add(voucher)
    db.flush()
    return voucher.id


def _user_data_keys(db, user_id) -> int:
    return db.execute(
        select(func.count())
        .select_from(DataKey)
        .where(DataKey.owner_type == "user", DataKey.owner_id == user_id)
    ).scalar_one()


def _counts(db, model, *conditions) -> int:
    return db.execute(select(func.count()).select_from(model).where(*conditions)).scalar_one()


def _run_purge(db) -> dict:
    report = asyncio.run(purge_retention_job({}))
    db.expire_all()  # the job ran in its own session
    return report


def test_old_diary_data_is_purged_and_fresh_data_is_kept(db, provider, make_adult):
    user = make_adult()
    old_entry = _sync_entry(db, provider, user, _old())
    fresh_entry = _sync_entry(db, provider, user, utc_now_naive())
    old_evaluation = _add_evaluation(db, provider, user, _old())
    fresh_evaluation = _add_evaluation(db, provider, user, utc_now_naive())
    db.commit()

    report = _run_purge(db)

    assert report == {
        "diary_entries_purged": 1,
        "diary_versions_purged": 1,
        "rule_evaluations_purged": 1,
        "data_keys_purged": 0,  # a fresh diary row still needs the key
        "vouchers_expired": 0,
    }
    assert db.get(DiaryEntry, old_entry) is None
    assert _counts(db, DiaryEntryVersion, DiaryEntryVersion.entry_id == old_entry) == 0
    assert db.get(DiaryEntry, fresh_entry) is not None
    assert _counts(db, DiaryEntryVersion, DiaryEntryVersion.entry_id == fresh_entry) == 1
    assert db.get(RuleEvaluation, old_evaluation) is None
    assert db.get(RuleEvaluation, fresh_evaluation) is not None


def test_data_keys_are_never_destroyed_by_the_purge(db, provider, make_adult):
    """The owner_type='user' key also wraps phone/birth-date ciphertexts —
    deleting it would make a live user's PII unrecoverable. Keys are removed
    only by the erasure path, never by retention (CC-6)."""
    retired = make_adult()
    _sync_entry(db, provider, retired, _old())
    _add_evaluation(db, provider, retired, _old())
    active = make_adult()
    _sync_entry(db, provider, active, _old())
    _sync_entry(db, provider, active, utc_now_naive())
    db.commit()
    assert _user_data_keys(db, retired.id) == 1

    report = _run_purge(db)

    assert report["diary_entries_purged"] == 2
    assert report["data_keys_purged"] == 0
    assert _user_data_keys(db, retired.id) == 1  # key kept: user PII still needs it
    assert _user_data_keys(db, active.id) == 1


def test_lapsed_vouchers_are_expired_and_settled_ones_are_left_alone(db):
    settings = get_settings()
    lapsed = utc_now_naive() - timedelta(days=settings.retention_voucher_days + 30)
    old_issued = _add_voucher(db, expires_at=lapsed, status="issued")
    old_redeemed = _add_voucher(
        db, expires_at=lapsed, status="redeemed", redeemed_at=lapsed + timedelta(days=1)
    )
    already_expired = _add_voucher(db, expires_at=lapsed, status="expired")
    fresh = _add_voucher(db, expires_at=utc_now_naive() + timedelta(days=30), status="issued")
    db.commit()

    report = _run_purge(db)

    assert report["vouchers_expired"] == 1
    assert db.get(Voucher, old_issued).status == "expired"
    assert db.get(Voucher, old_redeemed).status == "redeemed"  # settled money stays settled
    assert db.get(Voucher, already_expired).status == "expired"
    assert db.get(Voucher, fresh).status == "issued"  # still inside its window


def test_audit_rows_are_never_deleted_and_the_event_is_counts_only(db, provider, make_adult):
    user = make_adult()
    _sync_entry(db, provider, user, _old())
    record_event(
        db,
        event_type="synthetic_pre_existing",
        actor_type="system",
        actor_id=None,
        actor_role=None,
        resource_type="test",
        resource_id=uuid7(),
        payload={"note": "must survive the purge"},
    )
    db.commit()
    snapshot = select(AuditEvent.seq, AuditEvent.row_hash)
    before = [(row.seq, row.row_hash) for row in db.execute(snapshot)]

    report = _run_purge(db)

    after = [(row.seq, row.row_hash) for row in db.execute(snapshot)]
    assert set(before).issubset(set(after))  # every pre-purge row is untouched
    assert len(after) == len(before) + 1  # only the purge's own event was appended

    events = (
        db.execute(select(AuditEvent).where(AuditEvent.event_type == "retention_purge_run"))
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].payload == {"counts": report}
    assert verify_chain(db)["ok"] is True


def test_purge_is_idempotent(db, provider, make_adult):
    user = make_adult()
    _sync_entry(db, provider, user, _old())
    db.commit()

    first = _run_purge(db)
    second = _run_purge(db)

    assert first["diary_entries_purged"] == 1
    assert second == {
        "diary_entries_purged": 0,
        "diary_versions_purged": 0,
        "rule_evaluations_purged": 0,
        "data_keys_purged": 0,
        "vouchers_expired": 0,
    }
    assert _counts(db, AuditEvent, AuditEvent.event_type == "retention_purge_run") == 2
