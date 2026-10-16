"""Deterministic guardrails (HZ-07/HZ-08): scope gate, minor gate, pre-LLM
refusal detectors, and every post-filter rule — including the negated-diagnosis
control ("you do not have…" is still a diagnosis statement) and band mismatch,
which is how a model is stopped from becoming a second band authority (A36)."""

import re

import pytest
from app.config import get_settings as get_backend_settings
from app.rules.loader import build_matcher

from ai_service.guardrails import (
    LANGUAGES,
    MINOR_NO_SEX_TEXTS,
    MINOR_SEX_CHECK_TEXTS,
    MINOR_YES_NURSE_LINE,
    REFUSAL_TEXTS,
    ROUTING_AGE_GATED_MINOR,
    ROUTING_OUT_OF_SCOPE,
    ROUTING_REFUSE_DIAGNOSIS,
    ROUTING_REFUSE_PRESCRIPTION,
    ROUTING_REFUSED,
    SAFEGUARDING_LINES,
    TOPIC_KEYWORDS,
    URGENT_SCRIPTS,
    VIOLATION_BAND_MISMATCH,
    VIOLATION_DIAGNOSIS_CLAIM,
    VIOLATION_DRUG_DOSE,
    VIOLATION_MISSING_CITATION,
    VIOLATION_OFF_TOPIC_ANSWER,
    VIOLATION_PRESCRIPTION,
    VIOLATION_PROMPT_LEAK,
    DiagnosisAskDetector,
    MinorTopicGate,
    PostFilter,
    PrescriptionAskDetector,
    TopicFilter,
    build_urgent_script,
    citations_for,
    minor_no_sex_text,
    refusal_text,
)
from ai_service.prompts import MINOR_SEX_FRAMING_LINE
from ai_service.providers.llm import (
    BAND_CONTRADICTION_MARKER,
    DIAGNOSIS_MARKER,
    OFF_TOPIC_MARKER,
    PRESCRIPTION_MARKER,
    PROMPT_LEAK_MARKER,
)
from ai_service.rag import SearchHit


@pytest.fixture()
def backend_settings():
    return get_backend_settings()


@pytest.fixture()
def postfilter() -> PostFilter:
    return PostFilter()


def _hit(chunk_id: str, title: str = "Cervical screening", language: str = "en") -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        slug=chunk_id.split("#")[0],
        title=title,
        text="text",
        language=language,
        audience="patient",
        score=0.9,
    )


# --- topic filter -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("I have period pain that comes every month", "en"),
        ("Nina maumivu ya hedhi", "sw"),
        ("Damu inatoka kama kawaida", "sw"),
        ("Niko na discharge ya ajabu", "sheng"),
        ("My periods are irregular", "sheng"),
        ("Can I get screened for cervical cancer?", "en"),
    ],
)
def test_topic_filter_accepts_womens_health(text: str, language: str) -> None:
    assert TopicFilter().is_womens_health(text, language)


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("How do I cook chapati?", "en"),
        ("Who won the football match last night?", "en"),
        ("Nipe recipe ya ugali", "sw"),
        ("Tell me about the politics of this county", "en"),
        ("", "en"),
    ],
)
def test_topic_filter_rejects_off_topic(text: str, language: str) -> None:
    assert not TopicFilter().is_womens_health(text, language)


def test_sw_topic_filter_accepts_a_code_switched_endometriosis_question() -> None:
    """Regression: TOPIC_KEYWORDS["sw"] carried the truncated "endometrios". The
    keyword match is word-bounded, so a truncated form can never fire on the real
    word — a Kiswahili question about endometriosis was refused as out of scope."""
    assert TopicFilter().is_womens_health("Endometriosis ni nini?", "sw")
    assert "endometriosis" in TOPIC_KEYWORDS["sw"]
    assert "endometrios" not in TOPIC_KEYWORDS["sw"]


