"""Phase 5 education content tests (spec 5.4.1): /ontology/content is the single
source of truth, every shipped chunk carries the screening disclaimer flag and is
unvalidated until a clinician signs off, the patient copy never claims low risk or
delivers a diagnosis, and the API projects only public fields."""

import json

import pytest

from app.config import get_settings
from app.core.errors import PreconditionFailed
from app.corridor import education
from app.testkit import auth_headers

EN_DISCLAIMER = "A normal symptom check does not replace screening."
SW_DISCLAIMER = (
    "Uchunguzi wa kawaida wa dalili hauchukui nafasi ya uchunguzi wa saratani ya "
    "mlango wa kizazi."
)
PUBLIC_KEYS = {
    "slug",
    "language",
    "audience",
    "title",
    "body",
    "sources",
    "clinically_validated",
}
SOURCE_TYPES = {"clinical_guideline", "systematic_review", "health_authority", "other"}


def content_files() -> list[dict]:
    directory = get_settings().ontology_dir / "content"
    assert directory.is_dir()
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.json"))
    ]


# --- listing -----------------------------------------------------------------


def test_list_content_returns_the_shipped_chunks():
    items = education.list_content()
    assert len(items) == 12
    assert {item["slug"] for item in items} == {
        "cervical-screening-patient-en",
        "cervical-screening-patient-sw",
        "endometriosis-patient-en",
        "endometriosis-patient-sw",
        "fibroids-patient-en",
        "fibroids-patient-sw",
        "hpv-vaccination-guardian-en",
        "hpv-vaccination-guardian-sw",
        "pcos-patient-en",
        "pcos-patient-sw",
        "period-health-patient-en",
        "period-health-patient-sw",
    }
    for item in items:
        assert set(item.keys()) == PUBLIC_KEYS
        assert item["clinically_validated"] is False
        assert item["body"].strip()


def test_list_content_filters_by_language():
    assert {i["language"] for i in education.list_content(language="en")} == {"en"}
    assert len(education.list_content(language="en")) == 6
    assert len(education.list_content(language="sw")) == 6
    assert education.list_content(language="fr") == []


def test_list_content_filters_by_audience():
    assert len(education.list_content(audience="patient")) == 10
    assert len(education.list_content(audience="guardian")) == 2
    assert education.list_content(audience="clinician") == []


def test_list_content_filters_combine():
    both = education.list_content(language="sw", audience="patient")
    assert [i["slug"] for i in both] == [
        "cervical-screening-patient-sw",
        "endometriosis-patient-sw",
        "fibroids-patient-sw",
        "pcos-patient-sw",
        "period-health-patient-sw",
    ]
    assert education.list_content(language="sw", audience="guardian")[0]["slug"] == (
        "hpv-vaccination-guardian-sw"
    )


# --- shipped file flags ------------------------------------------------------


def test_every_content_file_is_unvalidated_with_empty_signoff():
    files = content_files()
    assert len(files) == 12
    for item in files:
        name = item["slug"]
        if name.startswith(("cervical-screening", "hpv-vaccination")):
            assert item["has_screening_disclaimer"] is True, name
        else:
            assert item["has_screening_disclaimer"] is False, name
        assert item["clinically_validated"] is False, name
        assert item["reviewer_name"] is None, name
        assert item["reviewer_registration_no"] is None, name
        assert item["signed_at"] is None, name
        assert item["language"] in {"en", "sw"}, name
        assert item["audience"] in {"patient", "guardian"}, name
        assert item["title"].strip() and item["body"].strip(), name


def test_every_content_file_cites_sources():
    for item in content_files():
        assert item["sources"], item["slug"]
        for source in item["sources"]:
            assert source["title"].strip()
            assert source["source_type"] in SOURCE_TYPES
            assert source["organization"].strip()
            assert isinstance(source["year"], int)


def test_patient_bodies_carry_the_screening_disclaimer():
    """The mandatory disclaimer applies to SCREENING content (spec 5.4.1);
    non-screening topics (Phase 6) ship the flag false instead."""
    for item in content_files():
        if not item["slug"].startswith(("cervical-screening", "hpv-vaccination")):
            continue
        if item["language"] == "sw":
            assert SW_DISCLAIMER in item["body"], item["slug"]
        else:
            assert EN_DISCLAIMER in item["body"], item["slug"]


def test_content_never_claims_low_risk_or_diagnoses():
    # The copy may explain that SISI does not diagnose; it may never state a risk
    # verdict or hand anyone a diagnosis, prescription or cure.
    forbidden = (
        "low risk",
        "low-risk",
        "no risk",
        "not at risk",
        "you are healthy",
        "you have cancer",
        "diagnosed with",
        "we diagnose",
        "prescrib",
        "will cure",
    )
    for item in content_files():
        text = f"{item['title']}\n{item['body']}".lower()
        for phrase in forbidden:
            assert phrase not in text, f"{item['slug']} contains {phrase!r}"


def test_guardian_content_marks_the_schedule_as_a_placeholder():
    for item in content_files():
        if item["audience"] != "guardian":
            continue
        assert "screening_schedule.json" in item["body"], item["slug"]
        assert "PLACEHOLDER" in item["body"], item["slug"]
        titles = " ".join(source["title"] for source in item["sources"]).lower()
        assert "hpv" in titles or "papillomavirus" in titles, item["slug"]
        assert "who position paper" in titles, item["slug"]


def test_patient_content_cites_who_and_the_kenyan_authority():
    for item in content_files():
        if item["audience"] != "patient":
            continue
        organizations = {source["organization"] for source in item["sources"]}
        assert any("WHO" in org for org in organizations), item["slug"]
        assert any("Kenya" in org for org in organizations), item["slug"]


def test_content_without_the_disclaimer_flag_is_refused(tmp_path, monkeypatch):
    """The loader refuses any chunk that does not declare the screening disclaimer."""
    directory = tmp_path / "content"
    directory.mkdir()
    (directory / "bad.json").write_text(
        json.dumps({"slug": "bad", "language": "en", "audience": "patient"}),
        encoding="utf-8",
    )
    patched = get_settings().model_copy(update={"ontology_dir": tmp_path})
    monkeypatch.setattr(education, "get_settings", lambda: patched)
    education._content_files.cache_clear()
    try:
        with pytest.raises(PreconditionFailed, match="screening disclaimer flag"):
            education.list_content()
    finally:
        education._content_files.cache_clear()


# --- endpoints ---------------------------------------------------------------


def test_education_endpoint_filters_for_staff(client, db, make_staff, staff_token):
    staff = make_staff("nurse")
    db.commit()
    resp = client.get(
        "/v1/corridor/education",
        params={"language": "en", "audience": "guardian"},
        headers=auth_headers(staff_token(staff)),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert [item["slug"] for item in data] == ["hpv-vaccination-guardian-en"]


def test_patient_education_endpoint_is_user_scoped(client, db, adult_with_consent):
    from app.auth.tokens import create_access_token

    db.commit()
    headers = auth_headers(create_access_token(adult_with_consent.id, get_settings()))
    resp = client.get("/v1/corridor/education/patient", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert {item["audience"] for item in data} == {"patient"}
    assert {item["language"] for item in data} == {"en", "sw"}
    assert all(item["clinically_validated"] is False for item in data)
