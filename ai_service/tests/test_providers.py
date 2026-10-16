"""LLM providers (D8): stub behaviours, the recording wrapper, and the exact
request shape of the hosted and open-weight clients (contract-tested with
httpx.MockTransport — no network, no credentials)."""

import json

import httpx
import pytest

from ai_service.config import AISettings
from ai_service.errors import ProviderNotConfigured
from ai_service.providers.llm import (
    BAND_CONTRADICTION_MARKER,
    DIAGNOSIS_MARKER,
    OFF_TOPIC_MARKER,
    PRESCRIPTION_MARKER,
    PROMPT_LEAK_MARKER,
    Completion,
    HostedProvider,
    OpenWeightProvider,
    RecordingLLMProvider,
    StubProvider,
    build_llm_provider,
)

SYSTEM = (
    "SISI_INTERNAL_SYSTEM_PROMPT_V1\nENGINE_BAND: YELLOW\nBAND_LABEL: see a nurse\n"
    "CONTENT CHUNKS:\n[cervical-screening-patient-en#1] Screening\nSome text.\n"
    "[endometriosis-en#2] Endometriosis\nMore text.\n"
)


def _complete(provider: object, system: str = SYSTEM) -> Completion:
    return provider.complete(  # type: ignore[attr-defined]
        system=system, user="Nina maumivu ya hedhi", max_output_tokens=64, temperature=0.2
    )


def test_stub_educational_cites_chunks_and_echoes_band() -> None:
    completion = _complete(StubProvider())
    assert "cervical-screening-patient-en#1" in completion.text
    assert "endometriosis-en#2" in completion.text
    assert "YELLOW" in completion.text
    assert "see a nurse" in completion.text
    assert completion.provider == "stub"
    assert completion.input_tokens > 0
    assert completion.output_tokens > 0


@pytest.mark.parametrize(
    ("behavior", "marker"),
    [
        ("diagnosis_attempt", DIAGNOSIS_MARKER),
        ("prescription_attempt", PRESCRIPTION_MARKER),
        ("prompt_leak", PROMPT_LEAK_MARKER),
        ("off_topic", OFF_TOPIC_MARKER),
    ],
)
def test_stub_misbehaviours_emit_deterministic_markers(behavior: str, marker: str) -> None:
    text = _complete(StubProvider(behavior)).text
    assert text.startswith(marker) or marker in text
    # misbehaviours still cite a retrieved chunk, so exactly ONE post-filter rule fires
    assert "cervical-screening-patient-en#1" in text


def test_stub_band_contradiction_picks_a_different_band() -> None:
    text = _complete(StubProvider("band_contradiction")).text
    assert "STUB_MARKER_BAND" in text
    assert "GREEN" in text  # engine band in SYSTEM is YELLOW
    assert BAND_CONTRADICTION_MARKER.format(band="GREEN") in text


def test_stub_prompt_leak_returns_the_system_prompt() -> None:
    text = _complete(StubProvider("prompt_leak")).text
    assert "SISI_INTERNAL_SYSTEM_PROMPT_V1" in text


def test_stub_rejects_unknown_behavior_and_negative_latency() -> None:
    with pytest.raises(ValueError, match="unknown stub behavior"):
        StubProvider("diagnose")
    with pytest.raises(ValueError, match="latency_ms"):
        StubProvider(latency_ms=-1)


def test_recording_wrapper_counts_and_records_prompts() -> None:
    recording = RecordingLLMProvider(StubProvider())
    assert recording.count == 0
    _complete(recording, system=SYSTEM)
    _complete(recording, system=SYSTEM)
    assert recording.count == 2
    assert recording.calls[0][0] == SYSTEM
    assert recording.calls[0][1] == "Nina maumivu ya hedhi"
    assert recording.system_prompts[1] == SYSTEM
    assert recording.name == "stub"


