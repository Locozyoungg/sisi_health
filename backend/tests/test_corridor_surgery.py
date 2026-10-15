"""Phase 5 surgery navigation tests (spec 5.4): cases move only along the
diagnostic -> surgical_evaluation -> surgery -> follow_up -> closed path, outcome
logs are limited to generic navigation categories, and pricing stubs are always
indicative and always sourced."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import Conflict, NotFound
from app.corridor import facilities, surgery
from app.models import Facility, OutcomeLog, PricingStub, SurgeryCase, SurgeryEvent
from app.testkit import auth_headers

FULL_PATH = ["surgical_evaluation", "surgery", "follow_up", "closed"]


def add_case(db, staff, user, *, referral_id=None, facility_id=None) -> SurgeryCase:
    created = surgery.create_case(
        db,
        staff_id=staff.id,
        user_id=user.id,
        referral_id=referral_id,
        facility_id=facility_id,
    )
    return db.get(SurgeryCase, uuid.UUID(created["id"]))


def add_facility(db, staff) -> Facility:
    created = facilities.create_facility(
        db,
        staff_id=staff.id,
        fields={"name": "Demo Surgical Hospital", "county": "Nairobi", "level": "tertiary"},
    )
    return db.get(Facility, uuid.UUID(created["id"]))


# --- cases -------------------------------------------------------------------


def test_create_case_starts_at_diagnostic_and_opens_an_event(db, make_staff,
                                                             adult_with_consent):
    staff = make_staff("gynecologist")
    case = add_case(db, staff, adult_with_consent)
    assert case.status == "diagnostic"
    assert case.gynecologist_id == staff.id
    events = db.execute(
        select(SurgeryEvent).where(SurgeryEvent.case_id == case.id)
    ).scalars().all()
    assert [(e.event_type, e.status_to) for e in events] == [("opened", "diagnostic")]


def test_create_case_carries_referral_and_facility_links(db, make_staff,
                                                         adult_with_consent):
    staff = make_staff("gynecologist")
    facility = add_facility(db, staff)
    case = add_case(db, staff, adult_with_consent, facility_id=facility.id)
    assert case.facility_id == facility.id
    listed = surgery.list_cases(db)
    assert [row["id"] for row in listed] == [str(case.id)]
    assert listed[0]["status"] == "diagnostic"
    assert listed[0]["facility_id"] == str(facility.id)


def test_walking_the_documented_path(db, make_staff, adult_with_consent):
    staff = make_staff("gynecologist")
    case = add_case(db, staff, adult_with_consent)
    for to_status in FULL_PATH:
        result = surgery.transition_case(
            db, staff_id=staff.id, case_id=case.id, to_status=to_status, note=None
        )
        assert result["status"] == to_status
    assert db.get(SurgeryCase, case.id).status == "closed"
    transitions = db.execute(
        select(SurgeryEvent)
        .where(SurgeryEvent.case_id == case.id)
        .order_by(SurgeryEvent.created_at, SurgeryEvent.id)  # uuid7 breaks ties
    ).scalars().all()
    assert [(e.status_from, e.status_to) for e in transitions[1:]] == [
        ("diagnostic", "surgical_evaluation"),
        ("surgical_evaluation", "surgery"),
        ("surgery", "follow_up"),
        ("follow_up", "closed"),
    ]


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        ("diagnostic", "surgical_evaluation"),
        ("diagnostic", "cancelled"),
        ("surgical_evaluation", "surgery"),
        ("surgical_evaluation", "cancelled"),
        ("surgery", "follow_up"),
        ("surgery", "cancelled"),
        ("follow_up", "closed"),
        ("follow_up", "cancelled"),
    ],
)
def test_every_valid_transition_edge(db, make_staff, adult_with_consent, from_status,
                                     to_status):
    staff = make_staff("gynecologist")
    case = add_case(db, staff, adult_with_consent)
    walk = {
        "diagnostic": [],
        "surgical_evaluation": ["surgical_evaluation"],
        "surgery": ["surgical_evaluation", "surgery"],
        "follow_up": ["surgical_evaluation", "surgery", "follow_up"],
    }[from_status]
    for step in walk:
        surgery.transition_case(
            db, staff_id=staff.id, case_id=case.id, to_status=step, note=None
        )
    assert db.get(SurgeryCase, case.id).status == from_status
    result = surgery.transition_case(
        db, staff_id=staff.id, case_id=case.id, to_status=to_status, note=None
    )
    assert result["status"] == to_status


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        ("diagnostic", "surgery"),
        ("diagnostic", "follow_up"),
        ("surgical_evaluation", "diagnostic"),
        ("surgery", "diagnostic"),
        ("surgery", "closed"),
        ("follow_up", "surgery"),
        ("closed", "follow_up"),
        ("cancelled", "diagnostic"),
    ],
)
def test_invalid_transitions_are_conflicts(db, make_staff, adult_with_consent, from_status,
                                           to_status):
    staff = make_staff("gynecologist")
    case = add_case(db, staff, adult_with_consent)
    if from_status == "cancelled":
        surgery.transition_case(
            db, staff_id=staff.id, case_id=case.id, to_status="cancelled", note=None
        )
    else:
        walk = {
            "diagnostic": [],
            "surgical_evaluation": ["surgical_evaluation"],
            "surgery": ["surgical_evaluation", "surgery"],
            "follow_up": ["surgical_evaluation", "surgery", "follow_up"],
            "closed": FULL_PATH,
        }[from_status]
        for step in walk:
            surgery.transition_case(
                db, staff_id=staff.id, case_id=case.id, to_status=step, note=None
            )
    with pytest.raises(Conflict, match="cannot move a surgery case"):
        surgery.transition_case(
            db, staff_id=staff.id, case_id=case.id, to_status=to_status, note=None
        )


def test_transition_unknown_case_is_not_found(db, make_staff):
    with pytest.raises(NotFound):
        surgery.transition_case(
            db, staff_id=make_staff("gynecologist").id, case_id=uuid.uuid4(),
            to_status="surgical_evaluation", note=None,
        )


def test_transition_note_is_sanitized(db, make_staff, adult_with_consent):
    staff = make_staff("gynecologist")
    case = add_case(db, staff, adult_with_consent)
    surgery.transition_case(
        db, staff_id=staff.id, case_id=case.id, to_status="surgical_evaluation",
        note="synthetic note 0712345678",
    )
    event = db.execute(
        select(SurgeryEvent).where(SurgeryEvent.status_to == "surgical_evaluation")
    ).scalars().first()
    assert event.note is not None
    assert "0712345678" not in event.note  # phone-like runs are stripped


# --- outcomes ----------------------------------------------------------------


@pytest.mark.parametrize("category", sorted(surgery.OUTCOME_CATEGORIES))
def test_outcome_categories_accepted(db, make_staff, adult_with_consent, category):
    staff = make_staff("gynecologist")
    case = add_case(db, staff, adult_with_consent)
    logged = surgery.add_outcome(
        db, staff_id=staff.id, case_id=case.id, outcome_category=category, note=None
    )
    assert logged["category"] == category
    stored = db.execute(select(OutcomeLog)).scalars().all()
    assert [row.outcome_category for row in stored] == [category]
    assert stored[0].recorded_by == staff.id


def test_outcome_category_enum_is_closed(db, make_staff, adult_with_consent):
    staff = make_staff("gynecologist")
    case = add_case(db, staff, adult_with_consent)
    with pytest.raises(Conflict, match="unknown outcome category"):
        surgery.add_outcome(
            db, staff_id=staff.id, case_id=case.id, outcome_category="biopsy_result",
            note=None,
        )
    assert db.execute(select(OutcomeLog)).scalars().all() == []


def test_outcome_unknown_case_is_not_found(db, make_staff):
    with pytest.raises(NotFound):
        surgery.add_outcome(
            db, staff_id=make_staff("gynecologist").id, case_id=uuid.uuid4(),
            outcome_category="completed_surgery", note=None,
        )


def test_outcome_categories_and_transitions_are_exactly_as_specified():
    assert surgery.OUTCOME_CATEGORIES == {
        "completed_surgery",
        "follow_up_scheduled",
        "referred_on",
        "cancelled",
        "no_show",
    }
    assert surgery.SURGERY_TRANSITIONS == {
        "diagnostic": {"surgical_evaluation", "cancelled"},
        "surgical_evaluation": {"surgery", "cancelled"},
        "surgery": {"follow_up", "cancelled"},
        "follow_up": {"closed", "cancelled"},
    }
    assert surgery.TERMINAL_SURGERY == {"closed", "cancelled"}


# --- pricing stubs -----------------------------------------------------------


def test_pricing_stub_requires_a_source(db, make_staff):
    staff = make_staff("gynecologist")
    facility = add_facility(db, staff)
    with pytest.raises(Conflict, match="requires a source"):
        surgery.add_pricing_stub(
            db, staff_id=staff.id, procedure="Demo procedure", facility_id=facility.id,
            amount_ksh_min=1000, amount_ksh_max=2000, source="", note=None,
        )


def test_pricing_stub_rejects_invalid_ranges(db, make_staff):
    staff = make_staff("gynecologist")
    facility = add_facility(db, staff)
    with pytest.raises(Conflict, match="invalid price range"):
        surgery.add_pricing_stub(
            db, staff_id=staff.id, procedure="Demo procedure", facility_id=facility.id,
            amount_ksh_min=5000, amount_ksh_max=1000, source="demo tariff", note=None,
        )
    with pytest.raises(Conflict, match="invalid price range"):
        surgery.add_pricing_stub(
            db, staff_id=staff.id, procedure="Demo procedure", facility_id=facility.id,
            amount_ksh_min=-1, amount_ksh_max=1000, source="demo tariff", note=None,
        )


def test_pricing_stub_unknown_facility_is_not_found(db, make_staff):
    with pytest.raises(NotFound):
        surgery.add_pricing_stub(
            db, staff_id=make_staff("gynecologist").id, procedure="Demo procedure",
            facility_id=uuid.uuid4(), amount_ksh_min=1000, amount_ksh_max=2000,
            source="demo tariff", note=None,
        )


def test_pricing_stub_is_indicative_and_listed(db, make_staff):
    staff = make_staff("gynecologist")
    facility = add_facility(db, staff)
    created = surgery.add_pricing_stub(
        db, staff_id=staff.id, procedure="Demo diagnostic procedure",
        facility_id=facility.id, amount_ksh_min=15000, amount_ksh_max=45000,
        source="synthetic partner tariff sheet 2026", note=None,
    )
    assert created["indicative"] is True
    listed = surgery.list_pricing(db)
    assert len(listed) == 1
    assert listed[0]["indicative"] is True
    assert listed[0]["currency"] == "KES"
    assert listed[0]["source"] == "synthetic partner tariff sheet 2026"
    assert listed[0]["facility_id"] == str(facility.id)


def test_pricing_stub_filters_by_facility(db, make_staff):
    staff = make_staff("gynecologist")
    one = add_facility(db, staff)
    two = facilities.create_facility(
        db,
        staff_id=staff.id,
        fields={"name": "Second Surgical Hospital", "county": "Kisumu"},
    )
    for facility_id, amount in ((one.id, 1000), (uuid.UUID(two["id"]), 2000)):
        surgery.add_pricing_stub(
            db, staff_id=staff.id, procedure="Demo procedure", facility_id=facility_id,
            amount_ksh_min=amount, amount_ksh_max=amount + 500, source="demo tariff",
            note=None,
        )
    assert len(surgery.list_pricing(db)) == 2
    assert len(surgery.list_pricing(db, facility_id=one.id)) == 1
    assert surgery.list_pricing(db, facility_id=one.id)[0]["amount_ksh_min"] == 1000


def test_pricing_stub_indicative_constraint_is_enforced_in_the_database(db, make_staff):
    """`indicative` is forced True in code AND by a CHECK constraint (spec 5.4)."""
    staff = make_staff("gynecologist")
    facility = add_facility(db, staff)
    db.add(
        PricingStub(
            id=uuid.uuid4(),
            procedure="Demo procedure",
            facility_id=facility.id,
            amount_ksh_min=1000,
            amount_ksh_max=2000,
            source="demo tariff",
            indicative=False,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# --- endpoints ---------------------------------------------------------------


def test_surgery_endpoints_round_trip(client, db, make_staff, staff_token, make_adult):
    staff = make_staff("gynecologist")
    facility = add_facility(db, staff)
    user = make_adult()
    db.commit()
    headers = auth_headers(staff_token(staff))

    resp = client.post(
        "/v1/corridor/surgery/cases",
        json={"user_id": str(user.id), "facility_id": str(facility.id)},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    case_id = resp.json()["data"]["id"]
    assert resp.json()["data"]["status"] == "diagnostic"

    resp = client.post(
        f"/v1/corridor/surgery/cases/{case_id}/transition",
        json={"to_status": "surgery"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"

    resp = client.post(
        f"/v1/corridor/surgery/cases/{case_id}/transition",
        json={"to_status": "surgical_evaluation"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    resp = client.post(
        f"/v1/corridor/surgery/cases/{case_id}/outcomes",
        json={"outcome_category": "follow_up_scheduled"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["category"] == "follow_up_scheduled"

    resp = client.post(
        "/v1/corridor/surgery/pricing-stubs",
        json={
            "procedure": "Demo procedure",
            "facility_id": str(facility.id),
            "amount_ksh_min": 1000,
            "amount_ksh_max": 4000,
            "source": "synthetic partner tariff sheet 2026",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["indicative"] is True

    resp = client.get(
        "/v1/corridor/surgery/pricing-stubs",
        params={"facility_id": str(facility.id)},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["data"]) == 1

    resp = client.get("/v1/corridor/surgery/cases", headers=headers)
    assert resp.status_code == 200, resp.text
    assert [c["status"] for c in resp.json()["data"]] == ["surgical_evaluation"]
