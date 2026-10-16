"""Conversation pipeline (spec 5.2): the ORDER of the steps is the safety property.
Every pre-LLM routing is proved with a recording provider — "the model was never
called" is an assertion, not a hope — and every post-LLM failure is proved to
return a deterministic refusal instead of the model's text (HZ-07)."""

import re

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from ai_service.config import AISettings
from ai_service.errors import ProviderNotConfigured
from ai_service.guardrails import (
    ROUTING_AGE_GATED_MINOR,
    ROUTING_EDUCATION,
    ROUTING_OUT_OF_SCOPE,
    ROUTING_REFUSE_DIAGNOSIS,
    ROUTING_REFUSE_PRESCRIPTION,
    ROUTING_REFUSED,
    ROUTING_URGENT_SCRIPT,
    VIOLATION_BAND_MISMATCH,
    VIOLATION_DIAGNOSIS_CLAIM,
    VIOLATION_OFF_TOPIC_ANSWER,
    VIOLATION_PROMPT_LEAK,
    refusal_text,
)
from ai_service.providers.llm import (
    DIAGNOSIS_MARKER,
    OFF_TOPIC_MARKER,
    PRESCRIPTION_MARKER,
    PROMPT_LEAK_MARKER,
    HostedProvider,
    RecordingLLMProvider,
    StubProvider,
)
from ai_service.rag import EmbeddingStore, index_content
from ai_service.service import AskRequest, ConversationService


def _service(**kwargs) -> ConversationService:
    return ConversationService(**kwargs)


# --- 1. red flags come first -------------------------------------------------------


@pytest.mark.parametrize(
    ("text_value", "language"),
    [
        ("I have sudden severe pain in my lower belly", "en"),
        ("Nina damu nyingi na naskia kizunguzungu", "sw"),
        ("bleed nyingi na naskia dizzy", "sheng"),
        ("I want to hurt myself", "en"),
    ],
)
def test_red_flag_routes_to_the_urgent_script_without_an_llm_call(
    service: ConversationService,
    llm: RecordingLLMProvider,
    backend_settings,
    text_value: str,
    language: str,
) -> None:
    response = service.ask(AskRequest(text=text_value, language=language, band="RED"))
    assert response.routing == ROUTING_URGENT_SCRIPT
    assert llm.count == 0  # the model is never in the red-flag loop
    assert backend_settings.helpline_child in response.text
    assert backend_settings.helpline_gbv in response.text
    assert response.input_tokens == 0 and response.output_tokens == 0
    assert response.citations == []


def test_engine_urgent_and_safeguarding_flags_force_the_urgent_script(
    service: ConversationService, llm: RecordingLLMProvider, backend_settings
) -> None:
    urgent = service.ask(
        AskRequest(text="Nina maumivu ya hedhi", language="sw", band="RED", urgent=True)
    )
    assert urgent.routing == ROUTING_URGENT_SCRIPT
    safeguarding = service.ask(
        AskRequest(text="Nina maumivu ya hedhi", language="sw", safeguarding=True)
    )
    assert safeguarding.routing == ROUTING_URGENT_SCRIPT
    assert "si kosa lako" in safeguarding.text  # safeguarding paragraph, in language
    assert llm.count == 0


# --- 2. deterministic refusals before the model ------------------------------------


@pytest.mark.parametrize(
    ("text_value", "language"),
    [
        ("What medicine should I take for the pain?", "en"),
        ("Nipe dawa ya maumivu", "sw"),
        ("Nitumie vidonge gani?", "sw"),
    ],
)
def test_prescription_asks_are_refused_before_the_llm(
    service: ConversationService, llm: RecordingLLMProvider, text_value: str, language: str
) -> None:
    response = service.ask(AskRequest(text=text_value, language=language, band="YELLOW"))
    assert response.routing == ROUTING_REFUSE_PRESCRIPTION
    assert llm.count == 0
    assert response.text == refusal_text(ROUTING_REFUSE_PRESCRIPTION, language)


@pytest.mark.parametrize(
    ("text_value", "language"),
    [
        ("Do I have cancer?", "en"),
        ("Am I low risk?", "en"),
        ("Je, nina saratani?", "sw"),
        ("Niko na cancer?", "sheng"),
    ],
)
def test_diagnosis_and_risk_questions_are_refused_before_the_llm(
    service: ConversationService, llm: RecordingLLMProvider, text_value: str, language: str
) -> None:
    response = service.ask(AskRequest(text=text_value, language=language, band="YELLOW"))
    assert response.routing == ROUTING_REFUSE_DIAGNOSIS
    assert llm.count == 0
    assert response.band == "YELLOW"  # the engine's band is echoed, never reassigned


