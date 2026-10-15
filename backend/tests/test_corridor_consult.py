"""Phase 5 corridor consult tests (spec 5.4): patient booking is consent-gated,
the nurse/gynecologist queue is pseudonymous and band-only, the case view decrypts
the computed features snapshot (never raw diary) and audits every view, review
follows the state machine, and telehealth sessions are one-time JWT-gated rooms
with minor consent + chaperone guards."""

import uuid
from datetime import UTC, date, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from app.auth.tokens import create_access_token
from app.config import get_settings
from app.consent.service import consent_state
from app.core.errors import Conflict, NotFound
from app.corridor import consult
from app.diary.service import SyncEntry, compute_features, sync_entries
from app.models import AuditEvent, ConsultConsent, ConsultEvent, ConsultRequest, ConsultSession
from app.rules.loader import build_engine
from app.testkit import auth_headers
from app.users.service import age_of


def _engine():
    return build_engine(get_settings().ontology_dir, allow_unvalidated=True)


def seed_diary(db, provider, user, *, days: int = 14, symptoms: dict | None = None) -> None:
    """Deterministic synthetic diary days so the 14-day window gate is satisfied."""
    today = date.today()
    entries = [
        SyncEntry(
            client_id=uuid.uuid4(),
            idempotency_key=uuid.uuid4().hex,
            version=1,
            payload={
                "date": (today - timedelta(days=i)).isoformat(),
                "pain": 1,
                "bleeding_volume": 1,
                "symptoms": dict(symptoms or {}),
            },
        )
        for i in range(days)
    ]
    sync_entries(db, provider, user, entries)
    db.flush()


def expected_band(db, provider, user):
    """What the deterministic engine says for this user right now (non-negotiable 1:
    the service stores the engine's band, it never invents one)."""
    age = age_of(provider, db, user)
    features, diary_days = compute_features(db, provider, user)
    return _engine().evaluate(age=age, diary_days=diary_days, features=features)


def book(db, provider, user, *, chaperone=False, note=None, county=None, language="en"):
    age = age_of(provider, db, user)
    state = consent_state(db, user, age)
    return consult.book_request(
        db,
        provider,
        user,
        _engine(),
        preferred_county=county,
        preferred_language=language,
        patient_note=note,
        chaperone_requested=chaperone,
        consent_satisfied=state["satisfied"],
    )


def advance_to_scheduled(db, provider, user, staff_id, *, chaperone=False):
    """Book -> (minor consents) -> approved -> scheduled. Returns (request, session)."""
    booked = book(db, provider, user, chaperone=chaperone)
    rid = uuid.UUID(booked["id"])
    if _is_minor(db, provider, user):
        consult.record_consent(
            db,
            request_id=rid,
            kind="guardian_consent",
            method="digital",
            evidence_ref=None,
            staff_id=staff_id,
        )
        consult.record_consent(
            db,
            request_id=rid,
            kind="minor_assent",
            method="digital",
            evidence_ref=None,
            staff_id=staff_id,
        )
    consult.review(
        db,
        provider,
        request_id=rid,
        staff_id=staff_id,
        decision="approved",
        note=None,
    )
    scheduled = consult.schedule(
        db,
        request_id=rid,
        gynecologist_id=staff_id,
        scheduled_at=utc_offset(minutes=30),
        modality="video",
        staff_id=staff_id,
    )
    return rid, uuid.UUID(scheduled["session_id"])


def utc_offset(*, minutes: int) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes)


def _is_minor(db, provider, user) -> bool:
    age = age_of(provider, db, user)
    return age is not None and age < get_settings().self_consent_age


# --- booking ---------------------------------------------------------------


def test_booking_requires_active_consent(db, provider, adult_with_consent):
    user = adult_with_consent
    state = consent_state(db, user, age_of(provider, db, user))
    assert state["satisfied"] is True  # fixture grants self-consent
    booked = book(db, provider, user)
    assert booked["status"] == "pending_nurse_review"


