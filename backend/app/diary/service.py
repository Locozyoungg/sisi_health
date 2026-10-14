"""Diary sync: append-only encrypted entries with the spec's conflict rule —
highest version wins per field, server timestamp breaks ties. Idempotency keys make
sync safe to retry; feature extraction feeds the rules engine."""

import statistics
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.crypto.envelope import open_json, seal_json
from app.crypto.key_provider import DatabaseKeyProvider
from app.models import DiaryEntry, DiaryEntryVersion, User

WINDOW_DAYS = 90
FATIGUE_WINDOW_DAYS = 30
CYCLE_NEAR_DAYS = 3


class SyncEntry(BaseModel):
    client_id: uuid.UUID
    idempotency_key: str = Field(min_length=8, max_length=64)
    version: int = Field(ge=1)
    payload: dict[str, Any]
    created_at: datetime | None = None


def _merge_versions(versions: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-field highest-version-wins; within the same version, server timestamp
    breaks ties. Nested dicts (symptoms) merge recursively by the same rule.
    Returns a new dict (no mutation of inputs)."""

    def pick(pairs: list[tuple[int, datetime, Any]]) -> Any:
        ordered = sorted(pairs, key=lambda p: (p[0], p[1]))
        return ordered[-1][2]

    def merge(pairs: list[tuple[int, datetime, dict[str, Any]]]) -> dict[str, Any]:
        keys = {k for _, _, payload in pairs for k in payload}
        merged: dict[str, Any] = {}
        for key in keys:
            candidates = [(v, ts, payload[key]) for v, ts, payload in pairs if key in payload]
            value = pick(candidates)
            if isinstance(value, dict):
                nested = [
                    (v, ts, payload[key])
                    for v, ts, payload in pairs
                    if key in payload and isinstance(payload[key], dict)
                ]
                merged[key] = merge(nested)
            else:
                merged[key] = value
        return merged

    return merge([(v["version"], v["server_ts"], v["payload"]) for v in versions])


def sync_entries(
    db: Session,
    provider: DatabaseKeyProvider,
    user: User,
    entries: list[SyncEntry],
) -> dict[str, Any]:
    """Batch sync. Idempotency: an idempotency key already seen is skipped and
    reported as duplicate. Edits add a new version of the same client_id."""
    results: list[dict[str, Any]] = []
    for entry in entries:
        existing_key = (
            db.execute(
                select(DiaryEntry).where(DiaryEntry.idempotency_key == entry.idempotency_key)
            )
            .scalars()
            .first()
        )
        if existing_key is not None:
            results.append(
                {"client_id": str(existing_key.client_id), "status": "duplicate", "version": None}
            )
            continue
        row = (
            db.execute(
                select(DiaryEntry).where(
                    DiaryEntry.user_id == user.id, DiaryEntry.client_id == entry.client_id
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            row = DiaryEntry(
                id=uuid7(),
                user_id=user.id,
                client_id=entry.client_id,
                idempotency_key=entry.idempotency_key,
            )
            db.add(row)
            db.flush()
        else:
            latest = (
                db.execute(
                    select(DiaryEntryVersion)
                    .where(DiaryEntryVersion.entry_id == row.id)
                    .order_by(DiaryEntryVersion.version.desc())
                )
                .scalars()
                .first()
            )
            if latest is not None and entry.version <= latest.version:
                results.append(
                    {
                        "client_id": str(entry.client_id),
                        "status": "stale_version",
                        "version": latest.version,
                    }
                )
                continue
        blob, key_id = seal_json(provider, db, "user", user.id, entry.payload)
        db.add(
            DiaryEntryVersion(
                id=uuid7(),
                entry_id=row.id,
                version=entry.version,
                payload_ciphertext=blob,
                key_id=key_id,
                server_ts=utc_now_naive(),
                created_at=entry.created_at or utc_now_naive(),
            )
        )
        row.updated_at = utc_now_naive()
        db.flush()
        results.append(
            {"client_id": str(entry.client_id), "status": "accepted", "version": entry.version}
        )
    accepted = sum(1 for r in results if r["status"] == "accepted")
    from app.audit.service import record_event

    record_event(
        db,
        event_type="diary_synced",
        actor_type="user",
        actor_id=user.id,
        actor_role=None,
        resource_type="user",
        resource_id=user.id,
        payload={"entries": len(entries), "accepted": accepted},  # counts only, never content
    )
    return {"accepted": accepted, "results": results}


def get_entries(db: Session, provider: DatabaseKeyProvider, user: User) -> list[dict[str, Any]]:
    """Merged current view (decrypted) of the user's diary, newest first."""
    rows = (
        db.execute(
            select(DiaryEntry)
            .where(DiaryEntry.user_id == user.id)
            .order_by(DiaryEntry.created_at.desc())
        )
        .scalars()
        .all()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        versions = (
            db.execute(
                select(DiaryEntryVersion)
                .where(DiaryEntryVersion.entry_id == row.id)
                .order_by(DiaryEntryVersion.version.asc(), DiaryEntryVersion.server_ts.asc())
            )
            .scalars()
            .all()
        )
        payloads = [
            {
                "payload": open_json(provider, db, v.payload_ciphertext, v.key_id),
                "version": v.version,
                "server_ts": v.server_ts,
            }
            for v in versions
        ]
        merged = _merge_versions(payloads)
        out.append(
            {
                "client_id": str(row.client_id),
                "version": max(v.version for v in versions),
                "payload": merged,
                "updated_at": row.updated_at,
            }
        )
    return out


def compute_features(
    db: Session, provider: DatabaseKeyProvider, user: User
) -> tuple[dict[str, Any], int]:
    """Deterministic feature extraction over the 90-day window. Keys match the rule
    schema input names exactly; missing data is None (the engine applies asymmetry)."""
    entries = get_entries(db, provider, user)
    today = date.today()
    window_start = today - timedelta(days=WINDOW_DAYS)
    fat_start = today - timedelta(days=FATIGUE_WINDOW_DAYS)
    records: list[dict[str, Any]] = []
    for e in entries:
        payload = e["payload"]
        d = payload.get("date")
        if not d:
            continue
        try:
            day = date.fromisoformat(d)
        except ValueError:
            continue
        if day < window_start:
            continue
        records.append({"date": day, **payload})

    diary_days = len({r["date"] for r in records})
    pain = [r["pain"] for r in records if r.get("pain") is not None]
    bleeding = [r["bleeding_volume"] for r in records if r.get("bleeding_volume") is not None]

    def _in_window(record: dict[str, Any], start: date) -> bool:
        day = record["date"]
        return isinstance(day, date) and day >= start

    fatigue_days = [
        r["date"]
        for r in records
        if _in_window(r, fat_start) and r.get("symptoms", {}).get("fatigue") is True
    ]
    logged_30d = [r["date"] for r in records if _in_window(r, fat_start)]
    cycle_starts = sorted(r["date"] for r in records if r.get("cycle_start") is True)

    pain_days = {r["date"] for r in records if r.get("pain") is not None}
    near_days: set[date] = set()
    for start in cycle_starts:
        for offset in range(-CYCLE_NEAR_DAYS, CYCLE_NEAR_DAYS + 1):
            near_days.add(start + timedelta(days=offset))
    cyclical = len(pain_days & near_days) / len(pain_days) if pain_days else None

    gaps = [(b - a).days for a, b in zip(cycle_starts, cycle_starts[1:], strict=False)]
    irregularity = statistics.pstdev(gaps) if len(gaps) >= 2 else None

    symptoms = [r.get("symptoms", {}) for r in records]
    return {
        "max_pain_90d": max(pain) if pain else None,
        "avg_pain_90d": round(sum(pain) / len(pain), 2) if pain else None,
        "cyclical_pain_ratio_90d": round(cyclical, 2) if cyclical is not None else None,
        "avg_bleeding_volume_90d": round(sum(bleeding) / len(bleeding), 2) if bleeding else None,
        "fatigue_ratio_30d": round(len(fatigue_days) / len(logged_30d), 2) if logged_30d else None,
        "cycle_irregularity_90d": round(irregularity, 2) if irregularity is not None else None,
        "dyschezia": any(s.get("dyschezia") for s in symptoms),
        "dyspareunia": any(s.get("dyspareunia") for s in symptoms),
        "pelvic_pressure": any(s.get("pelvic_pressure") for s in symptoms),
        "urinary_frequency": any(s.get("urinary_frequency") for s in symptoms),
        "androgenic_symptoms": any(s.get("androgenic") for s in symptoms),
        "self_harm_signal": any(s.get("self_harm") for s in symptoms),
        "dizziness_signal": any(s.get("dizziness") for s in symptoms),
    }, diary_days
