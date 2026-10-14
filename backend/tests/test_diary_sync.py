"""Diary sync: idempotency, per-field conflict merge (highest version wins, server
timestamp breaks ties), stale-version rejection, and feature extraction."""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.diary.service import (
    SyncEntry,
    _merge_versions,
    compute_features,
    get_entries,
    sync_entries,
)
from app.models import DiaryEntryVersion


def _entry(**overrides) -> SyncEntry:
    base = {
        "client_id": uuid.uuid4(),
        "idempotency_key": uuid.uuid4().hex[:32],
        "version": 1,
        "payload": {"date": date.today().isoformat(), "pain": 3, "symptoms": {"fatigue": False}},
    }
    base.update(overrides)
    return SyncEntry(**base)


def test_idempotency_key_skips_duplicates(db, provider, adult_with_consent):
    key = "duplicate-key-0001"
    first = _entry(idempotency_key=key)
    result = sync_entries(db, provider, adult_with_consent, [first])
    assert result["results"][0]["status"] == "accepted"
    db.commit()
    again = _entry(idempotency_key=key, client_id=first.client_id)
    result = sync_entries(db, provider, adult_with_consent, [again])
    assert result["results"][0]["status"] == "duplicate"
    assert (
        db.execute(select(DiaryEntryVersion)).scalars().all()
        and len(db.execute(select(DiaryEntryVersion)).scalars().all()) == 1
    )


def test_new_version_updates_and_stale_rejected(db, provider, adult_with_consent):
    client_id = uuid.uuid4()
    v1 = _entry(client_id=client_id, version=1, payload={"date": "2026-10-01", "pain": 3})
    sync_entries(db, provider, adult_with_consent, [v1])
    db.commit()
    v2 = _entry(
        client_id=client_id,
        idempotency_key=uuid.uuid4().hex[:32],
        version=2,
        payload={"date": "2026-10-01", "pain": 7},
    )
    result = sync_entries(db, provider, adult_with_consent, [v2])
    assert result["results"][0]["status"] == "accepted"
    db.commit()
    stale = _entry(client_id=client_id, idempotency_key=uuid.uuid4().hex[:32], version=1)
    result = sync_entries(db, provider, adult_with_consent, [stale])
    assert result["results"][0]["status"] == "stale_version"


def test_merge_highest_version_wins_per_field():
    ts = datetime(2026, 10, 1, tzinfo=UTC)
    v1 = {
        "payload": {"pain": 3, "symptoms": {"fatigue": False, "dizziness": False}},
        "version": 1,
        "server_ts": ts,
    }
    v2 = {"payload": {"pain": 7}, "version": 2, "server_ts": ts + timedelta(seconds=1)}
    merged = _merge_versions([v1, v2])
    assert merged["pain"] == 7  # v2 wins
    assert merged["symptoms"] == {"fatigue": False, "dizziness": False}  # v1 fields kept


def test_merge_server_ts_breaks_ties():
    ts = datetime(2026, 10, 1, tzinfo=UTC)
    early = {"payload": {"pain": 3}, "version": 1, "server_ts": ts}
    late = {"payload": {"pain": 5}, "version": 1, "server_ts": ts + timedelta(seconds=30)}
    assert _merge_versions([early, late])["pain"] == 5
    assert _merge_versions([late, early])["pain"] == 5  # order-independent


def test_merge_nested_field_level():
    ts = datetime(2026, 10, 1, tzinfo=UTC)
    v1 = {
        "payload": {"symptoms": {"fatigue": False, "dizziness": False}},
        "version": 1,
        "server_ts": ts,
    }
    v2 = {
        "payload": {"symptoms": {"fatigue": True}},
        "version": 2,
        "server_ts": ts + timedelta(seconds=1),
    }
    merged = _merge_versions([v1, v2])
    assert merged["symptoms"] == {"fatigue": True, "dizziness": False}


def test_compute_features_from_diary(db, provider, adult_with_consent):
    today = date.today()
    entries = []
    for i in range(25):
        payload = {
            "date": (today - timedelta(days=i)).isoformat(),
            "pain": 8 if i % 5 == 0 else 2,
            "bleeding_volume": 3,
            "cycle_start": i % 28 == 0,
            "symptoms": {"fatigue": i % 2 == 0, "dyschezia": i % 9 == 0, "dizziness": i % 11 == 0},
        }
        entries.append(
            SyncEntry(
                client_id=uuid.uuid4(),
                idempotency_key=uuid.uuid4().hex[:32],
                version=1,
                payload=payload,
            )
        )
    result = sync_entries(db, provider, adult_with_consent, entries)
    assert result["accepted"] == 25
    db.commit()

    features, diary_days = compute_features(db, provider, adult_with_consent)
    assert diary_days == 25
    assert features["max_pain_90d"] == 8
    assert features["avg_bleeding_volume_90d"] == 3.0
    assert features["dyschezia"] is True
    assert features["dizziness_signal"] is True
    assert features["fatigue_ratio_30d"] == 0.52  # 13 of 25 days flagged
    assert features["cycle_irregularity_90d"] is None  # only one cycle start in window


def test_readback_returns_merged_entries(db, provider, adult_with_consent):
    client_id = uuid.uuid4()
    sync_entries(
        db,
        provider,
        adult_with_consent,
        [
            _entry(client_id=client_id, version=1, payload={"date": "2026-10-01", "pain": 2}),
            _entry(
                client_id=client_id,
                idempotency_key=uuid.uuid4().hex[:32],
                version=2,
                payload={"date": "2026-10-01", "pain": 6},
            ),
        ],
    )
    db.commit()
    rows = get_entries(db, provider, adult_with_consent)
    assert len(rows) == 1
    assert rows[0]["payload"]["pain"] == 6
    assert rows[0]["version"] == 2


def test_diary_rows_are_encrypted_at_rest(db, provider, adult_with_consent):
    sync_entries(db, provider, adult_with_consent, [_entry()])
    db.commit()
    version = db.execute(select(DiaryEntryVersion)).scalars().first()
    assert b'"pain"' not in version.payload_ciphertext
    assert version.payload_ciphertext != b""
