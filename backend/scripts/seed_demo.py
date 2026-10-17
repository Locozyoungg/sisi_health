"""Seed the dev/demo database: consent texts, staff (fixed TOTP secrets printed),
and synthetic users with synthetic diaries — the Phase 8 deliverable 5 roster of
40 users spread across the 13-17 / 18-30 / 31-45 bands. NEVER real patient data
(non-negotiable 2). Idempotent — safe to re-run."""

import random
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.auth.staff import create_staff
from app.config import get_settings
from app.consent.service import ensure_consent_texts, grant_consent
from app.crypto.key_provider import DatabaseKeyProvider
from app.db import SessionLocal
from app.diary.service import SyncEntry, sync_entries
from app.models import DiaryEntry, StaffUser
from app.users.service import age_of, create_user, get_by_phone

# Fixed base32 secret ("Hello!") so every demo staff account opens with the
# same authenticator entry (same convention as seed_school_demo.py).
E2E_TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # noqa: S105 — synthetic e2e demo secret, never real

DEMO_PHONES = {
    "adult": "+254700000101",
    "minor": "+254700000102",
    "minor_few_days": "+254700000103",
}

# Phase 8 deliverable 5: the roster grows to 40 users. The three phones above are
# pinned and never move — tests and demos depend on them. The new users continue
# the +2547000001xx block (the +2547000002xx block belongs to the corridor seed
# users, which stay untouched).
NEW_USER_PHONE_START = 110
NEW_USER_AGES = (
    # 12 users aged 13-17 (guardian grant + the minor's own assent)
    (13, 14, 15, 16, 17, 13, 14, 15, 16, 17, 14, 15)
    # 12 users aged 18-30 (self-consent)
    + (18, 20, 22, 24, 26, 28, 30, 19, 21, 23, 25, 27)
    # 13 users aged 31-45 (self-consent)
    + (31, 34, 37, 40, 43, 45, 32, 35, 38, 41, 44, 33, 36)
)
DIARY_DAYS = 90
TOTAL_DEMO_USERS = len(DEMO_PHONES) + len(NEW_USER_AGES)


def _birth_date_for_age(age: int, today: date | None = None) -> date:
    """The birth date that makes `age` exact today (29 February clamps to the 28th)."""
    today = today or date.today()
    try:
        return today.replace(year=today.year - age)
    except ValueError:  # 29 February with a non-leap target year
        return today.replace(year=today.year - age, day=28)


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
            else:
                staff = existing
            # Pin the TOTP secret to the fixed demo secret (same convention as
            # seed_school_demo.py) so every demo staff account opens with the
            # same authenticator entry: base32 "Hello!".
            from app.auth.staff import _open_totp, _seal_totp

            pinned = False
            try:
                pinned = _open_totp(provider, db, staff) == E2E_TOTP_SECRET
            except Exception:  # noqa: BLE001 — unreadable secret means repin
                pinned = False
            if not pinned:
                blob, _key_id = _seal_totp(provider, db, staff.id, E2E_TOTP_SECRET)
                staff.totp_secret_encrypted = blob
                staff.totp_confirmed = True
                db.commit()
            print(f"[seed] staff {email} role={role} pinned to the demo TOTP secret")

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

        # Phase 8 deliverable 5: 37 more users across the 13-17 / 18-30 / 31-45
        # bands, each with a 90-day synthetic diary and the consent its age band
        # requires (minors: guardian grant + the minor's own assent).
        for index, age in enumerate(NEW_USER_AGES):
            phone = f"+2547{NEW_USER_PHONE_START + index:08d}"
            user = get_by_phone(db, phone, settings)
            if user is None:
                user = create_user(
                    db,
                    provider,
                    phone=phone,
                    birth_date=_birth_date_for_age(age),
                    language="sw" if index % 4 == 3 else "en",
                    settings=settings,
                )
                db.commit()
            current_age = age_of(provider, db, user)
            if current_age is not None and current_age >= settings.self_consent_age:
                grant_consent(db, user, event_type="self_grant", method="digital", age=current_age)
            else:
                grant_consent(
                    db, user, event_type="guardian_grant", method="digital", age=current_age
                )
                grant_consent(
                    db, user, event_type="minor_assent", method="digital", age=current_age
                )
            db.commit()
            label = f"user{index:02d} (age {current_age}, {phone})"
            has_entries = (
                db.execute(select(DiaryEntry).where(DiaryEntry.user_id == user.id))
                .scalars()
                .first()
            )
            if has_entries is None:
                sync_entries(
                    db,
                    provider,
                    user,
                    _diary_entries(rng, heavy=index % 5 == 0, days=DIARY_DAYS),
                )
                db.commit()
                print(f"[seed] {label}: {DIARY_DAYS} synthetic diary days")
            else:
                print(f"[seed] {label}: diary already present")

        print(f"[seed] demo roster complete: {TOTAL_DEMO_USERS} users across all age bands")
    print("[seed] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
