"""Seed the Phase 5 corridor demo world (idempotent, synthetic ONLY):
- e2e staff: gyn-e2e@sisi.demo (gynecologist) and nurse-e2e@sisi.demo (nurse),
  both with a FIXED TOTP secret so Playwright can compute the code in JS
- 3 synthetic users with fixed phones: adult-a (ORANGE: post-coital bleeding +
  persistent discharge), adult-b (RED: heavy bleeding + dizziness), minor-m
  (ORANGE floor + safeguarding signal, hazard C5)
- 3 facilities (verified / stale / never verified) + 2 indicative pricing stubs
- consult requests (pending nurse review, pending minor with recorded consents,
  reviewed + scheduled session), one referral awaiting patient approval, surgery
  cases at surgical_evaluation and follow_up, and follow-up trackers across the
  state machine including one lost to follow-up
NEVER real patient data (non-negotiable 2). Safe to re-run: the second run is a
no-op and still exits 0.

Both backend defects found while writing this seed are now FIXED in the
services; the savepoint + direct-insert fallbacks below are defensive only and
are bypassed automatically (the seed calls the services first, always):
1. `consult.book_request` used to flush the request before sealing the features
   snapshot (`features_ciphertext` NOT NULL) -> IntegrityError.
2. `referrals.status` is varchar(24); the canonical status is the 18-character
   'awaiting_approval' (fits).

This file deliberately exceeds the 800-line maintainability ceiling: it is a
single-purpose, self-contained demo seeder covering the whole Phase 5 data
model, and splitting it would put the seed order (users -> consent -> diary ->
triage -> corridor artefacts) behind an import for no gain."""

import random
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.audit.service import record_event
from app.auth.staff import _open_totp, _seal_totp, create_staff
from app.config import Settings, get_settings
from app.consent.service import ensure_consent_texts, grant_consent
from app.core.errors import Unauthorized
from app.core.ids import uuid7
from app.core.time import utc_now_naive
from app.corridor import consult, facilities, referral, surgery, tracking
from app.crypto.envelope import open_json, seal_json
from app.crypto.key_provider import DatabaseKeyProvider
from app.db import SessionLocal
from app.diary.service import SyncEntry, compute_features, sync_entries
from app.models import (
    ConsultConsent,
    ConsultEvent,
    ConsultRequest,
    DiaryEntry,
    Facility,
    FollowUpTracker,
    OutcomeLog,
    PricingStub,
    Referral,
    StaffUser,
    SurgeryCase,
    User,
)
from app.rules.engine import RuleEngine
from app.rules.loader import build_engine
from app.users.service import age_of, create_user, get_by_phone

# Fixed base32 secret ("Hello!") so Playwright can compute the TOTP in JS.
E2E_TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # noqa: S105 — synthetic e2e demo secret, never real

GYN_EMAIL = "gyn-e2e@sisi.demo"
NURSE_EMAIL = "nurse-e2e@sisi.demo"

# Fixed synthetic phones (distinct from scripts/seed_demo.py's +2547000001xx block).
PHONE_ADULT_A = "+254700000201"
PHONE_ADULT_B = "+254700000202"
PHONE_MINOR_M = "+254700000203"

DIARY_DAYS = 90

