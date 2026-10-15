"""Phase 5 corridor referral tests (spec 5.4): the letter is drafted from the
computed features + triage output, the patient previews the FULL letter, approves
only the sections she chooses, can revoke sharing at any time, and the PDF a
facility receives contains exactly the approved sections."""

import base64
import binascii
import re
import uuid
import zlib

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.consent.service import consent_state
from app.core.errors import Conflict, NotFound
from app.corridor import consult, facilities, referral
from app.models import Referral, SharingApproval
from app.rules.loader import build_engine
from app.testkit import auth_headers
from app.users.service import age_of

SECTION_KEYS = [
    "diary_summary",
    "triage_summary",
    "recommendations",
    "facility_details",
    "personal_details",
]


def _book(db, provider, user) -> uuid.UUID:
    age = age_of(provider, db, user)
    state = consent_state(db, user, age)
    booked = consult.book_request(
        db,
        provider,
        user,
        build_engine(get_settings().ontology_dir, allow_unvalidated=True),
        preferred_county="Nairobi",
        preferred_language="en",
        patient_note=None,
        chaperone_requested=False,
        consent_satisfied=state["satisfied"],
    )
    return uuid.UUID(booked["id"])


def draft(db, provider, user, staff, *, facility_id=None) -> Referral:
    created = referral.create_referral(
        db,
        provider,
        staff_id=staff.id,
        request_id=_book(db, provider, user),
        facility_id=facility_id,
    )
    assert created["status"] == "awaiting_approval"
    return db.get(Referral, uuid.UUID(created["id"]))


def pdf_text(content: bytes) -> str:
    """Text of the PDF content streams. reportlab writes them with
    `/Filter [ /ASCII85Decode /FlateDecode ]`, so decode both layers."""
    chunks: list[bytes] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", content, re.S):
        raw = match.group(1).strip()
        try:
            raw = base64.a85decode(raw, adobe=True)
        except (ValueError, binascii.Error):
            pass  # not ASCII85: plain or Flate-only stream
        try:
            chunks.append(zlib.decompressobj().decompress(raw))
        except zlib.error:
            chunks.append(raw)  # uncompressed stream: use it as-is
    return b"\n".join(chunks).decode("latin-1", errors="replace")


# --- drafting ----------------------------------------------------------------


def test_create_referral_drafts_every_section(db, provider, adult_with_consent, make_staff):
    staff = make_staff("nurse")
    row = draft(db, provider, adult_with_consent, staff)
    assert row.sections == SECTION_KEYS
    assert row.approved_sections == []
    assert row.status == "awaiting_approval"
    letter = referral.preview(db, provider, user=adult_with_consent, referral_id=row.id)
    assert [s["key"] for s in letter["sections"]] == SECTION_KEYS
    titles = {s["key"]: s["title"] for s in letter["sections"]}
    assert titles["triage_summary"] == "Health check summary"
    assert titles["diary_summary"].startswith("Diary summary")
    triage = next(s for s in letter["sections"] if s["key"] == "triage_summary")
    assert referral.DISCLAIMER in triage["body"]


def test_create_referral_with_facility_uses_the_directory(db, provider,
                                                          adult_with_consent, make_staff):
    staff = make_staff("nurse")
    facility = facilities.create_facility(
        db,
        staff_id=staff.id,
        fields={
            "name": "Demo Sub-County Hospital",
            "county": "Nairobi",
            "level": "secondary",
            "screening_tests": ["hpv_test", "via"],
            "estimated_cost_ksh_min": 200,
            "estimated_cost_ksh_max": 500,
        },
    )
    row = draft(db, provider, adult_with_consent, staff, facility_id=uuid.UUID(facility["id"]))
    assert row.facility_id == uuid.UUID(facility["id"])
    letter = referral.preview(db, provider, user=adult_with_consent, referral_id=row.id)
    body = next(s for s in letter["sections"] if s["key"] == "facility_details")["body"]
    assert "Demo Sub-County Hospital" in body
    assert "Nairobi" in body
    assert "hpv_test" in body


def test_create_referral_unknown_request_is_not_found(db, provider, make_staff):
    with pytest.raises(NotFound):
        referral.create_referral(
            db,
            provider,
            staff_id=make_staff("nurse").id,
            request_id=uuid.uuid4(),
            facility_id=None,
        )


def test_create_referral_unknown_facility_is_not_found(db, provider, adult_with_consent,
                                                       make_staff):
    staff = make_staff("nurse")
    with pytest.raises(NotFound):
        referral.create_referral(
            db,
            provider,
            staff_id=staff.id,
            request_id=_book(db, provider, adult_with_consent),
            facility_id=uuid.uuid4(),
        )