def test_out_of_scope_questions_are_refused_before_the_llm(
    service: ConversationService, llm: RecordingLLMProvider
) -> None:
    response = service.ask(AskRequest(text="How do I cook chapati?", band="YELLOW"))
    assert response.routing == ROUTING_OUT_OF_SCOPE
    assert llm.count == 0


# --- 4. minor gate -----------------------------------------------------------------


def test_minor_gate_refuses_adult_topics_for_minors(
    service: ConversationService, llm: RecordingLLMProvider
) -> None:
    for age in (None, 15, 17):
        response = service.ask(
            AskRequest(text="How do I get an abortion?", age=age, band="YELLOW")
        )
        assert response.routing == ROUTING_AGE_GATED_MINOR, age
    assert llm.count == 0


def test_minor_gate_lets_adults_through(
    service: ConversationService, llm: RecordingLLMProvider
) -> None:
    response = service.ask(AskRequest(text="How do I get an abortion?", age=30, band="YELLOW"))
    assert response.routing != ROUTING_AGE_GATED_MINOR
    assert llm.count == 1  # an adult asking an in-scope question reaches the model


# --- 5. retrieval ------------------------------------------------------------------


def test_no_retrieved_content_refuses(
    settings: AISettings,
    backend_settings,
    matcher,
    store: EmbeddingStore,
    embedder,
    llm: RecordingLLMProvider,
    db: Session,
) -> None:
    db.execute(text("DELETE FROM ai.chunk_embeddings"))
    db.execute(text("DELETE FROM ai.content_chunks"))
    db.commit()
    service = _service(
        settings=settings,
        backend_settings=backend_settings,
        matcher=matcher,
        store=store,
        embedder=embedder,
        llm=llm,
    )
    response = service.ask(AskRequest(text="Nina maumivu ya hedhi", language="sw", band="YELLOW"))
    assert response.routing == ROUTING_REFUSED
    assert llm.count == 0  # no grounded content, no model call
    assert response.postfilter_reason is None


# --- 9. education ------------------------------------------------------------------


def test_education_answer_carries_citations_from_the_store(
    service: ConversationService, llm: RecordingLLMProvider, db: Session
) -> None:
    response = service.ask(
        AskRequest(text="Nina maumivu ya hedhi kila mwezi", language="sw", band="YELLOW")
    )
    assert response.routing == ROUTING_EDUCATION
    assert llm.count == 1
    assert response.citations, "every education answer must cite retrieved chunk ids"
    indexed = {
        str(row[0]) for row in db.execute(text("SELECT chunk_id FROM ai.content_chunks"))
    }
    for citation in response.citations:
        assert citation.chunk_id in indexed, "a citation must be a retrieved chunk"
        assert citation.chunk_id in response.text
        assert citation.title and citation.language
    assert response.input_tokens > 0 and response.output_tokens > 0
    assert response.latency_ms >= 0


def test_education_without_an_engine_band(service: ConversationService) -> None:
    # no engine band supplied: the model must not mention any band, and the stub
    # echoes NOT_SUPPLIED, which is not a band
    response = service.ask(AskRequest(text="Tell me about period pain", band=None))
    assert response.routing == ROUTING_EDUCATION
    assert response.band is None


def test_education_in_sheng_falls_back_to_the_english_library(service: ConversationService) -> None:
    response = service.ask(
        AskRequest(text="Niko na period pain, nifanye nini?", language="sheng", band="GREEN")
    )
    assert response.routing == ROUTING_EDUCATION
    assert response.citations
    assert all(citation.language == "en" for citation in response.citations)


# --- 6. the prompt carries engine values and chunk ids, never identifiers ----------


