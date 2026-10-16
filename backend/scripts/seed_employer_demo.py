"""Seed the Phase 7 employer demo world (idempotent, synthetic ONLY):
- employer 00000000-0000-0000-0000-0000000000e1 "Demo Employer Ltd" (Nairobi),
  the fixed id the web console's employer page uses
- e2e staff employer-admin-e2e@sisi.demo (role employer_admin, FIXED TOTP secret
  so Playwright can compute the code in JS), bound to that employer
- 25 synthetic employees (adults, self-consented, phone block +2547000004xx)
  linked to the employer, each with one sealed `diary.rule_evaluations` row:
  18 GREEN / 4 ORANGE / 2 RED / 1 YELLOW -> the small cells (YELLOW, ORANGE,
  RED) are suppressed by the k-anonymity module on the dashboard
- the employer wallet funded twice (100,000 then 50,000) -> 2 ledger rows
NEVER real patient data (non-negotiable 2). Safe to re-run: the second run is a
no-op and still exits 0."""

import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.auth.staff import _seal_totp, create_staff
from app.config import get_settings
from app.consent.service import ensure_consent_texts, grant_consent
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.crypto.envelope import seal_json
from app.crypto.key_provider import DatabaseKeyProvider
from app.db import SessionLocal
from app.employer import service as employer_service
from app.models import (
    Employer,
    EmployerStaff,
    RuleEvaluation,
    StaffUser,
    User,
    Wallet,
    WalletLedger,
)
from app.users.service import age_of, create_user

EMPLOYER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e1")
EMPLOYER_NAME = "Demo Employer Ltd"
EMPLOYER_COUNTY = "Nairobi"
EMPLOYER_ADMIN_EMAIL = "employer-admin-e2e@sisi.demo"
# Fixed base32 secret ("Hello!") so Playwright can compute the TOTP in JS.
E2E_TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # noqa: S105 — synthetic e2e demo secret, never real
PHONE_BLOCK = "+2547000004"  # distinct from seed_demo (+...01xx) and corridor (+...02xx)
RULE_SET_VERSION = "ontology-1.1"
FUNDINGS = (100_000, 50_000)
# 25 employees: the small band cells (< MIN_K = 5) exercise suppression.
EMPLOYEE_BANDS = ("GREEN",) * 18 + ("ORANGE",) * 4 + ("RED",) * 2 + ("YELLOW",)


def _staff(db, provider, email: str, role: str) -> StaffUser:
    staff = db.execute(select(StaffUser).where(StaffUser.email == email)).scalars().first()
    if staff is not None:
        return staff
    staff = create_staff(
        db,
        provider,
        email=email,
        password="demo-password-123",  # noqa: S106 — demo seed only
        role=role,
    )
    blob, _key_id = _seal_totp(provider, db, staff.id, E2E_TOTP_SECRET)
    staff.totp_secret_encrypted = blob
    db.flush()
    print(f"[seed] staff {email} (role={role}) with fixed e2e TOTP")
    return staff


def _employees(db, provider, settings) -> list[User]:
    """25 synthetic adults, each linked to the employer, self-consented, with one
    sealed rule evaluation. Returns the existing employees when already seeded."""
    existing = db.execute(select(User).where(User.employer_id == EMPLOYER_ID)).scalars().all()
    if existing:
        return list(existing)
    ensure_consent_texts(db)
    employees: list[User] = []
    for index, band in enumerate(EMPLOYEE_BANDS):
        user = create_user(
            db,
            provider,
            phone=f"{PHONE_BLOCK}{index + 1:02d}",
            birth_date=date(2000, 1, 15),
            language="en",
            settings=settings,
        )
        grant_consent(
            db, user, event_type="self_grant", method="digital", age=age_of(provider, db, user)
        )
        user.employer_id = EMPLOYER_ID
        payload = {
            "band": band,
            "indicators": ["synthetic-seed"],
            "urgent": band == "RED",
            "safeguarding": False,
            "rule_set_version": RULE_SET_VERSION,
            "evaluated_at": utc_now_naive().isoformat(),
        }
        blob, key_id = seal_json(provider, db, "user", user.id, payload)
        db.add(
            RuleEvaluation(
                id=uuid7(),
                user_id=user.id,
                rule_set_version=RULE_SET_VERSION,
                payload_ciphertext=blob,
                key_id=key_id,
            )
        )
        db.flush()
        employees.append(user)
    print(f"[seed] {len(employees)} synthetic employees + sealed rule evaluations")
    return employees


def _fund(db) -> None:
    """Fund twice through the service (which appends the ledger rows). Idempotent:
    a run that already has all the funding rows adds nothing."""
    wallet = (
        db.execute(
            select(Wallet).where(Wallet.owner_type == "employer", Wallet.owner_id == EMPLOYER_ID)
        )
        .scalars()
        .first()
    )
    wallet_rows = (
        db.execute(select(WalletLedger).where(WalletLedger.wallet_id == wallet.id)).scalars().all()
        if wallet is not None
        else []
    )
    written = len(wallet_rows)
    if written >= len(FUNDINGS):
        return
    staff = (
        db.execute(select(StaffUser).where(StaffUser.email == EMPLOYER_ADMIN_EMAIL)).scalars().one()
    )
    for amount in FUNDINGS[written:]:
        employer_service.fund(db, staff_id=staff.id, employer_id=EMPLOYER_ID, amount_ksh=amount)
    db.commit()
    print(f"[seed] employer wallet funded: {sum(FUNDINGS):,} KES in {len(FUNDINGS)} ledger rows")


def main() -> int:
    settings = get_settings()
    if settings.env not in {"dev", "demo"}:
        print("seed_employer_demo refuses to run outside dev/demo")
        return 1
    provider = DatabaseKeyProvider(settings)
    with SessionLocal() as db:
        employer = db.get(Employer, EMPLOYER_ID)
        if employer is None:
            employer = Employer(
                id=EMPLOYER_ID, name=EMPLOYER_NAME, county=EMPLOYER_COUNTY, status="active"
            )
            db.add(employer)
            db.flush()
            print(f"[seed] employer {EMPLOYER_NAME} ({EMPLOYER_ID})")

        staff = _staff(db, provider, EMPLOYER_ADMIN_EMAIL, "employer_admin")
        binding = (
            db.execute(
                select(EmployerStaff).where(
                    EmployerStaff.staff_id == staff.id, EmployerStaff.employer_id == EMPLOYER_ID
                )
            )
            .scalars()
            .first()
        )
        if binding is None:
            employer_service.bind_staff(db, staff_id=staff.id, employer_id=EMPLOYER_ID)
            print(f"[seed] bound {EMPLOYER_ADMIN_EMAIL} to the employer")

        employees = _employees(db, provider, settings)
        db.commit()
        _fund(db)
        print(f"[seed] employer demo done ({len(employees)} employees)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