FACILITY_SPECS: tuple[dict[str, Any], ...] = (
    {
        "name": "Nairobi Women's Clinic",
        "county": "Nairobi",
        "level": "tertiary",
        "catchment_counties": ["Nairobi", "Kiambu", "Machakos"],
        "languages": ["en", "sw"],
        "services": ["screening", "consultation", "diagnostics", "surgery"],
        "screening_tests": ["hpv_test", "via", "pap_smear"],
        "estimated_cost_ksh_min": 1500,
        "estimated_cost_ksh_max": 6500,
        "cost_note": "Indicative range only. Confirm current charges with the facility.",
        "phone": "+254700000301",
        "verified_days_ago": 30,
    },
    {
        "name": "Kisumu County Hospital",
        "county": "Kisumu",
        "level": "secondary",
        "catchment_counties": ["Kisumu", "Siaya", "Vihiga"],
        "languages": ["en", "sw", "luo"],
        "services": ["screening", "consultation"],
        "screening_tests": ["via"],
        "estimated_cost_ksh_min": 500,
        "estimated_cost_ksh_max": 2000,
        "cost_note": "Indicative public-facility range. Confirm current charges.",
        "phone": "+254700000302",
        "verified_days_ago": 120,  # stale: older than the 90-day staleness window
    },
    {
        "name": "Mombasa Care Centre",
        "county": "Mombasa",
        "level": "primary",
        "catchment_counties": ["Mombasa", "Kilifi"],
        "languages": ["en", "sw"],
        "services": ["consultation"],
        "screening_tests": [],
        "estimated_cost_ksh_min": 800,
        "estimated_cost_ksh_max": 2500,
        "cost_note": "Indicative range only. Confirm current charges with the facility.",
        "phone": "+254700000303",
        "verified_days_ago": None,  # never verified -> stale
    },
)

PRICING_SOURCE = "Demo partner price list 2026"
PRICING_SPECS: tuple[dict[str, Any], ...] = (
    {
        "procedure": "Cervical screening (HPV test)",
        "amount_ksh_min": 1500,
        "amount_ksh_max": 3000,
        "note": "Indicative partner price, not medical advice.",
    },
    {
        "procedure": "Colposcopy with biopsy",
        "amount_ksh_min": 6000,
        "amount_ksh_max": 15000,
        "note": "Indicative partner price, not medical advice.",
    },
)

SUMMARY: list[str] = []


def _note(line: str) -> None:
    SUMMARY.append(line)


def _birth_date(age_years: int) -> date:
    """A birth date that makes the synthetic user exactly `age_years` old today."""
    today = date.today()
    try:
        return today.replace(year=today.year - age_years)
    except ValueError:  # 29 Feb in a non-leap target year
        return today.replace(year=today.year - age_years, day=28)


def _symptoms(**overrides: bool) -> dict[str, bool]:
    base = {
        "fatigue": False,
        "dyschezia": False,
        "dyspareunia": False,
        "pelvic_pressure": False,
        "urinary_frequency": False,
        "androgenic": False,
        "self_harm": False,
        "dizziness": False,
        "postcoital_bleeding": False,
        "intermenstrual_bleeding": False,
        "postmenopausal_bleeding": False,
        "unusual_discharge": False,
    }
    base.update(overrides)
    return base


def _entry(
    day: date, *, pain: int, bleeding: int, cycle_start: bool, symptoms: dict[str, bool]
) -> SyncEntry:
    return SyncEntry(
        client_id=uuid.uuid4(),
        idempotency_key=f"corridor-seed-{uuid.uuid4().hex[:24]}",
        version=1,
        payload={
            "date": day.isoformat(),
            "pain": pain,
            "bleeding_volume": bleeding,
            "cycle_start": cycle_start,
            "symptoms": symptoms,
        },
    )


def _day(index: int, days: int = DIARY_DAYS) -> date:
    return date.today() - timedelta(days=days - index)


def _adult_a_entries() -> list[SyncEntry]:
    """ORANGE: post-coital bleeding on 2 days + unusual discharge on 6 days."""
    rng = random.Random(101)  # noqa: S311 — deterministic synthetic data, not crypto
    out: list[SyncEntry] = []
    for i in range(DIARY_DAYS):
        out.append(
            _entry(
                _day(i),
                pain=rng.choice([0, 1, 2]),
                bleeding=rng.choice([0, 1, 2]),
                cycle_start=i % 30 == 0,
                symptoms=_symptoms(
                    postcoital_bleeding=i in {30, 61},
                    unusual_discharge=i in {10, 20, 35, 48, 70, 84},
                ),
            )
        )
    return out