def test_prompt_carries_no_identifiers_and_only_engine_context(
    service: ConversationService, llm: RecordingLLMProvider
) -> None:
    # the /ask contract itself has no identifier field to carry (A36)
    assert {"id", "user_id", "phone", "phone_number", "name", "email", "national_id"} & set(
        AskRequest.model_fields
    ) == set()

    response = service.ask(
        AskRequest(
            text="Nina maumivu ya hedhi. Namba yangu ni +254712345678, email amina@example.com",
            language="sw",
            band="YELLOW",
            indicators=["endo-indicator"],
        )
    )
    assert response.routing == ROUTING_EDUCATION
    assert llm.count == 1
    system_prompt, user_message = llm.calls[0]
    assert re.search(r"\d{9,}", system_prompt) is None
    assert re.search(r"\d{9,}", user_message) is None
    assert "254712345678" not in user_message
    assert "amina@example.com" not in user_message
    assert "[number]" in user_message and "[email]" in user_message
    assert "ENGINE_BAND: YELLOW" in system_prompt
    assert "INDICATORS: endo-indicator" in system_prompt
    assert re.search(r"\[[a-z0-9-]+-sw#\d+\]", system_prompt)  # retrieved chunks are in the prompt
    assert "phone" not in system_prompt.lower()


# --- 8. the post-filter is the backstop -------------------------------------------


@pytest.mark.parametrize(
    ("behavior", "marker", "expected_reason"),
    [
        ("diagnosis_attempt", DIAGNOSIS_MARKER, VIOLATION_DIAGNOSIS_CLAIM),
        ("prescription_attempt", PRESCRIPTION_MARKER, "prescription"),
        ("band_contradiction", "STUB_MARKER_BAND", VIOLATION_BAND_MISMATCH),
        ("prompt_leak", PROMPT_LEAK_MARKER, VIOLATION_PROMPT_LEAK),
        ("off_topic", OFF_TOPIC_MARKER, VIOLATION_OFF_TOPIC_ANSWER),
    ],
)
def test_postfilter_refusals_never_return_model_text(
    settings: AISettings,
    backend_settings,
    matcher,
    seeded_store: EmbeddingStore,
    embedder,
    behavior: str,
    marker: str,
    expected_reason: str,
) -> None:
    recording = RecordingLLMProvider(StubProvider(behavior))
    service = _service(
        settings=settings,
        backend_settings=backend_settings,
        matcher=matcher,
        store=seeded_store,
        embedder=embedder,
        llm=recording,
    )
    response = service.ask(AskRequest(text="Tell me about period pain", band="YELLOW"))
    assert response.routing == ROUTING_REFUSED
    assert response.postfilter_reason == expected_reason
    assert marker not in response.text  # the model's text never reaches the user
    assert response.text == refusal_text(ROUTING_REFUSED, "en")
    assert response.citations == []
    assert recording.count == 1


def test_band_contradiction_is_caught_even_without_an_engine_band(
    settings: AISettings, backend_settings, matcher, seeded_store, embedder
) -> None:
    recording = RecordingLLMProvider(StubProvider("band_contradiction"))
    service = _service(
        settings=settings,
        backend_settings=backend_settings,
        matcher=matcher,
        store=seeded_store,
        embedder=embedder,
        llm=recording,
    )
    response = service.ask(AskRequest(text="Tell me about period pain", band=None))
    assert response.routing == ROUTING_REFUSED
    assert response.postfilter_reason == VIOLATION_BAND_MISMATCH


# --- provider failure surfaces as an error, never as an answer ---------------------


def test_unconfigured_provider_raises_instead_of_answering(
    settings: AISettings, backend_settings, matcher, seeded_store, embedder
) -> None:
    hosted = HostedProvider(AISettings())  # no key, no model
    service = _service(
        settings=settings,
        backend_settings=backend_settings,
        matcher=matcher,
        store=seeded_store,
        embedder=embedder,
        llm=hosted,
    )
    with pytest.raises(ProviderNotConfigured):
        service.ask(AskRequest(text="Tell me about period pain", band="YELLOW"))


def test_short_circuit_paths_keep_the_provider_identity(service: ConversationService) -> None:
    response = service.ask(AskRequest(text="Do I have cancer?", band="YELLOW"))
    assert response.provider == "stub"
    assert response.model  # the identity of the configured provider, unused


def test_index_content_helper_is_used_by_the_service_fixture(
    store: EmbeddingStore, embedder, settings: AISettings, backend_settings, matcher, llm
) -> None:
    """Guard rail on the fixture itself: the seeded store is rebuilt from /ontology."""
    count = index_content(store, embedder, settings.ontology_dir, embedder.model, embedder.dim)
    assert count > 0
    service = _service(
        settings=settings,
        backend_settings=backend_settings,
        matcher=matcher,
        store=store,
        embedder=embedder,
        llm=llm,
    )
    assert service.store is store