def test_sw_topic_filter_accepts_a_kiswahili_pcos_question() -> None:
    """Regression (A38 companion): the sw list carried no PCOS keyword at all — the
    en/sw union applies only to sheng — so a Kiswahili "PCOS ni nini?" was refused as
    out of scope. The full Kiswahili form is the maintainer's wording."""
    assert TopicFilter().is_womens_health("PCOS ni nini?", "sw")
    for keyword in ("pcos", "ovari zenye uvimbe", "ugonjwa wa ovari zenye uvimbe"):
        assert keyword in TOPIC_KEYWORDS["sw"], keyword
    assert "pcos" in TOPIC_KEYWORDS["en"]
    assert "pcos" in TOPIC_KEYWORDS["sheng"]  # explicit, not only via the en union


def test_topic_keyword_lists_carry_no_truncated_terms() -> None:
    """A keyword that is a strict prefix of a full clinical term only works when the
    full term is listed alongside it (e.g. "fibroid" and "fibroids"). A prefix that
    stands alone can never match — the same defect class as "endometrios"."""
    canonical = (
        "endometriosis",
        "fibroids",
        "polycystic",
        "pregnancy",
        "menopause",
        "discharge",
        "cervical",
        "bleeding",
        "screening",
    )
    for language, words in TOPIC_KEYWORDS.items():
        for word in words:
            for term in canonical:
                if word != term and term.startswith(word):
                    assert term in words, f"{language}: {word!r} is a truncated {term!r}"


# --- minor gate -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("How do I get an abortion?", "en"),
        ("Can I get a hysterectomy?", "en"),
        ("Nataka kufunga uzazi", "sw"),
        ("Kutoa mimba ni salama?", "sw"),
        ("Tell me about IVF treatment", "en"),
        ("I want sterilization", "sheng"),
    ],
)
def test_minor_gate_flags_18_plus_topics(text: str, language: str) -> None:
    assert MinorTopicGate().is_minor_gated(text, language)


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("My period is late", "en"),
        ("Nina maumivu ya hedhi", "sw"),
        ("Is family planning safe?", "en"),
    ],
)
def test_minor_gate_passes_ordinary_topics(text: str, language: str) -> None:
    assert not MinorTopicGate().is_minor_gated(text, language)


def test_minor_gate_treats_unknown_age_as_a_minor() -> None:
    gate = MinorTopicGate()
    assert gate.applies(None)
    assert gate.applies(15)
    assert gate.applies(17)
    assert not gate.applies(18)
    assert not gate.applies(30)


def test_minor_gate_splits_procedures_from_sexual_health_questions() -> None:
    """A38: procedures are hard-gated for every minor; sexual-health questions take the
    two-step. A text matching both families belongs to the hard gate (the service checks
    the procedure branch first)."""
    gate = MinorTopicGate()
    for text in (
        "How do I get an abortion?",
        "Tell me about IVF treatment",
        "Nataka kufunga uzazi",
        "Advise me kuhusu kupasua kizazi.",
    ):
        assert gate.is_procedure_gated(text, "en"), text
        assert not gate.is_sexual_health_gated(text, "en"), text
        assert gate.is_minor_gated(text, "en"), text
    for text in (
        "Is sex painful normal?",
        "Je, ngono inaumiza, ni kawaida?",
        "Sex inaumiza ni normal?",
    ):
        assert gate.is_sexual_health_gated(text), text
        assert gate.is_minor_gated(text), text
        assert not gate.is_procedure_gated(text), text
    mixed = "Can I get an abortion after having sex?"
    assert gate.is_procedure_gated(mixed) and gate.is_sexual_health_gated(mixed)


# --- pre-LLM refusal detectors -----------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Do I have cancer?",
        "Do I have endometriosis or something else?",
        "Am I low risk?",
        "Am I at risk of cervical cancer?",
        "Je, nina saratani?",
        "Niko na cancer?",
        "Nina ugonjwa gani?",
        "What is wrong with me?",
        "Should I be screened?",
    ],
)
def test_diagnosis_ask_detector_catches_risk_questions(text: str) -> None:
    assert DiagnosisAskDetector().is_diagnosis_ask(text, "en")


@pytest.mark.parametrize(
    "text",
    [
        "What is endometriosis?",
        "I have no symptoms at all. Do I still need screening?",
        "Tell me about period pain",
        "How does a pap smear work?",
    ],
)
def test_diagnosis_ask_detector_leaves_education_questions_alone(text: str) -> None:
    assert not DiagnosisAskDetector().is_diagnosis_ask(text, "en")