def _adult_b_entries() -> list[SyncEntry]:
    """RED: heavy bleeding (volume 3-4) with dizziness on 3 days."""
    rng = random.Random(202)  # noqa: S311 — deterministic synthetic data, not crypto
    out: list[SyncEntry] = []
    for i in range(DIARY_DAYS):
        out.append(
            _entry(
                _day(i),
                pain=rng.choice([1, 2, 3]),
                bleeding=rng.choice([3, 4]),
                cycle_start=i % 28 == 0,
                symptoms=_symptoms(dizziness=i in {12, 40, 66}),
            )
        )
    return out


def _minor_m_entries() -> list[SyncEntry]:
    """ORANGE floor + safeguarding: a minor reporting post-coital bleeding (C5)."""
    rng = random.Random(303)  # noqa: S311 — deterministic synthetic data, not crypto
    out: list[SyncEntry] = []
    for i in range(DIARY_DAYS):
        out.append(
            _entry(
                _day(i),
                pain=rng.choice([0, 1, 2]),
                bleeding=rng.choice([0, 1]),
                cycle_start=i % 28 == 0,
                symptoms=_symptoms(postcoital_bleeding=i in {25, 64}),
            )
        )
    return out


def _ensure_staff(
    db: Session, provider: DatabaseKeyProvider, *, email: str, role: str
) -> StaffUser:
    staff = db.execute(select(StaffUser).where(StaffUser.email == email)).scalars().first()
    if staff is None:
        staff = create_staff(
            db,
            provider,
            email=email,
            password="demo-password-123",  # noqa: S106 — demo seed only
            role=role,
        )
        print(f"[seed] staff {email} (role={role}) created")
    else:
        print(f"[seed] staff {email} (role={role}) already present")
    try:
        current = _open_totp(provider, db, staff)
    except Unauthorized:
        current = None
    if current != E2E_TOTP_SECRET:
        # Pin the fixed e2e secret so the Playwright login can compute TOTP in JS.
        blob, _key_id = _seal_totp(provider, db, staff.id, E2E_TOTP_SECRET)
        staff.totp_secret_encrypted = blob
        db.flush()
        print(f"[seed] {email}: TOTP pinned to the fixed e2e secret")
    return staff


def _ensure_user(
    db: Session,
    provider: DatabaseKeyProvider,
    settings: Settings,
    *,
    label: str,
    phone: str,
    age_years: int,
    minor: bool,
) -> User:
    user = get_by_phone(db, phone, settings)
    if user is None:
        user = create_user(
            db,
            provider,
            phone=phone,
            birth_date=_birth_date(age_years),
            language="en",
            settings=settings,
        )
        db.flush()
        print(f"[seed] user {label} ({phone}, age {age_years}) created")
    else:
        print(f"[seed] user {label} ({phone}) already present")
    age = age_of(provider, db, user)
    if minor:
        grant_consent(db, user, event_type="guardian_grant", method="digital", age=age)
        grant_consent(db, user, event_type="minor_assent", method="digital", age=age)
        db.flush()
        _note(f"consent {label}: guardian_grant + minor_assent (age {age})")
    else:
        grant_consent(db, user, event_type="self_grant", method="digital", age=age)
        db.flush()
        _note(f"consent {label}: self_grant (age {age})")
    return user


def _ensure_diary(
    db: Session,
    provider: DatabaseKeyProvider,
    user: User,
    entries: list[SyncEntry],
    *,
    label: str,
) -> None:
    existing = (
        db.execute(select(DiaryEntry).where(DiaryEntry.user_id == user.id)).scalars().first()
    )
    if existing is not None:
        print(f"[seed] {label}: diary already present")
        _note(f"diary {label}: already present ({DIARY_DAYS} synthetic days)")
        return
    result = sync_entries(db, provider, user, entries)
    print(f"[seed] {label}: {result['accepted']} synthetic diary days")
    _note(f"diary {label}: {result['accepted']} synthetic days")


