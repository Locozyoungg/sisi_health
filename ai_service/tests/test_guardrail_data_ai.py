"""Guardrail data tests for the Phase 6 AI suite (spec 5.2, decision D6, hazard HZ-07).

The 157-case file ships as data with a closed routing vocabulary, a closed
never-actions vocabulary, a closed stub-behaviour vocabulary, the plan's exact
category budget and per-language split, and one property that cannot be asserted
from the file alone: every `urgent_script` case must actually hit a real red-flag
pattern in `ontology/redflags/patterns.*.json`. That last test is the 100% red-flag
routing gate at the data level; `eval_guardrails.py --ci` proves it end to end.
"""

import json
import re
from pathlib import Path

import pytest
from app.config import Settings as BackendSettings
from app.rules.loader import build_matcher

from ai_service.config import AISettings
from ai_service.eval.harness import (
    AI_CASES_FILE,
    CASE_OPTIONAL_KEYS,
    CASE_REQUIRED_KEYS,
    CATEGORY_POSTFILTER,
    CATEGORY_PROMPT_INJECTION,
    CERVICAL_CASES_FILE,
    CERVICAL_ROUTING_MAP,
    LANGUAGES,
    NEVER_ACTIONS,
    ROUTINGS,
    CaseSpec,
    CaseSpecError,
    load_ai_cases,
    load_cervical_cases,
    load_guardrail_document,
)
from ai_service.guardrails import ROUTING_EDUCATION, ROUTING_URGENT_SCRIPT, MinorTopicGate
from ai_service.providers.llm import STUB_BEHAVIORS

PLAN_BUDGET = {
    "education": 43,
    "urgent_script": 21,
    "refuse_diagnosis": 24,
    "refuse_prescription": 12,
    "out_of_scope": 12,
    "age_gated_minor": 15,
    "prompt_injection_blocked": 18,
    "postfilter_refusal": 12,
}
# Per-language split. Education is deliberately NOT uniform: the Kiswahili PCOS case
# (ai-157) is a single-language addition, so sw carries one more than en/sheng.
PLAN_PER_LANGUAGE = {
    "education": {"en": 14, "sw": 15, "sheng": 14},
    "urgent_script": {"en": 7, "sw": 7, "sheng": 7},
    "refuse_diagnosis": {"en": 8, "sw": 8, "sheng": 8},
    "refuse_prescription": {"en": 4, "sw": 4, "sheng": 4},
    "out_of_scope": {"en": 4, "sw": 4, "sheng": 4},
    "age_gated_minor": {"en": 5, "sw": 5, "sheng": 5},
    "prompt_injection_blocked": {"en": 6, "sw": 6, "sheng": 6},
    "postfilter_refusal": {"en": 4, "sw": 4, "sheng": 4},
}
DROP_BEHAVIORS = {
    "diagnosis_attempt",
    "prescription_attempt",
    "band_contradiction",
    "off_topic",
}
LEAK_SENTINEL = "SISI_INTERNAL_SYSTEM_PROMPT"
MARKER_FOR_BEHAVIOR = {
    "diagnosis_attempt": "STUB_MARKER_DIAGNOSIS",
    "prescription_attempt": "STUB_MARKER_PRESCRIPTION",
    "band_contradiction": "STUB_MARKER_BAND",
    "off_topic": "STUB_MARKER_OFF_TOPIC",
    "prompt_leak": LEAK_SENTINEL,
}


@pytest.fixture(scope="module")
def ontology_dir(settings: AISettings) -> Path:
    return settings.ontology_dir


@pytest.fixture(scope="module")
def raw_document(ontology_dir: Path) -> dict:
    return load_guardrail_document(ontology_dir, AI_CASES_FILE)


@pytest.fixture(scope="module")
def cases(ontology_dir: Path) -> list[CaseSpec]:
    return load_ai_cases(ontology_dir)


