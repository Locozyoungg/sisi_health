"""Phase 5 facility directory tests (spec 5.4.1): screening fields are validated
against the known test set, the 90-day staleness warning is COMPUTED (never
stored), verification resets the clock, and the directory filters by county, level,
language and screening test."""

import uuid
from datetime import timedelta

import pytest

from app.core.errors import Conflict, NotFound
from app.core.time import utc_now_naive
from app.corridor import facilities
from app.models import Facility
from app.testkit import auth_headers

PUBLIC_KEYS = {
    "id",
    "name",
    "county",
    "level",
    "catchment_counties",
    "languages",
    "services",
    "screening_tests",
    "opening_hours",
    "estimated_cost_ksh_min",
    "estimated_cost_ksh_max",
    "cost_note",
    "last_verified_at",
    "stale",
    "warning",
}


def add(db, staff, **fields) -> Facility:
    base = {"name": "Demo Health Centre", "county": "Nairobi", "level": "primary"}
    base.update(fields)
    created = facilities.create_facility(db, staff_id=staff.id, fields=base)
    return db.get(Facility, uuid.UUID(created["id"]))


def view(db, facility_id) -> dict:
    return next(f for f in facilities.list_facilities(db) if f["id"] == str(facility_id))


# --- create / read -----------------------------------------------------------


def test_create_facility_returns_public_view_with_defaults(db, make_staff):
    staff = make_staff("super_admin")
    created = facilities.create_facility(
        db, staff_id=staff.id, fields={"name": "Demo Clinic", "county": "Kisumu"}
    )
    assert set(created.keys()) == PUBLIC_KEYS
    assert created["level"] == "primary"
    assert created["catchment_counties"] == []
    assert created["languages"] == []
    assert created["screening_tests"] == []
    assert created["stale"] is True  # never verified
    assert created["warning"] == facilities.STALE_WARNING


def test_create_facility_requires_name_and_county(db, make_staff):
    staff = make_staff("super_admin")
    with pytest.raises(Conflict, match="name and county are required"):
        facilities.create_facility(db, staff_id=staff.id, fields={"name": "No county"})
    with pytest.raises(Conflict, match="name and county are required"):
        facilities.create_facility(db, staff_id=staff.id, fields={"county": "Nairobi"})


def test_create_facility_validates_level_and_screening_tests(db, make_staff):
    staff = make_staff("super_admin")
    with pytest.raises(Conflict, match="level must be"):
        facilities.create_facility(
            db,
            staff_id=staff.id,
            fields={"name": "Demo", "county": "Nairobi", "level": "dispensary"},
        )
    with pytest.raises(Conflict, match="unknown screening tests"):
        facilities.create_facility(
            db,
            staff_id=staff.id,
            fields={
                "name": "Demo",
                "county": "Nairobi",
                "screening_tests": ["hpv_test", "ct_scan"],
            },
        )


def test_create_facility_rejects_non_list_fields(db, make_staff):
    staff = make_staff("super_admin")
    with pytest.raises(Conflict, match="languages must be a list"):
        facilities.create_facility(
            db,
            staff_id=staff.id,
            fields={"name": "Demo", "county": "Nairobi", "languages": "en"},
        )
    with pytest.raises(Conflict, match="services must be a list"):
        facilities.update_facility(
            db,
            staff_id=staff.id,
            facility_id=add(db, staff).id,
            fields={"services": "screening"},
        )
    # A bare string is never a valid test list either (its characters are unknown).
    with pytest.raises(Conflict, match="unknown screening tests"):
        facilities.create_facility(
            db,
            staff_id=staff.id,
            fields={"name": "Demo", "county": "Nairobi", "screening_tests": "hpv_test"},
        )


def test_screening_test_vocabulary_is_closed():
    assert facilities.SCREENING_TESTS == {"hpv_test", "via", "pap_smear"}


# --- staleness ---------------------------------------------------------------


def test_staleness_constant_is_ninety_days():
    assert facilities.STALENESS_DAYS == 90


def test_facility_never_verified_is_stale_with_warning(db, make_staff):
    facility = add(db, make_staff("super_admin"))
    assert facility.last_verified_at is None
    row = view(db, facility.id)
    assert row["stale"] is True
    assert row["warning"] == facilities.STALE_WARNING


def test_facility_verified_89_days_ago_is_fresh(db, make_staff):
    facility = add(db, make_staff("super_admin"))
    facility.last_verified_at = utc_now_naive() - timedelta(days=89)
    db.flush()
    row = view(db, facility.id)
    assert row["stale"] is False
    assert row["warning"] is None


def test_facility_verified_91_days_ago_is_stale(db, make_staff):
    facility = add(db, make_staff("super_admin"))
    facility.last_verified_at = utc_now_naive() - timedelta(days=91)
    db.flush()
    row = view(db, facility.id)
    assert row["stale"] is True
    assert row["warning"] == facilities.STALE_WARNING