def test_list_referrals_reports_status_and_sections(db, provider, adult_with_consent,
                                                    make_staff):
    staff = make_staff("nurse")
    row = draft(db, provider, adult_with_consent, staff)
    rows = referral.list_referrals(db)
    assert [r["id"] for r in rows] == [str(row.id)]
    assert rows[0]["status"] == "awaiting_approval"
    assert rows[0]["sections"] == SECTION_KEYS
    assert rows[0]["approved_sections"] == []


# --- patient preview / approval ----------------------------------------------


def test_preview_is_owner_only(db, provider, adult_with_consent, make_adult, make_staff):
    staff = make_staff("nurse")
    row = draft(db, provider, adult_with_consent, staff)
    with pytest.raises(NotFound):
        referral.preview(db, provider, user=make_adult(), referral_id=row.id)
    with pytest.raises(NotFound):
        referral.preview(db, provider, user=adult_with_consent, referral_id=uuid.uuid4())


def test_approve_subset_records_sharing_approval(db, provider, adult_with_consent,
                                                 make_staff):
    staff = make_staff("nurse")
    row = draft(db, provider, adult_with_consent, staff)
    result = referral.approve(
        db,
        user=adult_with_consent,
        referral_id=row.id,
        approved_sections=["triage_summary", "facility_details"],
    )
    assert result["status"] == "approved"
    assert result["approved_sections"] == ["triage_summary", "facility_details"]
    stored = db.get(Referral, row.id)
    assert stored.approved_at is not None
    assert stored.approved_sections == ["triage_summary", "facility_details"]
    approvals = db.execute(select(SharingApproval)).scalars().all()
    assert [(a.action, a.resource_type) for a in approvals] == [("approved", "referral")]
    assert approvals[0].resource_id == row.id
    assert approvals[0].user_id == adult_with_consent.id


def test_approve_unknown_section_is_conflict(db, provider, adult_with_consent, make_staff):
    row = draft(db, provider, adult_with_consent, make_staff("nurse"))
    with pytest.raises(Conflict, match="unknown sections"):
        referral.approve(
            db,
            user=adult_with_consent,
            referral_id=row.id,
            approved_sections=["everything_please"],
        )


def test_approve_empty_section_list_is_conflict(db, provider, adult_with_consent, make_staff):
    row = draft(db, provider, adult_with_consent, make_staff("nurse"))
    with pytest.raises(Conflict, match="at least one section"):
        referral.approve(
            db, user=adult_with_consent, referral_id=row.id, approved_sections=[]
        )


def test_approve_wrong_owner_or_status_is_rejected(db, provider, adult_with_consent,
                                                   make_adult, make_staff):
    row = draft(db, provider, adult_with_consent, make_staff("nurse"))
    with pytest.raises(NotFound):
        referral.approve(
            db, user=make_adult(), referral_id=row.id, approved_sections=["triage_summary"]
        )
    referral.approve(
        db, user=adult_with_consent, referral_id=row.id, approved_sections=["triage_summary"]
    )
    with pytest.raises(Conflict, match="not awaiting approval"):
        referral.approve(
            db, user=adult_with_consent, referral_id=row.id, approved_sections=["triage_summary"]
        )


# --- sending -----------------------------------------------------------------


def test_send_requires_patient_approval(db, provider, adult_with_consent, make_staff):
    staff = make_staff("nurse")
    row = draft(db, provider, adult_with_consent, staff)
    with pytest.raises(Conflict, match="only an approved referral can be sent"):
        referral.mark_sent(db, staff_id=staff.id, referral_id=row.id)
    referral.approve(
        db, user=adult_with_consent, referral_id=row.id, approved_sections=["triage_summary"]
    )
    sent = referral.mark_sent(db, staff_id=staff.id, referral_id=row.id)
    assert sent["status"] == "sent"
    assert db.get(Referral, row.id).sent_at is not None


def test_send_unknown_referral_is_not_found(db, make_staff):
    with pytest.raises(NotFound):
        referral.mark_sent(db, staff_id=make_staff("nurse").id, referral_id=uuid.uuid4())


# --- revoking ----------------------------------------------------------------


def test_revoke_after_send_records_revocation_and_is_not_repeatable(db, provider,
                                                                    adult_with_consent,
                                                                    make_staff):
    staff = make_staff("nurse")
    row = draft(db, provider, adult_with_consent, staff)
    referral.approve(
        db, user=adult_with_consent, referral_id=row.id, approved_sections=["triage_summary"]
    )
    referral.mark_sent(db, staff_id=staff.id, referral_id=row.id)
    revoked = referral.revoke(db, user=adult_with_consent, referral_id=row.id)
    assert revoked["status"] == "revoked"
    assert db.get(Referral, row.id).revoked_at is not None
    with pytest.raises(Conflict, match="already revoked"):
        referral.revoke(db, user=adult_with_consent, referral_id=row.id)
    actions = [a.action for a in db.execute(select(SharingApproval)).scalars()]
    assert actions == ["approved", "revoked"]