@pytest.mark.parametrize(
    "text",
    [
        "What medicine should I take for the pain?",
        "Which antibiotic works for discharge?",
        "Nipe dawa ya maumivu",
        "Dawa gani ya maumivu?",
        "Can I take ibuprofen for the pain?",
        "What dose of paracetamol is safe?",
        "Nitumie vidonge gani?",
    ],
)
def test_prescription_ask_detector_catches_medicine_requests(text: str) -> None:
    assert PrescriptionAskDetector().is_prescription_ask(text, "en")


@pytest.mark.parametrize(
    "text",
    [
        "How do I manage period pain at home?",
        "What foods help with low iron?",
        "Nifanye nini kuhusu maumivu?",
    ],
)
def test_prescription_ask_detector_leaves_self_care_questions_alone(text: str) -> None:
    assert not PrescriptionAskDetector().is_prescription_ask(text, "en")


# --- post-filter -------------------------------------------------------------------


def test_post_filter_accepts_a_clean_education_answer(postfilter: PostFilter) -> None:
    verdict = postfilter.check(
        "The approved content on period pain says this is common "
        "[cervical-screening-patient-en#1].",
        band="YELLOW",
    )
    assert verdict["ok"] is True
    assert verdict["violations"] == []
    assert verdict["reason"] is None


@pytest.mark.parametrize(
    "text",
    [
        "You have endometriosis.",
        "You definitely have a hormonal imbalance. [a#1]",
        "You do not have endometriosis. [a#1]",  # negated form is still a diagnosis
        "You don't have PCOS, so relax. [a#1]",
        "Your test results show fibroids. [a#1]",
        "Una ugonjwa wa saratani. [a#1]",
    ],
)
def test_post_filter_blocks_diagnosis_claims(postfilter: PostFilter, text: str) -> None:
    verdict = postfilter.check(text, band="YELLOW")
    assert verdict["ok"] is False
    assert VIOLATION_DIAGNOSIS_CLAIM in verdict["violations"]


def test_post_filter_blocks_prescription_and_dose(postfilter: PostFilter) -> None:
    verdict = postfilter.check("You should take antibiotics twice. [a#1]", band="YELLOW")
    assert VIOLATION_PRESCRIPTION in verdict["violations"]
    dose = postfilter.check("Take 400 mg ibuprofen every 8 hours. [a#1]", band="YELLOW")
    assert VIOLATION_PRESCRIPTION in dose["violations"]
    assert VIOLATION_DRUG_DOSE in dose["violations"]
    assert dose["reason"] == VIOLATION_PRESCRIPTION  # first violation is the reason


@pytest.mark.parametrize(
    ("band", "text"),
    [
        ("YELLOW", "The band is RED. [a#1]"),
        ("GREEN", "Your result came back ORANGE. [a#1]"),
        (None, "The band is GREEN. [a#1]"),  # any band mention without an engine band
        (None, "NOT_ENOUGH_DATA [a#1]"),
    ],
)
def test_post_filter_blocks_band_mismatch(
    postfilter: PostFilter, band: str | None, text: str
) -> None:
    verdict = postfilter.check(text, band=band)
    assert verdict["ok"] is False
    assert VIOLATION_BAND_MISMATCH in verdict["violations"]


def test_post_filter_allows_the_engine_band_itself(postfilter: PostFilter) -> None:
    verdict = postfilter.check("The engine result is YELLOW. [a#1]", band="YELLOW")
    assert verdict["ok"] is True


def test_post_filter_blocks_prompt_leaks(postfilter: PostFilter) -> None:
    for text in (
        PROMPT_LEAK_MARKER + " [a#1]",
        "My system prompt says to answer in Kiswahili. [a#1]",
        "SISI_INTERNAL_SYSTEM_PROMPT_V1 [a#1]",
    ):
        verdict = postfilter.check(text, band="YELLOW")
        assert VIOLATION_PROMPT_LEAK in verdict["violations"], text