def test_booking_without_consent_is_conflict(db, provider, make_adult):
    user = make_adult()  # registered but no consent grant yet
    state = consent_state(db, user, age_of(provider, db, user))
    assert state["satisfied"] is False
    with pytest.raises(Conflict):
        consult.book_request(
            db,
            provider,
            user,
            _engine(),
            preferred_county=None,
            preferred_language="en",
            patient_note=None,
            chaperone_requested=False,
            consent_satisfied=state["satisfied"],
        )


def test_booking_records_engine_band_and_requests_event(db, provider, adult_with_consent):
    user = adult_with_consent
    seed_diary(db, provider, user)
    booked = book(db, provider, user)
    expected = expected_band(db, provider, user)
    assert booked["band"] == expected.band
    assert booked["band"] in {"GREEN", "YELLOW", "ORANGE", "RED"}
    assert booked["urgent"] == expected.urgent
    assert booked["safeguarding"] == expected.safeguarding
    row = db.get(ConsultRequest, uuid.UUID(booked["id"]))
    assert row.status == "pending_nurse_review"
    events = db.execute(
        select(ConsultEvent).where(ConsultEvent.request_id == row.id)
    ).scalars().all()
    assert [e.event_type for e in events] == ["requested"]


def test_booking_no_diary_keeps_engine_insufficient_data_band(db, provider, adult_with_consent):
    """A user with no diary days gets the engine's insufficient-data band — the
    service never upgrades or invents a band (non-negotiable 1)."""
    user = adult_with_consent
    booked = book(db, provider, user)
    assert booked["band"] == expected_band(db, provider, user).band


def test_booking_self_harm_diary_is_red_and_safeguarding(db, provider, adult_with_consent):
    user = adult_with_consent
    seed_diary(db, provider, user, symptoms={"self_harm": True})
    booked = book(db, provider, user)
    assert booked["band"] == "RED"
    assert booked["urgent"] is True
    assert booked["safeguarding"] is True


def test_booking_stores_note_encrypted_and_never_in_audit(db, provider, adult_with_consent):
    user = adult_with_consent
    booked = book(db, provider, user, note="Synthetic note: ask about clinic hours",
                  county="Nairobi", language="sw")
    row = db.get(ConsultRequest, uuid.UUID(booked["id"]))
    assert row.patient_note_ciphertext is not None
    assert b"Synthetic note" not in row.patient_note_ciphertext
    assert row.preferred_county == "Nairobi"
    assert row.preferred_language == "sw"
    audit_payloads = [
        str(e.payload) for e in db.execute(select(AuditEvent)).scalars()
    ]
    assert not any("Synthetic note" in p for p in audit_payloads)


def test_my_requests_are_own_only(db, provider, adult_with_consent, make_adult):
    mine = book(db, provider, adult_with_consent)
    other = make_adult()
    listed = consult.my_requests(db, other)
    assert listed == []
    assert [r["id"] for r in consult.my_requests(db, adult_with_consent)] == [mine["id"]]


