"""Seed the dev/demo database: consent texts, staff (fixed TOTP secrets printed),
and synthetic users with synthetic diaries. NEVER real patient data
(non-negotiable 2). Idempotent — safe to re-run."""

import random
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.auth.staff import create_staff, setup_totp
from app.config import get_settings
from app.consent.service import ensure_consent_texts, grant_consent
from app.crypto.key_provider import DatabaseKeyProvider
from app.db import SessionLocal
from app.diary.service import SyncEntry, sync_entries
from app.models import DiaryEntry, StaffUser
from app.users.service import age_of, create_user, get_by_phone

DEMO_PHONES = {
    "adult": "+254700000101",
    "minor": "+254700000102",
    "minor_few_days": "+254700000103",
}


def _diary_entries(rng: random.Random, heavy: bool, days: int) -> list[SyncEntry]:
    entries = []
    for i in range(days):
        day = date.today() - timedelta(days=days - i)
        payload = {
            "date": day.isoformat(),
            "pain": rng.choice([0, 1, 2, 3, 8 if heavy and i % 4 == 0 else 2]),
            "bleeding_volume": 3 if heavy else rng.choice([0, 1, 2]),
            "cycle_start": i % 28 == 0,
            "symptoms": {
                "fatigue": heavy and i % 2 == 0,
                "dyschezia": heavy and i % 9 == 0,
                "dizziness": False,
                "dyspareunia": False,
                "pelvic_pressure": False,
                "urinary_frequency": False,
                "androgenic": False,
                "self_harm": False,
            },
        }
        entries.append(
            SyncEntry(
                client_id=uuid.uuid4(),
                idempotency_key=f"seed-{uuid.uuid4().hex[:24]}",
                version=1,
                payload=payload,
            )
        )
    return entries


def main() -> int:
    settings = get_settings()
    if settings.env not in {"dev", "demo"}:
        print("seed_demo refuses to run outside dev/demo")
        return 1
    provider = DatabaseKeyProvider(settings)
    with SessionLocal() as db:
        ensure_consent_texts(db)
        print("[seed] consent texts ensured")

        for role in ("super_admin", "nurse", "gynecologist"):
            email = f"{role}@sisi.demo"
            existing = (
                db.execute(select(StaffUser).where(StaffUser.email == email)).scalars().first()
            )
            if existing is None:
                staff = create_staff(
                    db, provider, email=email, password="demo-password-123", role=role  # noqa: S106 — demo seed only
                )
                uri = setup_totp(db, provider, staff)
                db.commit()
                print(f"[seed] staff {email} role={role} TOTP URI: {uri}")
            else:
                print(f"[seed] staff {email} already seeded")

        rng = random.Random(42)  # noqa: S311 — deterministic synthetic data, not crypto
        for name, phone, birth, days in (
            ("adult", DEMO_PHONES["adult"], date(1998, 5, 2), 90),
            ("minor", DEMO_PHONES["minor"], date(2011, 2, 20), 90),
            ("minor_few_days", DEMO_PHONES["minor_few_days"], date(2012, 6, 1), 13),
        ):
            user = get_by_phone(db, phone, settings)
            if user is None:
                user = create_user(
                    db, provider, phone=phone, birth_date=birth, language="en", settings=settings
                )
                db.commit()
            age = age_of(provider, db, user)
            if age is not None and age >= settings.self_consent_age:
                grant_consent(db, user, event_type="self_grant", method="digital", age=age)
            else:
                grant_consent(db, user, event_type="guardian_grant", method="digital", age=age)
                grant_consent(db, user, event_type="minor_assent", method="digital", age=age)
            db.commit()
            has_entries = (
                db.execute(select(DiaryEntry).where(DiaryEntry.user_id == user.id))
                .scalars()
                .first()
            )
            if has_entries is None:
                sync_entries(
                    db, provider, user, _diary_entries(rng, heavy=(name == "adult"), days=days)
                )
                db.commit()
                print(f"[seed] {name} ({phone}): {days} synthetic diary days")
            else:
                print(f"[seed] {name} ({phone}): diary already present")
    print("[seed] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