def count_by(cases: list[CaseSpec], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        value = case.category if key == "category" else getattr(case, key)
        counts[value] = counts.get(value, 0) + 1
    return counts


# --- shape ---------------------------------------------------------------------------


def test_file_declares_the_closed_vocabularies(raw_document: dict) -> None:
    assert raw_document["languages"] == ["en", "sw", "sheng"]
    assert set(raw_document["routings"]) == set(ROUTINGS)
    assert set(raw_document["never_actions_vocabulary"]) == set(NEVER_ACTIONS)
    assert set(raw_document["llm_behaviors"]) == set(STUB_BEHAVIORS)
    assert "does not diagnose" in raw_document["disclaimer"]
    assert "H16" in raw_document["source"]


def test_guardrail_cases_are_unvalidated_with_empty_signoff(raw_document: dict) -> None:
    assert raw_document["clinically_validated"] is False
    assert raw_document["reviewer_name"] is None
    assert raw_document["reviewer_registration_no"] is None
    assert raw_document["signed_at"] is None


def test_exactly_one_hundred_and_fifty_seven_sequential_unique_ids(cases: list[CaseSpec]) -> None:
    assert len(cases) == 157
    assert [case.id for case in cases] == [f"ai-{number:03d}" for number in range(1, 158)]
    assert len({case.id for case in cases}) == 157


def test_every_case_carries_only_the_documented_keys(raw_document: dict) -> None:
    allowed = set(CASE_REQUIRED_KEYS) | set(CASE_OPTIONAL_KEYS)
    for raw in raw_document["cases"]:
        assert set(raw) <= allowed, raw["id"]
        assert set(CASE_REQUIRED_KEYS) <= set(raw), raw["id"]
        # the loader is the schema: a bad case must raise, not pass silently
        CaseSpec.from_dict(raw, source=raw["id"])


def test_inputs_are_synthetic_and_carry_no_identifiers(raw_document: dict) -> None:
    for raw in raw_document["cases"]:
        text = raw["input"]
        assert not re.search(r"\d{9,}", text), raw["id"]  # no phone-like runs
        assert "@" not in text, raw["id"]  # no email-like identifiers
        assert len(text) <= 200, raw["id"]
        assert len(text) <= 2000, raw["id"]  # AskRequest.text bound


# --- budget --------------------------------------------------------------------------


def test_category_budget_matches_the_plan(cases: list[CaseSpec]) -> None:
    assert count_by(cases, "category") == PLAN_BUDGET


@pytest.mark.parametrize("category", sorted(PLAN_BUDGET))
def test_every_category_covers_every_language(cases: list[CaseSpec], category: str) -> None:
    languages = [case.language for case in cases if case.category == category]
    assert len(languages) == PLAN_BUDGET[category]
    for language in LANGUAGES:
        assert languages.count(language) == PLAN_PER_LANGUAGE[category][language], (
            category,
            language,
        )


def test_derived_category_matches_the_stored_expectations(cases: list[CaseSpec]) -> None:
    for case in cases:
        if case.category == CATEGORY_PROMPT_INJECTION:
            assert case.expected_routing == "refused"
            assert case.llm_behavior == "prompt_leak"
        elif case.category == CATEGORY_POSTFILTER:
            assert case.expected_routing == "refused"
            assert case.llm_behavior in DROP_BEHAVIORS
        else:
            assert case.category == case.expected_routing


# --- the gates the data has to make possible ------------------------------------------


def test_every_urgent_case_hits_a_real_red_flag_pattern(
    cases: list[CaseSpec], backend_settings: BackendSettings
) -> None:
    """The 100% red-flag routing gate at the data level: the urgent script is only
    reached through the deterministic matcher, so a case that matched nothing would
    be answered by the model instead of by the urgent script."""
    matcher = build_matcher(backend_settings.ontology_dir)
    urgent = [case for case in cases if case.expected_routing == ROUTING_URGENT_SCRIPT]
    assert len(urgent) == PLAN_BUDGET["urgent_script"]
    for case in urgent:
        assert matcher.match_text(case.input), f"{case.id}: no red-flag pattern matched"


def test_urgent_cases_forbid_a_model_call(cases: list[CaseSpec]) -> None:
    for case in cases:
        if case.expected_routing == ROUTING_URGENT_SCRIPT:
            assert "llm_called" in case.never_actions, case.id
            assert "diagnosis" in case.never_actions, case.id


def test_education_cases_require_a_citation(cases: list[CaseSpec]) -> None:
    for case in cases:
        if case.expected_routing == ROUTING_EDUCATION:
            assert "missing_citation" in case.never_actions, case.id
            assert case.band is not None, case.id


def test_refusals_are_decided_before_the_model(cases: list[CaseSpec]) -> None:
    for case in cases:
        if case.expected_routing in {
            "refuse_diagnosis",
            "refuse_prescription",
            "out_of_scope",
            "age_gated_minor",
        }:
            assert "llm_called" in case.never_actions, case.id
        if case.expected_routing == "refuse_diagnosis":
            assert "diagnosis" in case.never_actions, case.id
        if case.expected_routing == "refuse_prescription":
            assert "prescription" in case.never_actions, case.id
            assert "drug_dose" in case.never_actions, case.id
        if case.expected_routing == "out_of_scope":
            assert "off_topic_answer" in case.never_actions, case.id


def test_age_gated_cases_are_minors_on_adult_topics(cases: list[CaseSpec]) -> None:
    gated = [case for case in cases if case.expected_routing == "age_gated_minor"]
    assert len(gated) == PLAN_BUDGET["age_gated_minor"]
    for case in gated:
        assert case.age == 15, case.id
        assert case.band is None, case.id


def test_minor_sexual_health_cases_encode_the_two_step(cases: list[CaseSpec]) -> None:
    """The six sexual-health age_gated_minor cases exercise the two-step (A38): three
    with the answer unknown (minor_has_sex null) and three with "no". The nine procedure
    cases leave the field unset — the hard gate never reads it."""
    gate = MinorTopicGate()
    gated = [case for case in cases if case.expected_routing == "age_gated_minor"]
    procedures = [case for case in gated if gate.is_procedure_gated(case.input)]
    sexual = [case for case in gated if gate.is_sexual_health_gated(case.input)]
    assert len(procedures) == 9
    assert len(sexual) == 6
    assert all(case.minor_has_sex is None for case in procedures), "the hard gate ignores it"
    assert sum(1 for case in sexual if case.minor_has_sex is None) == 3
    assert sum(1 for case in sexual if case.minor_has_sex is False) == 3
    assert all(case.minor_has_sex is not True for case in gated), "the yes branch is a service test"
    for case in gated:
        assert "llm_called" in case.never_actions, case.id
    assert {case.language for case in sexual} == set(LANGUAGES)


def test_prompt_injection_cases_name_the_leak_marker(cases: list[CaseSpec]) -> None:
    injections = [case for case in cases if case.category == CATEGORY_PROMPT_INJECTION]
    assert len(injections) == PLAN_BUDGET["prompt_injection_blocked"]
    for case in injections:
        assert case.llm_behavior == "prompt_leak", case.id
        assert case.marker == LEAK_SENTINEL, case.id
        assert case.never_actions == ("prompt_leak",), case.id
        assert case.band == "YELLOW", case.id


def test_postfilter_cases_exercise_every_misbehaviour(cases: list[CaseSpec]) -> None:
    drops = [case for case in cases if case.category == CATEGORY_POSTFILTER]
    assert len(drops) == PLAN_BUDGET["postfilter_refusal"]
    assert count_by(drops, "llm_behavior") == dict.fromkeys(DROP_BEHAVIORS, 3)
    for case in drops:
        assert case.marker and case.marker.startswith("STUB_MARKER_"), case.id
        assert case.band == "YELLOW", case.id
        assert case.indicators == ("period-pain",), case.id


def test_markers_match_the_declared_behaviour(cases: list[CaseSpec]) -> None:
    for case in cases:
        if case.marker is None:
            continue
        assert MARKER_FOR_BEHAVIOR[case.llm_behavior] == case.marker, case.id


# --- the cervical mapping (D6) ---------------------------------------------------------


def test_cervical_mapping_covers_the_cervical_vocabulary(ontology_dir: Path) -> None:
    document = load_guardrail_document(ontology_dir, CERVICAL_CASES_FILE)
    assert set(CERVICAL_ROUTING_MAP) == set(document["routings"])
    assert set(CERVICAL_ROUTING_MAP.values()) <= set(ROUTINGS)


def test_cervical_cases_load_through_the_mapping(ontology_dir: Path) -> None:
    cervical = load_cervical_cases(ontology_dir)
    assert len(cervical) == 20
    by_id = {case.id: case for case in cervical}
    assert by_id["cg-04"].expected_routing == ROUTING_URGENT_SCRIPT
    assert "llm_called" in by_id["cg-04"].never_actions
    assert by_id["cg-01"].expected_routing == "refuse_diagnosis"
    assert by_id["cg-19"].expected_routing == ROUTING_EDUCATION
    assert "missing_citation" in by_id["cg-19"].never_actions
    assert all(case.llm_behavior == "educational" for case in cervical)
    assert by_id["cg-15"].expected_routing == "refuse_diagnosis"


def test_every_cervical_red_flag_case_hits_the_real_matcher(
    ontology_dir: Path, backend_settings: BackendSettings
) -> None:
    """The eleven cervical cases that assert red_flag must all reach the urgent script
    through the deterministic matcher (spec 5.4.1). They did not before Phase 6: the
    four cervical categories (postcoital, intermenstrual, postmenopausal bleeding,
    unusual discharge) existed as engine rules but had no text patterns, so the
    assistant answered them from content instead of showing the urgent script. This
    test locks the coverage so a future pattern change shows up as a diff."""
    document = load_guardrail_document(ontology_dir, CERVICAL_CASES_FILE)
    matcher = build_matcher(backend_settings.ontology_dir)
    red_flags = [raw for raw in document["cases"] if raw["expected_routing"] == "red_flag"]
    assert len(red_flags) == 11
    unmatched = [raw["id"] for raw in red_flags if not matcher.match_text(raw["input"])]
    assert unmatched == []


# --- the loader is the schema -----------------------------------------------------------


@pytest.mark.parametrize(
    "mutation",
    [
        {"unexpected": True},
        {"language": "fr"},
        {"input": "   "},
        {"expected_routing": "diagnose"},
        {"llm_behavior": "helpful"},
        {"never_actions": []},
        {"never_actions": ["reassure"]},
        {"never_actions": ["diagnosis", "diagnosis"]},
        {"band": "PURPLE"},
        {"age": 12},
        {"indicators": ["Bad Id"]},
        {"accept": ["diagnose"]},
        {"marker": ""},
        {"minor_has_sex": "maybe"},
    ],
)
def test_case_spec_rejects_malformed_cases(mutation: dict) -> None:
    base = {
        "id": "ai-999",
        "language": "en",
        "input": "Tell me about period pain.",
        "expected_routing": "education",
        "never_actions": ["diagnosis"],
        "llm_behavior": "educational",
    }
    base.update(mutation)
    with pytest.raises(CaseSpecError):
        CaseSpec.from_dict(base)


def test_case_spec_requires_every_documented_key() -> None:
    with pytest.raises(CaseSpecError):
        CaseSpec.from_dict({"id": "ai-999", "language": "en"})


def test_case_spec_accepts_alternative_routings() -> None:
    spec = CaseSpec.from_dict(
        {
            "id": "ai-999",
            "language": "en",
            "input": "Tell me about period pain.",
            "expected_routing": "refused",
            "never_actions": ["diagnosis"],
            "llm_behavior": "diagnosis_attempt",
            "accept": ["education"],
        }
    )
    assert spec.accepted_routings == {"refused", "education"}
    assert spec.category == CATEGORY_POSTFILTER
    assert json.dumps(spec.request().model_dump(mode="json"))  # the request is serialisable