def test_verify_facility_resets_the_staleness_clock(db, make_staff):
    staff = make_staff("super_admin")
    facility = add(db, staff)
    facility.last_verified_at = utc_now_naive() - timedelta(days=200)
    db.flush()
    assert view(db, facility.id)["stale"] is True
    verified = facilities.verify_facility(db, staff_id=staff.id, facility_id=facility.id)
    assert verified["stale"] is False
    assert verified["warning"] is None
    assert verified["last_verified_at"] is not None
    assert db.get(Facility, facility.id).verified_by == staff.id


def test_verify_unknown_facility_is_not_found(db, make_staff):
    with pytest.raises(NotFound):
        facilities.verify_facility(
            db, staff_id=make_staff("super_admin").id, facility_id=uuid.uuid4()
        )


# --- update / delete ---------------------------------------------------------


def test_update_facility_changes_fields_and_validates(db, make_staff):
    staff = make_staff("super_admin")
    facility = add(db, staff)
    updated = facilities.update_facility(
        db,
        staff_id=staff.id,
        facility_id=facility.id,
        fields={
            "name": "Renamed Health Centre",
            "level": "secondary",
            "languages": ["en", "sw"],
            "screening_tests": ["via", "pap_smear"],
            "estimated_cost_ksh_min": 100,
            "estimated_cost_ksh_max": 300,
        },
    )
    assert updated["name"] == "Renamed Health Centre"
    assert updated["level"] == "secondary"
    assert updated["languages"] == ["en", "sw"]
    assert updated["screening_tests"] == ["via", "pap_smear"]
    with pytest.raises(Conflict):
        facilities.update_facility(
            db, staff_id=staff.id, facility_id=facility.id, fields={"level": "clinic"}
        )
    with pytest.raises(NotFound):
        facilities.update_facility(
            db, staff_id=staff.id, facility_id=uuid.uuid4(), fields={"name": "Ghost"}
        )


def test_delete_facility_removes_it_from_the_directory(db, make_staff):
    staff = make_staff("super_admin")
    keep = add(db, staff, name="Keep Me")
    drop = add(db, staff, name="Drop Me")
    facilities.delete_facility(db, staff_id=staff.id, facility_id=drop.id)
    assert db.get(Facility, drop.id) is None
    remaining = [f["id"] for f in facilities.list_facilities(db)]
    assert remaining == [str(keep.id)]
    with pytest.raises(NotFound):
        facilities.delete_facility(db, staff_id=staff.id, facility_id=drop.id)


# --- filtering ---------------------------------------------------------------


def test_list_facilities_filters_by_county_level_language_and_screening(db, make_staff):
    staff = make_staff("super_admin")
    nairobi = add(
        db,
        staff,
        name="Nairobi Referral",
        county="Nairobi",
        level="tertiary",
        languages=["en", "sw"],
        screening_tests=["hpv_test", "via"],
    )
    kisumu = add(
        db,
        staff,
        name="Kisumu Centre",
        county="Kisumu",
        level="primary",
        languages=["en"],
        screening_tests=["pap_smear"],
    )
    assert [f["id"] for f in facilities.list_facilities(db)] == [str(kisumu.id), str(nairobi.id)]
    assert [f["id"] for f in facilities.list_facilities(db, county="Nairobi")] == [
        str(nairobi.id)
    ]
    assert [f["id"] for f in facilities.list_facilities(db, level="primary")] == [str(kisumu.id)]
    assert [f["id"] for f in facilities.list_facilities(db, language="sw")] == [str(nairobi.id)]
    assert [f["id"] for f in facilities.list_facilities(db, screening="pap_smear")] == [
        str(kisumu.id)
    ]
    assert facilities.list_facilities(db, county="Mombasa") == []
    assert facilities.list_facilities(db, level="secondary") == []


def test_list_facilities_endpoint_accepts_filters(client, db, make_staff, staff_token):
    staff = make_staff("nurse")
    add(db, staff, name="Nairobi Referral", county="Nairobi", level="tertiary")
    db.commit()
    resp = client.get(
        "/v1/corridor/facilities",
        params={"county": "Nairobi", "level": "tertiary"},
        headers=auth_headers(staff_token(staff)),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert [f["name"] for f in data] == ["Nairobi Referral"]
    assert data[0]["stale"] is True


def test_create_facility_endpoint_returns_envelope(client, db, make_staff, staff_token):
    staff = make_staff("super_admin")
    db.commit()
    resp = client.post(
        "/v1/corridor/facilities",
        json={"name": "Console Health Centre", "county": "Nakuru", "screening_tests": ["via"]},
        headers=auth_headers(staff_token(staff)),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["name"] == "Console Health Centre"
    assert resp.json()["data"]["screening_tests"] == ["via"]