def test_post_filter_requires_a_chunk_citation(postfilter: PostFilter) -> None:
    verdict = postfilter.check("Period pain is common and it can be managed.", band="YELLOW")
    assert verdict["ok"] is False
    assert verdict["reason"] == VIOLATION_MISSING_CITATION
    ok = postfilter.check("Period pain is common. [f2h-epi#3]", band="YELLOW")
    assert ok["ok"] is True


def test_post_filter_flags_off_topic_drift(postfilter: PostFilter) -> None:
    verdict = postfilter.check(OFF_TOPIC_MARKER + " [a#1]", band="YELLOW")
    assert verdict["violations"] == [VIOLATION_OFF_TOPIC_ANSWER]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (DIAGNOSIS_MARKER + " [a#1]", [VIOLATION_DIAGNOSIS_CLAIM]),
        # a drug AND a dose is exactly what the prescription behaviour emits
        (PRESCRIPTION_MARKER + " [a#1]", [VIOLATION_PRESCRIPTION, VIOLATION_DRUG_DOSE]),
        (BAND_CONTRADICTION_MARKER.format(band="GREEN") + " [a#1]", [VIOLATION_BAND_MISMATCH]),
        (PROMPT_LEAK_MARKER + " [a#1]", [VIOLATION_PROMPT_LEAK]),
        (OFF_TOPIC_MARKER + " [a#1]", [VIOLATION_OFF_TOPIC_ANSWER]),
    ],
)
def test_post_filter_misbehaviour_markers_map_to_their_violations(
    postfilter: PostFilter, text: str, expected: list[str]
) -> None:
    verdict = postfilter.check(text, band="YELLOW")
    assert verdict["violations"] == expected
    assert verdict["reason"] == expected[0]


# --- urgent script -----------------------------------------------------------------


def test_urgent_script_embeds_both_hotlines(backend_settings) -> None:
    script = build_urgent_script([], backend_settings)
    assert backend_settings.helpline_child in script
    assert backend_settings.helpline_gbv in script
    assert "TODAY" in script


@pytest.mark.parametrize("language", ["en", "sw", "sheng"])
def test_urgent_script_has_every_language(backend_settings, language: str) -> None:
    script = build_urgent_script([], backend_settings, language=language)
    assert backend_settings.helpline_child in script
    assert backend_settings.helpline_gbv in script


def test_urgent_script_is_deterministic(backend_settings) -> None:
    first = build_urgent_script([], backend_settings)
    second = build_urgent_script([], backend_settings)
    assert first == second


def test_urgent_script_adds_safeguarding_paragraph_for_safeguarding_hits(
    backend_settings,
) -> None:
    matcher = build_matcher(backend_settings.ontology_dir)
    hits = matcher.match_text("I want to hurt myself")
    assert hits, "the ontology matcher must flag this self-harm phrasing"
    script = build_urgent_script(hits, backend_settings)
    assert "not your fault" in script
    assert backend_settings.helpline_child in script
    plain = build_urgent_script([], backend_settings)
    assert plain != script


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize(
    "routing",
    [
        ROUTING_REFUSE_DIAGNOSIS,
        ROUTING_REFUSE_PRESCRIPTION,
        ROUTING_OUT_OF_SCOPE,
        ROUTING_AGE_GATED_MINOR,
        ROUTING_REFUSED,
    ],
)
def test_refusal_texts_survive_their_own_post_filter(
    postfilter: PostFilter, language: str, routing: str
) -> None:
    """A refusal is a deterministic, pre-approved template, so it can never be
    rejected by the post-filter it is substituted into. Regression: the Kiswahili
    diagnosis refusal said "una ugonjwa", which the diagnosis-claim pattern matches —
    our own refusal would have been refused."""
    text = f"{refusal_text(routing, language)} [period-health-patient-en#1]"
    verdict = postfilter.check(text, band=None)
    assert verdict["ok"] is True, (language, routing, verdict["violations"])


def test_sw_diagnosis_refusal_never_uses_the_diagnosis_claim_phrase() -> None:
    text = refusal_text(ROUTING_REFUSE_DIAGNOSIS, "sw")
    assert "una ugonjwa" not in text
    assert "kuchunguzwa" in text  # the check-up wording is what carries the meaning
    verdict = PostFilter().check(f"{text} [period-health-patient-sw#2]", band=None)
    assert verdict["ok"] is True
    assert verdict["violations"] == []