def test_hosted_provider_request_shape() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "claude-test-1",
                "content": [{"type": "text", "text": "Jibu la elimu [a#1]"}],
                "usage": {"input_tokens": 120, "output_tokens": 8},
            },
        )

    settings = AISettings(
        ai_llm_provider="hosted",
        ai_hosted_api_key="test-key-not-real",
        ai_hosted_base_url="https://llm.example.test",
        ai_hosted_model="claude-test-1",
    )
    provider = HostedProvider(settings, transport=httpx.MockTransport(handler))
    completion = _complete(provider)

    assert seen["url"] == "https://llm.example.test/v1/messages"
    headers = seen["headers"]  # type: ignore[assignment]
    assert headers["x-api-key"] == "test-key-not-real"
    assert headers["anthropic-version"] == "2023-06-01"
    body = seen["body"]  # type: ignore[assignment]
    assert body["model"] == "claude-test-1"
    assert body["max_tokens"] == 64
    assert body["temperature"] == 0.2
    assert body["system"] == SYSTEM
    assert body["messages"] == [{"role": "user", "content": "Nina maumivu ya hedhi"}]
    assert completion.text == "Jibu la elimu [a#1]"
    assert completion.input_tokens == 120
    assert completion.output_tokens == 8
    assert completion.provider == "hosted"


def test_hosted_provider_requires_key_and_model() -> None:
    without_key = HostedProvider(AISettings(ai_hosted_model="m"))
    with pytest.raises(ProviderNotConfigured, match="SISI_AI_HOSTED_API_KEY"):
        _complete(without_key)
    without_model = HostedProvider(AISettings(ai_hosted_api_key="k"))
    with pytest.raises(ProviderNotConfigured, match="SISI_AI_HOSTED_MODEL"):
        _complete(without_model)


def test_hosted_provider_propagates_http_errors() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500, json={}))
    settings = AISettings(
        ai_hosted_api_key="k", ai_hosted_base_url="https://llm.example.test", ai_hosted_model="m"
    )
    with pytest.raises(httpx.HTTPStatusError):
        _complete(HostedProvider(settings, transport=transport))


def test_openweight_provider_request_shape() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "llama-3-8b-instruct",
                "choices": [{"message": {"role": "assistant", "content": "Elimu [a#1]"}}],
                "usage": {"prompt_tokens": 90, "completion_tokens": 12},
            },
        )

    settings = AISettings(
        ai_llm_provider="openweight",
        ai_openweight_base_url="http://vllm.example.test:8000/v1",
        ai_openweight_model="llama-3-8b-instruct",
    )
    provider = OpenWeightProvider(settings, transport=httpx.MockTransport(handler))
    completion = _complete(provider)

    assert seen["url"] == "http://vllm.example.test:8000/v1/chat/completions"
    body = seen["body"]  # type: ignore[assignment]
    assert body["model"] == "llama-3-8b-instruct"
    assert body["messages"][0] == {"role": "system", "content": SYSTEM}
    assert body["messages"][1]["role"] == "user"
    assert completion.text == "Elimu [a#1]"
    assert completion.input_tokens == 90
    assert completion.output_tokens == 12
    assert completion.provider == "openweight"


def test_openweight_provider_requires_model() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    with pytest.raises(ProviderNotConfigured, match="SISI_AI_OPENWEIGHT_MODEL"):
        _complete(OpenWeightProvider(AISettings(), transport=transport))


def test_build_llm_provider_selects_and_refuses_unknown() -> None:
    assert isinstance(build_llm_provider(AISettings()), StubProvider)
    hosted = build_llm_provider(AISettings(ai_llm_provider="hosted"))
    assert isinstance(hosted, HostedProvider)
    openweight = build_llm_provider(AISettings(ai_llm_provider="openweight"))
    assert isinstance(openweight, OpenWeightProvider)
    with pytest.raises(ProviderNotConfigured, match="unknown SISI_AI_LLM_PROVIDER"):
        build_llm_provider(AISettings(ai_llm_provider="gpt-like-thing"))