def _ensure_facility(
    db: Session, *, staff_id: uuid.UUID, spec: dict[str, Any]
) -> Facility:
    facility = (
        db.execute(select(Facility).where(Facility.name == spec["name"])).scalars().first()
    )
    if facility is None:
        created = facilities.create_facility(
            db,
            staff_id=staff_id,
            fields={k: v for k, v in spec.items() if k != "verified_days_ago"},
        )
        facility = db.get(Facility, uuid.UUID(created["id"]))
        if facility is None:  # pragma: no cover — created one line above
            raise RuntimeError("facility disappeared during seeding")
        days = spec["verified_days_ago"]
        if days is not None:
            facility.last_verified_at = utc_now_naive() - timedelta(days=days)
            facility.verified_by = staff_id
            db.flush()
        print(f"[seed] facility {facility.name} created")
    else:
        print(f"[seed] facility {facility.name} already present")
    state = "stale" if facilities.public_view(facility)["stale"] else "verified"
    _note(f"facility {facility.name} ({state}): {facility.id}")
    return facility


def _ensure_pricing(
    db: Session, *, staff_id: uuid.UUID, facility: Facility, spec: dict[str, Any]
) -> PricingStub:
    row = (
        db.execute(
            select(PricingStub).where(
                PricingStub.facility_id == facility.id,
                PricingStub.procedure == spec["procedure"],
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        created = surgery.add_pricing_stub(
            db,
            staff_id=staff_id,
            facility_id=facility.id,
            procedure=spec["procedure"],
            amount_ksh_min=spec["amount_ksh_min"],
            amount_ksh_max=spec["amount_ksh_max"],
            source=PRICING_SOURCE,
            note=spec["note"],
        )
        row = db.get(PricingStub, uuid.UUID(created["id"]))
        if row is None:  # pragma: no cover — created one line above
            raise RuntimeError("pricing stub disappeared during seeding")
        print(f"[seed] pricing stub {row.procedure} created")
    else:
        print(f"[seed] pricing stub {row.procedure} already present")
    _note(
        f"pricing {row.procedure}: {row.id} "
        f"(KES {row.amount_ksh_min}-{row.amount_ksh_max}, indicative={row.indicative})"
    )
    return row


def _book_request_direct(
    db: Session,
    provider: DatabaseKeyProvider,
    engine: RuleEngine,
    user: User,
    *,
    preferred_county: str,
    patient_note: str | None,
    chaperone_requested: bool,
) -> ConsultRequest:
    """Insert-equivalent of `consult.book_request`, sealing the features snapshot
    BEFORE the row is flushed (see `_book_request` for why this exists)."""
    age = age_of(provider, db, user)
    if age is None:
        raise RuntimeError("seeded user has no birth date")
    features, diary_days = compute_features(db, provider, user)
    evaluation = engine.evaluate(age=age, diary_days=diary_days, features=features)
    row = ConsultRequest(
        id=uuid7(),
        user_id=user.id,
        band=evaluation.band,
        urgent=evaluation.urgent,
        safeguarding=evaluation.safeguarding,
        indicators=evaluation.indicators,
        preferred_county=preferred_county,
        preferred_language="en",
        chaperone_requested=chaperone_requested,
    )
    blob, key_id = seal_json(provider, db, "corridor", row.id, features)
    row.features_ciphertext = blob
    row.features_key_id = key_id
    if patient_note:
        note_blob, note_key_id = seal_json(
            provider, db, "corridor", row.id, {"note": patient_note}
        )
        row.patient_note_ciphertext = note_blob
        row.patient_note_key_id = note_key_id
    db.add(row)
    db.flush()
    db.add(
        ConsultEvent(
            id=uuid7(),
            request_id=row.id,
            event_type="requested",
            status_to=row.status,
            actor_type="user",
            actor_id=user.id,
        )
    )
    record_event(
        db,
        event_type="consult_requested",
        actor_type="user",
        actor_id=user.id,
        actor_role=None,
        resource_type="consult_request",
        resource_id=row.id,
        payload={"band": evaluation.band, "safeguarding": evaluation.safeguarding},
    )
    return row


def _book_request(
    db: Session,
    provider: DatabaseKeyProvider,
    engine: RuleEngine,
    user: User,
    *,
    preferred_county: str,
    patient_note: str | None,
    chaperone_requested: bool,
) -> ConsultRequest:
    """Prefer the corridor service. `consult.book_request` currently flushes the
    row before sealing `features_ciphertext`, which is NOT NULL, so the insert
    fails; the seed falls back to an equivalent direct insert (and will use the
    service automatically once the backend flush order is fixed)."""
    savepoint = db.begin_nested()
    try:
        result = consult.book_request(
            db,
            provider,
            user,
            engine,
            preferred_county=preferred_county,
            preferred_language="en",
            patient_note=patient_note,
            chaperone_requested=chaperone_requested,
            consent_satisfied=True,
        )
    except IntegrityError:
        savepoint.rollback()
        print("[seed] note: consult.book_request tripped the features_ciphertext "
              "NOT NULL flush bug; inserting the request directly")
        return _book_request_direct(
            db,
            provider,
            engine,
            user,
            preferred_county=preferred_county,
            patient_note=patient_note,
            chaperone_requested=chaperone_requested,
        )
    savepoint.commit()
    row = db.get(ConsultRequest, uuid.UUID(result["id"]))
    if row is None:  # pragma: no cover — created one line above
        raise RuntimeError("consult request disappeared during seeding")
    return row


def _ensure_request(
    db: Session,
    provider: DatabaseKeyProvider,
    engine: RuleEngine,
    user: User,
    *,
    label: str,
    preferred_county: str,
    patient_note: str | None,
    chaperone_requested: bool,
    live_status: str | None = None,
) -> ConsultRequest:
    """Reuse the user's existing request. When `live_status` is given, only a
    request still in that status counts: the web e2e walks the adult request
    through to 'completed', so a later seed run restores the demo invariant
    (running the seed twice in a row is still a no-op)."""
    query = select(ConsultRequest).where(ConsultRequest.user_id == user.id)
    if live_status is not None:
        query = query.where(ConsultRequest.status == live_status)
    row = db.execute(query.order_by(ConsultRequest.created_at.asc())).scalars().first()
    if row is None:
        row = _book_request(
            db,
            provider,
            engine,
            user,
            preferred_county=preferred_county,
            patient_note=patient_note,
            chaperone_requested=chaperone_requested,
        )
        print(f"[seed] consult request for {label}: {row.status} band={row.band}")
    else:
        print(f"[seed] consult request for {label} already present ({row.status})")
    _note(
        f"consult {label}: {row.id} status={row.status} band={row.band} "
        f"urgent={row.urgent} safeguarding={row.safeguarding} "
        f"chaperone={row.chaperone_requested}"
    )
    return row


def _ensure_minor_consents(
    db: Session, *, request: ConsultRequest, staff_id: uuid.UUID
) -> None:
    kinds = {
        c.kind
        for c in db.execute(
            select(ConsultConsent).where(ConsultConsent.request_id == request.id)
        ).scalars()
    }
    for kind in ("guardian_consent", "minor_assent"):
        if kind in kinds:
            print(f"[seed] consult consent {kind} already recorded")
            continue
        consult.record_consent(
            db,
            request_id=request.id,
            kind=kind,
            method="digital",
            evidence_ref="seed-corridor-demo",
            staff_id=staff_id,
        )
        print(f"[seed] consult consent {kind} recorded")
    _note(f"consult consents: guardian_consent + minor_assent on {request.id}")


def _ensure_scheduled(
    db: Session,
    provider: DatabaseKeyProvider,
    request: ConsultRequest,
    *,
    gynecologist_id: uuid.UUID,
) -> ConsultRequest:
    """Drive a request through approved -> scheduled (idempotent at every step)."""
    if request.status == "pending_nurse_review":
        consult.review(
            db,
            provider,
            request_id=request.id,
            staff_id=gynecologist_id,
            decision="approved",
            note="Demo seed: approved for the corridor walkthrough.",
        )
        print(f"[seed] consult request {request.id} approved")
    if request.status == "approved":
        consult.schedule(
            db,
            request_id=request.id,
            gynecologist_id=gynecologist_id,
            scheduled_at=utc_now_naive() + timedelta(days=2),
            modality="video",
            staff_id=gynecologist_id,
        )
        print(f"[seed] consult session scheduled for request {request.id}")
    _note(
        f"consult (reviewed + scheduled): {request.id} status={request.status} "
        f"gynecologist={gynecologist_id}"
    )
    return request


def _referral_direct(
    db: Session,
    provider: DatabaseKeyProvider,
    *,
    user: User,
    request: ConsultRequest,
    facility: Facility,
    staff_id: uuid.UUID,
    status: str,
) -> Referral:
    """Equivalent of `referral.create_referral` with an explicit status — used when
    the canonical status does not fit the current `referrals.status` column width."""
    age = age_of(provider, db, user)
    features = open_json(provider, db, request.features_ciphertext, request.features_key_id)
    content = referral._section_content(request, features, age, facility)
    row = Referral(
        id=uuid7(),
        user_id=user.id,
        consult_request_id=request.id,
        facility_id=facility.id,
        status=status,
        sections=[s["key"] for s in content["sections"]],
        created_by=staff_id,
    )
    db.add(row)
    db.flush()
    blob, key_id = seal_json(provider, db, "corridor", row.id, content)
    row.letter_ciphertext = blob
    row.letter_key_id = key_id
    db.flush()
    record_event(
        db,
        event_type="referral_drafted",
        actor_type="staff",
        actor_id=staff_id,
        actor_role=None,
        resource_type="referral",
        resource_id=row.id,
        payload={"sections": row.sections},
    )
    return row


def _ensure_referral(
    db: Session,
    provider: DatabaseKeyProvider,
    *,
    user: User,
    request: ConsultRequest,
    facility: Facility,
    staff_id: uuid.UUID,
) -> Referral:
    row = db.execute(select(Referral).where(Referral.user_id == user.id)).scalars().first()
    if row is not None:
        print(f"[seed] referral already present ({row.status})")
        _note(f"referral: {row.id} status={row.status} facility={facility.name}")
        return row
    savepoint = db.begin_nested()
    try:
        created = referral.create_referral(
            db,
            provider,
            staff_id=staff_id,
            request_id=request.id,
            facility_id=facility.id,
        )
    except DataError:
        # Defensive fallback (the status value is 18 chars and fits varchar(24);
        # this path only triggers if the service regresses to a longer value).
        savepoint.rollback()
        print("[seed] WARNING: referral.create_referral failed; inserting directly")
        row = None
        for status in ("awaiting_approval", "draft"):
            nested = db.begin_nested()
            try:
                row = _referral_direct(
                    db,
                    provider,
                    user=user,
                    request=request,
                    facility=facility,
                    staff_id=staff_id,
                    status=status,
                )
            except DataError:
                nested.rollback()
                row = None
                continue
            nested.commit()
            print(f"[seed] referral inserted directly with status={status}")
            break
        if row is None:  # pragma: no cover — defensive: both statuses failed
            raise RuntimeError("could not seed the demo referral") from None
    else:
        savepoint.commit()
        row = db.get(Referral, uuid.UUID(created["id"]))
        if row is None:  # pragma: no cover — created one line above
            raise RuntimeError("referral disappeared during seeding")
        print(f"[seed] referral created ({row.status})")
    _note(f"referral: {row.id} status={row.status} facility={facility.name}")
    return row


def _ensure_surgery_case(
    db: Session,
    *,
    user: User,
    facility: Facility,
    staff_id: uuid.UUID,
    referral_id: uuid.UUID | None,
    transitions: tuple[str, ...],
) -> SurgeryCase:
    case = db.execute(select(SurgeryCase).where(SurgeryCase.user_id == user.id)).scalars().first()
    if case is None:
        created = surgery.create_case(
            db,
            staff_id=staff_id,
            user_id=user.id,
            referral_id=referral_id,
            facility_id=facility.id,
        )
        case = db.get(SurgeryCase, uuid.UUID(created["id"]))
        if case is None:  # pragma: no cover — created one line above
            raise RuntimeError("surgery case disappeared during seeding")
        for to_status in transitions:
            surgery.transition_case(
                db, staff_id=staff_id, case_id=case.id, to_status=to_status, note=None
            )
        print(f"[seed] surgery case created ({case.status})")
    else:
        print(f"[seed] surgery case already present ({case.status})")
    _note(f"surgery case: {case.id} status={case.status} facility={facility.name}")
    return case


def _ensure_outcome(db: Session, *, case: SurgeryCase, staff_id: uuid.UUID) -> None:
    row = db.execute(select(OutcomeLog).where(OutcomeLog.case_id == case.id)).scalars().first()
    if row is not None:
        print("[seed] surgery outcome already present")
        _note(f"surgery outcome: {row.id} category={row.outcome_category}")
        return
    created = surgery.add_outcome(
        db,
        staff_id=staff_id,
        case_id=case.id,
        outcome_category="referred_on",
        note="Demo seed: navigation outcome only.",
    )
    print("[seed] surgery outcome logged")
    _note(f"surgery outcome: {created['id']} category={created['category']}")


def _ensure_trackers(
    db: Session,
    *,
    user: User,
    facility: Facility,
    staff_id: uuid.UUID,
    chains: tuple[tuple[str, ...], ...],
    overdue_referred: bool,
    label: str,
) -> list[FollowUpTracker]:
    rows = list(
        db.execute(select(FollowUpTracker).where(FollowUpTracker.user_id == user.id)).scalars()
    )
    if rows:
        print(f"[seed] {label}: {len(rows)} follow-up trackers already present")
        for row in rows:
            _note(
                f"tracker {label}: {row.id} status={row.status} "
                f"lost_to_follow_up={row.lost_to_follow_up}"
            )
        return rows
    for chain in chains:
        created = tracking.create_tracker(
            db, user_id=user.id, facility_id=facility.id, staff_id=staff_id
        )
        tracker_id = uuid.UUID(created["id"])
        for to_status in chain:
            tracking.transition_tracker(
                db, staff_id=staff_id, tracker_id=tracker_id, to_status=to_status
            )
    if overdue_referred:
        created = tracking.create_tracker(
            db, user_id=user.id, facility_id=facility.id, staff_id=staff_id
        )
        tracker = db.get(FollowUpTracker, uuid.UUID(created["id"]))
        if tracker is None:  # pragma: no cover — created one line above
            raise RuntimeError("tracker disappeared during seeding")
        # Overdue + missed reminders: the state the lost-to-follow-up job derives.
        tracker.due_at = utc_now_naive() - timedelta(days=30)
        tracker.reminders_sent = 2
        tracker.last_reminder_at = utc_now_naive() - timedelta(days=16)
        tracker.lost_to_follow_up = True
        db.flush()
    rows = list(
        db.execute(select(FollowUpTracker).where(FollowUpTracker.user_id == user.id)).scalars()
    )
    print(f"[seed] {label}: {len(rows)} follow-up trackers")
    for row in rows:
        _note(
            f"tracker {label}: {row.id} status={row.status} "
            f"lost_to_follow_up={row.lost_to_follow_up}"
        )
    return rows


def main() -> int:
    settings = get_settings()
    if settings.env not in {"dev", "demo"}:
        print("seed_corridor_demo refuses to run outside dev/demo")
        return 1
    provider = DatabaseKeyProvider(settings)
    engine = build_engine(settings.ontology_dir, allow_unvalidated=True)
    with SessionLocal() as db:
        ensure_consent_texts(db)
        print("[seed] consent texts ensured")

        gyn = _ensure_staff(db, provider, email=GYN_EMAIL, role="gynecologist")
        nurse = _ensure_staff(db, provider, email=NURSE_EMAIL, role="nurse")

        adult_a = _ensure_user(
            db, provider, settings, label="adult-a", phone=PHONE_ADULT_A,
            age_years=30, minor=False,
        )
        adult_b = _ensure_user(
            db, provider, settings, label="adult-b", phone=PHONE_ADULT_B,
            age_years=40, minor=False,
        )
        minor_m = _ensure_user(
            db, provider, settings, label="minor-m", phone=PHONE_MINOR_M,
            age_years=15, minor=True,
        )

        _ensure_diary(db, provider, adult_a, _adult_a_entries(), label="adult-a")
        _ensure_diary(db, provider, adult_b, _adult_b_entries(), label="adult-b")
        _ensure_diary(db, provider, minor_m, _minor_m_entries(), label="minor-m")

        nairobi = _ensure_facility(db, staff_id=gyn.id, spec=FACILITY_SPECS[0])
        kisumu = _ensure_facility(db, staff_id=gyn.id, spec=FACILITY_SPECS[1])
        mombasa = _ensure_facility(db, staff_id=gyn.id, spec=FACILITY_SPECS[2])
        for spec in PRICING_SPECS:
            _ensure_pricing(db, staff_id=gyn.id, facility=nairobi, spec=spec)

        # --- consults -------------------------------------------------------
        request_a = _ensure_request(
            db,
            provider,
            engine,
            adult_a,
            label="adult-a",
            preferred_county="Nairobi",
            patient_note="Demo seed: prefers a morning appointment.",
            chaperone_requested=False,
            live_status="pending_nurse_review",
        )
        request_m = _ensure_request(
            db,
            provider,
            engine,
            minor_m,
            label="minor-m",
            preferred_county="Nairobi",
            patient_note=None,
            chaperone_requested=True,
        )
        _ensure_minor_consents(db, request=request_m, staff_id=nurse.id)
        request_b = _ensure_request(
            db,
            provider,
            engine,
            adult_b,
            label="adult-b",
            preferred_county="Kisumu",
            patient_note=None,
            chaperone_requested=False,
        )
        _ensure_scheduled(db, provider, request_b, gynecologist_id=gyn.id)

        # --- referral, surgery, tracking ------------------------------------
        referral_row = _ensure_referral(
            db,
            provider,
            user=adult_a,
            request=request_a,
            facility=nairobi,
            staff_id=gyn.id,
        )
        evaluation_case = _ensure_surgery_case(
            db,
            user=adult_a,
            facility=nairobi,
            staff_id=gyn.id,
            referral_id=referral_row.id,
            transitions=("surgical_evaluation",),
        )
        _ensure_outcome(db, case=evaluation_case, staff_id=gyn.id)
        _ensure_surgery_case(
            db,
            user=adult_b,
            facility=kisumu,
            staff_id=gyn.id,
            referral_id=None,
            transitions=("surgical_evaluation", "surgery", "follow_up"),
        )
        _ensure_trackers(
            db,
            user=adult_a,
            facility=nairobi,
            staff_id=gyn.id,
            chains=((), ("screened",)),
            overdue_referred=True,
            label="adult-a",
        )
        _ensure_trackers(
            db,
            user=adult_b,
            facility=kisumu,
            staff_id=gyn.id,
            chains=(
                ("screened", "result_received"),
                ("screened", "result_received", "further_assessment"),
                ("screened", "result_received", "further_assessment", "treatment"),
            ),
            overdue_referred=False,
            label="adult-b",
        )

        db.commit()

    print()
    print("[seed] corridor demo summary")
    print(f"  env: {settings.env}")
    print(f"  staff: {GYN_EMAIL} (gynecologist), {NURSE_EMAIL} (nurse)")
    print(f"  staff password: demo-password-123 | TOTP secret: {E2E_TOTP_SECRET}")
    print(f"  users: adult-a {adult_a.id} | adult-b {adult_b.id} | minor-m {minor_m.id}")
    print(f"  facilities: {nairobi.id} | {kisumu.id} | {mombasa.id}")
    for line in SUMMARY:
        print(f"  - {line}")
    print("[seed] corridor demo done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