def _two_step_texts(language: str) -> list[str]:
    """Every deterministic text the two-step can serve in one language."""
    return [
        MINOR_SEX_CHECK_TEXTS[language],
        MINOR_NO_SEX_TEXTS[language],
        MINOR_YES_NURSE_LINE[language],
        minor_no_sex_text(language),  # the composed "no" answer (guidance + referral)
    ]


@pytest.mark.parametrize("language", LANGUAGES)
def test_minor_two_step_texts_survive_their_own_post_filter(language: str) -> None:
    """The two-step texts are deterministic templates served beside the post-filter, so
    they can never be rejected by it (the same invariant as the refusal texts). The
    nurse-referral sentence is checked standalone because the "yes" branch appends it to
    a post-filtered education answer, where the harness re-checks the whole response."""
    postfilter = PostFilter()
    for text in _two_step_texts(language):
        verdict = postfilter.check(f"{text} [period-health-patient-en#1]", band=None)
        assert verdict["ok"] is True, (language, text, verdict["violations"])


@pytest.mark.parametrize("language", LANGUAGES)
def test_minor_two_step_texts_are_generic(language: str) -> None:
    """No condition name, no band, no medicine, no digits anywhere in the two-step texts
    or the prompt framing line (A38 / non-negotiable 4). The Kiswahili variant must also
    avoid "una ugonjwa" — the post-filter's own diagnosis-claim phrase (the earlier fix).
    """
    forbidden = (
        "pcos",
        "polycystic",
        "endometriosis",
        "fibroid",
        "cancer",
        "saratani",
        "kansa",
        "infection",
        "maambukizi",
        "hiv",
        "ugonjwa wa zinaa",
        "una ugonjwa",
        "medicine",
        "dawa",
        "dose",
        "mg",
        "GREEN",
        "YELLOW",
        "ORANGE",
        "RED",
    )
    for text in [*_two_step_texts(language), MINOR_SEX_FRAMING_LINE]:
        lowered = text.lower()
        for token in forbidden:
            assert token.lower() not in lowered, (language, token, text)
        assert re.search(r"\d", text) is None, (language, text)


def test_refusal_texts_exist_for_every_routing_and_language() -> None:
    for language in LANGUAGES:
        for routing in (
            ROUTING_REFUSE_DIAGNOSIS,
            ROUTING_REFUSE_PRESCRIPTION,
            ROUTING_OUT_OF_SCOPE,
            ROUTING_AGE_GATED_MINOR,
            ROUTING_REFUSED,
        ):
            text = refusal_text(routing, language)
            assert text
            # a refusal never contains a band token or the word "diagnosis" as a claim
            assert "GREEN" not in text and "YELLOW" not in text


def test_every_guardrail_vocabulary_covers_every_language() -> None:
    """A language added to the contract must not silently fall back to English."""
    assert set(LANGUAGES) == {"en", "sw", "sheng"}
    assert set(REFUSAL_TEXTS) == set(LANGUAGES)
    assert set(URGENT_SCRIPTS) == set(LANGUAGES)
    assert set(SAFEGUARDING_LINES) == set(LANGUAGES)
    assert set(TOPIC_KEYWORDS) == set(LANGUAGES)
    assert set(MINOR_SEX_CHECK_TEXTS) == set(LANGUAGES)
    assert set(MINOR_NO_SEX_TEXTS) == set(LANGUAGES)
    assert set(MINOR_YES_NURSE_LINE) == set(LANGUAGES)
    assert MINOR_SEX_FRAMING_LINE
    for language in LANGUAGES:
        assert TOPIC_KEYWORDS[language], language


def test_citations_for_keeps_only_retrieved_chunks_in_citation_order() -> None:
    hits = [_hit("a#1"), _hit("b#2"), _hit("c#3")]
    answer = "See [c#3] and [a#1]; also [not-retrieved#9]."
    cited = citations_for(answer, hits)
    assert [hit.chunk_id for hit in cited] == ["c#3", "a#1"]
