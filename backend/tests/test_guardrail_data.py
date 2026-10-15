"""Guardrail data tests (spec 5.4.1): the cervical conversational guardrail cases
ship as data with a closed routing vocabulary, a closed never-actions vocabulary,
all three spec languages, and enough coverage that a red-flag mention or a risk
question can never fall through to a diagnosis or a low-risk statement."""

import json
import re

from app.config import get_settings

ROUTINGS = {"red_flag", "referral_script", "refuse_diagnosis", "screening_education"}
LANGUAGES = {"en", "sw", "sheng"}
NEVER_ACTIONS = {"low_risk_statement", "diagnosis", "prescription"}
CASE_KEYS = {"id", "language", "input", "expected_routing", "never_actions"}

CANCER_CASES = {"cg-01", "cg-02", "cg-03"}
RED_FLAG_IDS = {"cg-04", "cg-05", "cg-06", "cg-07", "cg-08", "cg-09",
                "cg-10", "cg-11", "cg-12", "cg-13", "cg-14"}


def guardrail_file() -> dict:
    path = get_settings().ontology_dir / "guardrail" / "cervical_guardrail_cases.json"
    assert path.exists(), f"guardrail case file missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def cases() -> list[dict]:
    return guardrail_file()["cases"]


def by_id(case_id: str) -> dict:
    return next(case for case in cases() if case["id"] == case_id)


# --- shape -------------------------------------------------------------------


def test_file_declares_the_closed_vocabularies():
    data = guardrail_file()
    assert data["languages"] == ["en", "sw", "sheng"]
    assert set(data["routings"]) == ROUTINGS
    assert set(data["never_actions_vocabulary"]) == NEVER_ACTIONS
    assert "does not diagnose" in data["disclaimer"]


def test_guardrail_cases_are_unvalidated_with_empty_signoff():
    data = guardrail_file()
    assert data["clinically_validated"] is False
    assert data["reviewer_name"] is None
    assert data["reviewer_registration_no"] is None
    assert data["signed_at"] is None


def test_exactly_twenty_cases_with_sequential_ids():
    listed = cases()
    assert len(listed) == 20
    assert [case["id"] for case in listed] == [f"cg-{n:02d}" for n in range(1, 21)]
    assert len({case["id"] for case in listed}) == 20


def test_every_case_has_the_documented_shape():
    for case in cases():
        assert set(case.keys()) == CASE_KEYS, case["id"]
        assert isinstance(case["id"], str) and case["id"]
        assert case["language"] in LANGUAGES, case["id"]
        assert isinstance(case["input"], str) and case["input"].strip(), case["id"]
        assert case["expected_routing"] in ROUTINGS, case["id"]
        assert isinstance(case["never_actions"], list) and case["never_actions"], case["id"]
        for action in case["never_actions"]:
            assert isinstance(action, str)
            assert action in NEVER_ACTIONS, f"{case['id']}: {action}"
        assert len(set(case["never_actions"])) == len(case["never_actions"]), case["id"]


def test_inputs_are_synthetic_and_carry_no_identifiers():
    for case in cases():
        assert not re.search(r"\d{9,}", case["input"]), case["id"]  # no phone-like runs
        assert "@" not in case["input"], case["id"]  # no email-like identifiers
        assert len(case["input"]) <= 200, case["id"]


# --- coverage ----------------------------------------------------------------


def test_all_three_languages_are_covered():
    languages = [case["language"] for case in cases()]
    for language in LANGUAGES:
        assert languages.count(language) >= 3, language
    assert len(languages) == 20


def test_every_routing_value_is_exercised():
    used = {case["expected_routing"] for case in cases()}
    assert used == ROUTINGS


def test_red_flag_cases_cover_every_language():
    red_flags = [case for case in cases() if case["expected_routing"] == "red_flag"]
    assert {case["id"] for case in red_flags} == RED_FLAG_IDS
    assert {case["language"] for case in red_flags} == LANGUAGES


def test_red_flag_cases_are_the_bleeding_and_discharge_mentions():
    for case_id in RED_FLAG_IDS:
        text = by_id(case_id)["input"].lower()
        assert any(
            term in text
            for term in ("damu", "bleed", "discharge", "maji", "period", "hedhi")
        ), case_id


def test_cancer_questions_refuse_a_diagnosis_in_every_language():
    for case_id in CANCER_CASES:
        case = by_id(case_id)
        assert case["expected_routing"] == "refuse_diagnosis", case_id
        assert "diagnosis" in case["never_actions"], case_id
        lowered = case["input"].lower()
        assert "cancer" in lowered or "saratani" in lowered, case_id
    assert {by_id(case_id)["language"] for case_id in CANCER_CASES} == LANGUAGES


def test_low_risk_questions_never_answer_the_risk_question():
    risk_questions = [
        case for case in cases() if "low risk" in case["input"].lower()
        or "hatari ndogo" in case["input"].lower()
    ]
    assert risk_questions, "no low-risk question in the guardrail set"
    for case in risk_questions:
        assert "low_risk_statement" in case["never_actions"], case["id"]
        assert case["expected_routing"] == "refuse_diagnosis", case["id"]


def test_no_case_may_make_a_low_risk_statement():
    """Safety asymmetry: no routing in the set may reassure anyone about risk."""
    for case in cases():
        assert "low_risk_statement" in case["never_actions"], case["id"]


def test_screening_without_symptoms_gets_education():
    education_cases = [
        case for case in cases() if case["expected_routing"] == "screening_education"
    ]
    assert len(education_cases) >= 2
    assert "diagnosis" in {a for c in education_cases for a in c["never_actions"]}


def test_referral_script_cases_do_not_prescribe():
    scripts = [case for case in cases() if case["expected_routing"] == "referral_script"]
    assert scripts
    for case in scripts:
        assert "low_risk_statement" in case["never_actions"], case["id"]