def test_booking_endpoint_envelope(client, db, provider, adult_with_consent, make_adult):
    token = create_access_token(adult_with_consent.id, get_settings())
    resp = client.post(
        "/v1/corridor/consult/requests",
        json={"preferred_county": "Nairobi", "preferred_language": "en"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "pending_nurse_review"

    no_consent = create_access_token(make_adult().id, get_settings())
    resp = client.post(
        "/v1/corridor/consult/requests",
        json={},
        headers=auth_headers(no_consent),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


# --- queue -----------------------------------------------------------------


def test_queue_rows_are_pseudonymous_without_symptom_data(db, provider, adult_with_consent):
    user = adult_with_consent
    seed_diary(db, provider, user)
    booked = book(db, provider, user)
    rows = consult.queue(db, provider)
    assert len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == {
        "request_id",
        "pseudonym",
        "band",
        "urgent",
        "safeguarding",
        "age_band",
        "status",
        "chaperone_requested",
        "preferred_language",
        "created_at",
    }
    assert "features" not in row and "indicators" not in row
    assert row["pseudonym"] == str(user.id)[:8]
    assert row["band"] == booked["band"]
    assert row["age_band"] == "18+"
    assert row["status"] == "pending_nurse_review"


def test_queue_shows_minor_age_band_and_chaperone_request(db, provider, minor_with_consent):
    book(db, provider, minor_with_consent, chaperone=True)
    row = consult.queue(db, provider)[0]
    assert row["age_band"] == "13-17"
    assert row["chaperone_requested"] is True
    assert row["pseudonym"] == str(minor_with_consent.id)[:8]


def test_queue_limit_is_bounded(db, provider, adult_with_consent):
    for _ in range(3):
        book(db, provider, adult_with_consent)
    assert len(consult.queue(db, provider, limit=2)) == 2
    assert len(consult.queue(db, provider, limit=200)) == 3


def test_queue_endpoint_requires_corridor_queue_permission(client, db, make_staff, staff_token):
    nurse = staff_token(make_staff("nurse"))
    resp = client.get("/v1/corridor/queue", headers=auth_headers(nurse))
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []


# --- detail (case view) ----------------------------------------------------


def test_detail_returns_features_and_audits_the_view(db, provider, adult_with_consent,
                                                     make_staff):
    user = adult_with_consent
    seed_diary(db, provider, user)
    booked = book(db, provider, user)
    staff = make_staff("nurse")
    detail = consult.detail(
        db, provider, request_id=uuid.UUID(booked["id"]), staff_id=staff.id
    )
    features, _days = compute_features(db, provider, user)
    assert detail["features"] == features  # computed aggregates only
    assert isinstance(detail["indicators"], list)
    assert detail["consents"] == []
    assert detail["pseudonym"] == str(user.id)[:8]
    assert "answers" not in detail and "payload" not in detail
    events = db.execute(
        select(AuditEvent).where(AuditEvent.event_type == "corridor_case_viewed")
    ).scalars().all()
    assert len(events) == 1
    assert str(events[0].resource_id) == booked["id"]
    assert events[0].actor_id == staff.id


def test_detail_lists_recorded_consents(db, provider, minor_with_consent, make_staff):
    staff = make_staff("nurse")
    booked = book(db, provider, minor_with_consent, chaperone=True)
    rid = uuid.UUID(booked["id"])
    consult.record_consent(
        db, request_id=rid, kind="guardian_consent", method="voice",
        evidence_ref=None, staff_id=staff.id,
    )
    detail = consult.detail(db, provider, request_id=rid, staff_id=staff.id)
    assert [c["kind"] for c in detail["consents"]] == ["guardian_consent"]
    assert detail["age_band"] == "13-17"
    assert detail["chaperone_requested"] is True


def test_detail_unknown_request_is_not_found(db, provider, make_staff):
    with pytest.raises(NotFound):
        consult.detail(
            db, provider, request_id=uuid.uuid4(), staff_id=make_staff("nurse").id
        )


# --- review ----------------------------------------------------------------


def test_review_follows_the_state_machine(db, provider, adult_with_consent, make_staff):
    staff = make_staff("nurse")
    booked = book(db, provider, adult_with_consent)
    rid = uuid.UUID(booked["id"])
    approved = consult.review(
        db, provider, request_id=rid, staff_id=staff.id, decision="approved",
        note="synthetic review note",
    )
    assert approved["status"] == "approved"
    with pytest.raises(Conflict):  # approved -> approved is not an edge
        consult.review(
            db, provider, request_id=rid, staff_id=staff.id, decision="approved", note=None
        )
    with pytest.raises(Conflict):  # approved -> declined is not an edge
        consult.review(
            db, provider, request_id=rid, staff_id=staff.id, decision="declined", note=None
        )
    with pytest.raises(Conflict):  # bad decision value
        consult.review(
            db, provider, request_id=rid, staff_id=staff.id, decision="maybe", note=None
        )


def test_review_decline_and_unknown_request(db, provider, adult_with_consent, make_staff):
    staff = make_staff("nurse")
    booked = book(db, provider, adult_with_consent)
    declined = consult.review(
        db,
        provider,
        request_id=uuid.UUID(booked["id"]),
        staff_id=staff.id,
        decision="declined",
        note=None,
    )
    assert declined["status"] == "declined"
    with pytest.raises(NotFound):
        consult.review(
            db, provider, request_id=uuid.uuid4(), staff_id=staff.id, decision="approved",
            note=None,
        )


def test_review_writes_status_changed_event(db, provider, adult_with_consent, make_staff):
    staff = make_staff("nurse")
    booked = book(db, provider, adult_with_consent)
    consult.review(
        db,
        provider,
        request_id=uuid.UUID(booked["id"]),
        staff_id=staff.id,
        decision="approved",
        note=None,
    )
    events = db.execute(
        select(ConsultEvent)
        .where(ConsultEvent.request_id == uuid.UUID(booked["id"]))
        .order_by(ConsultEvent.id)  # uuid7 is time-ordered
    ).scalars().all()
    assert [(e.status_from, e.status_to) for e in events] == [
        (None, "pending_nurse_review"),
        ("pending_nurse_review", "approved"),
    ]


def test_approved_adult_review_needs_no_minor_consents(db, provider, adult_with_consent,
                                                       make_staff):
    staff = make_staff("nurse")
    booked = book(db, provider, adult_with_consent)
    result = consult.review(
        db,
        provider,
        request_id=uuid.UUID(booked["id"]),
        staff_id=staff.id,
        decision="approved",
        note=None,
    )
    assert result["status"] == "approved"
    assert db.execute(select(ConsultConsent)).scalars().all() == []


# --- minor consent gate -----------------------------------------------------


def test_minor_approval_requires_guardian_consent_and_assent(db, provider,
                                                             minor_with_consent, make_staff):
    staff = make_staff("nurse")
    booked = book(db, provider, minor_with_consent, chaperone=True)
    rid = uuid.UUID(booked["id"])
    with pytest.raises(Conflict, match="minor consult requires recorded consent"):
        consult.review(
            db, provider, request_id=rid, staff_id=staff.id, decision="approved", note=None
        )
    consult.record_consent(
        db, request_id=rid, kind="guardian_consent", method="paper", evidence_ref=None,
        staff_id=staff.id,
    )
    with pytest.raises(Conflict):  # assent still missing
        consult.review(
            db, provider, request_id=rid, staff_id=staff.id, decision="approved", note=None
        )
    consult.record_consent(
        db, request_id=rid, kind="minor_assent", method="digital", evidence_ref=None,
        staff_id=staff.id,
    )
    assert consult.review(
        db, provider, request_id=rid, staff_id=staff.id, decision="approved", note=None
    )["status"] == "approved"
    kinds = {
        c.kind
        for c in db.execute(
            select(ConsultConsent).where(ConsultConsent.request_id == rid)
        ).scalars()
    }
    assert kinds == {"guardian_consent", "minor_assent"}


def test_minor_decline_needs_no_consents(db, provider, minor_with_consent, make_staff):
    staff = make_staff("nurse")
    booked = book(db, provider, minor_with_consent)
    result = consult.review(
        db,
        provider,
        request_id=uuid.UUID(booked["id"]),
        staff_id=staff.id,
        decision="declined",
        note=None,
    )
    assert result["status"] == "declined"


def test_record_consent_validates_kind_method_and_request(db, provider,
                                                          adult_with_consent, make_staff):
    staff = make_staff("nurse")
    booked = book(db, provider, adult_with_consent)
    rid = uuid.UUID(booked["id"])
    with pytest.raises(Conflict, match="unknown consent kind"):
        consult.record_consent(
            db, request_id=rid, kind="verbal_ok", method="digital", evidence_ref=None,
            staff_id=staff.id,
        )
    with pytest.raises(Conflict, match="unknown consent method"):
        consult.record_consent(
            db, request_id=rid, kind="chaperone_confirmed", method="telepathy",
            evidence_ref=None, staff_id=staff.id,
        )
    with pytest.raises(NotFound):
        consult.record_consent(
            db, request_id=uuid.uuid4(), kind="chaperone_confirmed", method="digital",
            evidence_ref=None, staff_id=staff.id,
        )
    recorded = consult.record_consent(
        db, request_id=rid, kind="chaperone_confirmed", method="voice",
        evidence_ref="synthetic-rec-001", staff_id=staff.id,
    )
    assert recorded["kind"] == "chaperone_confirmed"


# --- scheduling + sessions ---------------------------------------------------


def test_schedule_creates_one_time_room_and_validates_modality(db, provider,
                                                               adult_with_consent, make_staff):
    staff = make_staff("gynecologist")
    booked = book(db, provider, adult_with_consent)
    rid = uuid.UUID(booked["id"])
    consult.review(
        db, provider, request_id=rid, staff_id=staff.id, decision="approved", note=None
    )
    with pytest.raises(Conflict, match="modality"):
        consult.schedule(
            db, request_id=rid, gynecologist_id=staff.id,
            scheduled_at=utc_offset(minutes=30), modality="telegram", staff_id=staff.id,
        )
    scheduled = consult.schedule(
        db, request_id=rid, gynecologist_id=staff.id,
        scheduled_at=utc_offset(minutes=30), modality="video", staff_id=staff.id,
    )
    assert scheduled["status"] == "scheduled"
    session = db.get(ConsultSession, uuid.UUID(scheduled["session_id"]))
    assert session.room_name == scheduled["room_name"]
    assert session.recorded is False
    assert session.status == "scheduled"


def test_schedule_requires_approved_request(db, provider, adult_with_consent, make_staff):
    staff = make_staff("gynecologist")
    booked = book(db, provider, adult_with_consent)
    with pytest.raises(Conflict):
        consult.schedule(
            db, request_id=uuid.UUID(booked["id"]), gynecologist_id=staff.id,
            scheduled_at=utc_offset(minutes=30), modality="audio", staff_id=staff.id,
        )


def test_start_session_issues_unrecorded_jwt_room_token(db, provider, adult_with_consent,
                                                        make_staff, settings):
    staff = make_staff("gynecologist")
    _rid, session_id = advance_to_scheduled(
        db, provider, adult_with_consent, staff.id
    )
    started = consult.start_session(db, provider, session_id=session_id, staff_id=staff.id)
    assert started["domain"] == settings.jitsi_domain
    assert session_id.__str__() == started["session_id"]
    payload = jwt.decode(
        started["token"],
        settings.jitsi_app_secret,
        algorithms=["HS256"],
        audience=settings.jitsi_app_id,
    )
    assert payload["room"] == started["room"]
    assert payload["features"] == {"recording": False, "livestreaming": False}
    assert payload["aud"] == settings.jitsi_app_id and payload["iss"] == settings.jitsi_app_id
    assert started["join_url"].startswith(f"https://{settings.jitsi_domain}/")
    session = db.get(ConsultSession, session_id)
    assert session.status == "in_progress"
    assert session.started_at is not None
    with pytest.raises(Conflict):  # one-time room, started twice
        consult.start_session(db, provider, session_id=session_id, staff_id=staff.id)


def test_complete_session_closes_request_and_cannot_repeat(db, provider,
                                                           adult_with_consent, make_staff):
    staff = make_staff("gynecologist")
    rid, session_id = advance_to_scheduled(db, provider, adult_with_consent, staff.id)
    consult.start_session(db, provider, session_id=session_id, staff_id=staff.id)
    with pytest.raises(Conflict, match="outcome"):
        consult.complete_session(
            db, session_id=session_id, outcome="rescheduled", staff_id=staff.id
        )
    completed = consult.complete_session(
        db, session_id=session_id, outcome="completed", staff_id=staff.id
    )
    assert completed["status"] == "completed"
    assert db.get(ConsultRequest, rid).status == "completed"
    with pytest.raises(Conflict):
        consult.complete_session(
            db, session_id=session_id, outcome="completed", staff_id=staff.id
        )


def test_complete_session_before_start_is_conflict(db, provider, adult_with_consent,
                                                   make_staff):
    staff = make_staff("gynecologist")
    _rid, session_id = advance_to_scheduled(db, provider, adult_with_consent, staff.id)
    with pytest.raises(Conflict, match="not in progress"):
        consult.complete_session(
            db, session_id=session_id, outcome="completed", staff_id=staff.id
        )


def test_complete_session_no_show_marks_request_missed(db, provider, adult_with_consent,
                                                       make_staff):
    staff = make_staff("gynecologist")
    rid, session_id = advance_to_scheduled(db, provider, adult_with_consent, staff.id)
    consult.start_session(db, provider, session_id=session_id, staff_id=staff.id)
    consult.complete_session(db, session_id=session_id, outcome="no_show", staff_id=staff.id)
    assert db.get(ConsultRequest, rid).status == "missed"


def test_session_endpoints_unknown_ids_are_not_found(db, provider, make_staff):
    staff = make_staff("gynecologist")
    with pytest.raises(NotFound):
        consult.start_session(db, provider, session_id=uuid.uuid4(), staff_id=staff.id)
    with pytest.raises(NotFound):
        consult.complete_session(
            db, session_id=uuid.uuid4(), outcome="completed", staff_id=staff.id
        )


def test_start_session_endpoint_returns_token_envelope(client, db, provider,
                                                       adult_with_consent, make_staff,
                                                       staff_token):
    gynecologist = make_staff("gynecologist")
    _rid, session_id = advance_to_scheduled(
        db, provider, adult_with_consent, gynecologist.id
    )
    db.commit()
    resp = client.post(
        f"/v1/corridor/sessions/{session_id}/start",
        headers=auth_headers(staff_token(gynecologist)),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert {"session_id", "room", "domain", "token", "join_url"} <= set(data)


# --- chaperone enforcement ---------------------------------------------------


def test_minor_with_chaperone_request_cannot_start_unconfirmed(db, provider,
                                                               minor_with_consent,
                                                               make_staff):
    staff = make_staff("gynecologist")
    _rid, session_id = advance_to_scheduled(
        db, provider, minor_with_consent, staff.id, chaperone=True
    )
    with pytest.raises(Conflict, match="chaperone must be confirmed"):
        consult.start_session(db, provider, session_id=session_id, staff_id=staff.id)
    assert db.get(ConsultSession, session_id).status == "scheduled"


def test_minor_session_starts_after_chaperone_confirmed(db, provider, minor_with_consent,
                                                        make_staff):
    staff = make_staff("gynecologist")
    rid, session_id = advance_to_scheduled(
        db, provider, minor_with_consent, staff.id, chaperone=True
    )
    consult.record_consent(
        db, request_id=rid, kind="chaperone_confirmed", method="voice", evidence_ref=None,
        staff_id=staff.id,
    )
    started = consult.start_session(db, provider, session_id=session_id, staff_id=staff.id)
    assert started["token"]
    assert db.get(ConsultSession, session_id).status == "in_progress"


def test_adult_with_chaperone_request_needs_no_confirmation(db, provider,
                                                            adult_with_consent, make_staff):
    staff = make_staff("gynecologist")
    _rid, session_id = advance_to_scheduled(
        db, provider, adult_with_consent, staff.id, chaperone=True
    )
    started = consult.start_session(db, provider, session_id=session_id, staff_id=staff.id)
    assert started["room"]


def test_minor_without_chaperone_request_starts(db, provider, minor_with_consent, make_staff):
    staff = make_staff("gynecologist")
    _rid, session_id = advance_to_scheduled(db, provider, minor_with_consent, staff.id)
    started = consult.start_session(db, provider, session_id=session_id, staff_id=staff.id)
    assert started["room"]


# --- state machines ----------------------------------------------------------


def test_consult_and_session_state_machines_are_exactly_as_specified():
    assert consult.CONSULT_TRANSITIONS == {
        "pending_nurse_review": {"approved", "declined"},
        "approved": {"scheduled", "cancelled"},
        "scheduled": {"completed", "missed", "cancelled"},
    }
    assert consult.SESSION_TRANSITIONS == {
        "scheduled": {"in_progress", "cancelled"},
        "in_progress": {"completed", "no_show", "cancelled"},
    }
    assert consult.CONSENT_KINDS == {
        "guardian_consent",
        "minor_assent",
        "chaperone_requested",
        "chaperone_confirmed",
    }
    assert consult.CONSENT_METHODS == {"digital", "sms_link", "paper", "voice"}