def test_revoke_before_approval_works_and_is_owner_only(db, provider, adult_with_consent,
                                                        make_adult, make_staff):
    row = draft(db, provider, adult_with_consent, make_staff("nurse"))
    with pytest.raises(NotFound):
        referral.revoke(db, user=make_adult(), referral_id=row.id)
    revoked = referral.revoke(db, user=adult_with_consent, referral_id=row.id)
    assert revoked["status"] == "revoked"
    with pytest.raises(Conflict, match="already revoked"):
        referral.revoke(db, user=adult_with_consent, referral_id=row.id)


# --- PDF ---------------------------------------------------------------------


def test_pdf_requires_patient_approval(db, provider, adult_with_consent, make_staff):
    row = draft(db, provider, adult_with_consent, make_staff("nurse"))
    with pytest.raises(Conflict, match="not approved by the patient"):
        referral.letter_pdf(db, provider, referral_id=row.id)
    referral.approve(
        db, user=adult_with_consent, referral_id=row.id, approved_sections=["triage_summary"]
    )
    referral.revoke(db, user=adult_with_consent, referral_id=row.id)
    with pytest.raises(Conflict):
        referral.letter_pdf(db, provider, referral_id=row.id)


def test_pdf_unknown_referral_is_not_found(db, provider):
    with pytest.raises(NotFound):
        referral.letter_pdf(db, provider, referral_id=uuid.uuid4())


def test_pdf_contains_only_the_approved_sections(db, provider, adult_with_consent,
                                                 make_staff):
    row = draft(db, provider, adult_with_consent, make_staff("nurse"))
    referral.approve(
        db, user=adult_with_consent, referral_id=row.id, approved_sections=["triage_summary"]
    )
    content = referral.letter_pdf(db, provider, referral_id=row.id)
    assert content[:4] == b"%PDF"
    text = pdf_text(content)
    assert "SISI Health" in text
    assert "Health check summary" in text  # approved section
    assert "Diary summary" not in text  # NOT approved -> absent
    assert "Recommended next step" not in text
    assert "Personal details" not in text


def test_pdf_includes_all_sections_once_approved(db, provider, adult_with_consent,
                                                 make_staff):
    row = draft(db, provider, adult_with_consent, make_staff("nurse"))
    referral.approve(
        db, user=adult_with_consent, referral_id=row.id, approved_sections=list(SECTION_KEYS)
    )
    text = pdf_text(referral.letter_pdf(db, provider, referral_id=row.id))
    assert "Health check summary" in text
    assert "Diary summary" in text
    assert "Recommended next step" in text
    assert "Personal details" in text


def test_pdf_endpoint_serves_the_letter(client, db, provider, adult_with_consent,
                                        make_staff, staff_token):
    staff = make_staff("gynecologist")  # corridor:referrals
    row = draft(db, provider, adult_with_consent, staff)
    referral.approve(
        db, user=adult_with_consent, referral_id=row.id, approved_sections=["triage_summary"]
    )
    db.commit()
    resp = client.get(
        f"/v1/corridor/referrals/{row.id}/pdf", headers=auth_headers(staff_token(staff))
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_preview_endpoint_is_user_scoped(client, db, provider, adult_with_consent,
                                         make_adult, make_staff):
    from app.auth.tokens import create_access_token

    row = draft(db, provider, adult_with_consent, make_staff("nurse"))
    db.commit()
    token = create_access_token(adult_with_consent.id, get_settings())
    resp = client.get(f"/v1/corridor/referrals/{row.id}/preview", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert [s["key"] for s in resp.json()["data"]["sections"]] == SECTION_KEYS

    stranger = create_access_token(make_adult().id, get_settings())
    resp = client.get(
        f"/v1/corridor/referrals/{row.id}/preview", headers=auth_headers(stranger)
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_approve_and_revoke_endpoints_envelope(client, db, provider, adult_with_consent,
                                               make_staff):
    from app.auth.tokens import create_access_token

    row = draft(db, provider, adult_with_consent, make_staff("nurse"))
    db.commit()
    token = create_access_token(adult_with_consent.id, get_settings())
    resp = client.post(
        f"/v1/corridor/referrals/{row.id}/approve",
        json={"approved_sections": ["nothing_like_this"]},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"
    resp = client.post(
        f"/v1/corridor/referrals/{row.id}/approve",
        json={"approved_sections": ["triage_summary"]},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "approved"
    resp = client.post(
        f"/v1/corridor/referrals/{row.id}/revoke", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "revoked"
