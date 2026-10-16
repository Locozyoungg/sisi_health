"""LLMProvider interface (spec 5.2, decisions D8/D9).

The default provider is a deterministic STUB: it produces marker text for each
misbehaviour the guardrails must catch (diagnosis claim, prescription, band
contradiction, prompt leak, off-topic drift), so the post-filter is exercised by
CI rather than by hope. Hosted (Anthropic-style) and open-weight (vLLM,
OpenAI-compatible) clients ship behind env config with contract tests; credentials
are never defaulted (non-negotiable 7).
"""

import re
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from ai_service.config import AISettings
from ai_service.errors import ProviderNotConfigured

STUB_BEHAVIORS = (
    "educational",
    "diagnosis_attempt",
    "prescription_attempt",
    "band_contradiction",
    "prompt_leak",
    "off_topic",
)

# Deterministic marker text (asserted by tests and by the eval harness). Each
# misbehaviour produces exactly ONE post-filter violation, so a harness failure
# names the misbehaviour that caused it.
DIAGNOSIS_MARKER = "STUB_MARKER_DIAGNOSIS: You definitely have endometriosis."
PRESCRIPTION_MARKER = "STUB_MARKER_PRESCRIPTION: Take 400 mg ibuprofen every 8 hours."
BAND_CONTRADICTION_MARKER = (
    "STUB_MARKER_BAND: The band is {band}, so there is nothing to worry about."
)
PROMPT_LEAK_MARKER = "STUB_MARKER_PROMPT_LEAK"
OFF_TOPIC_MARKER = "STUB_MARKER_OFF_TOPIC: Here is a recipe for chapati: mix flour with warm water."

BAND_ALTERNATIVES = ("GREEN", "YELLOW", "ORANGE", "RED")

_CHUNK_ID_RE = re.compile(r"\[([a-z0-9][a-z0-9-]*#\d+)\]")
_BAND_RE = re.compile(r"ENGINE_BAND:\s*(\S+)")
_BAND_LABEL_RE = re.compile(r"BAND_LABEL:\s*(.+)")


@dataclass(frozen=True)
class Completion:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    def complete(
        self, *, system: str, user: str, max_output_tokens: int, temperature: float
    ) -> Completion: ...


class StubProvider:
    """Deterministic stand-in for a language model (D8/A33)."""

    def __init__(
        self, behavior: str = "educational", *, latency_ms: int = 0, model: str = "stub-llm"
    ) -> None:
        if behavior not in STUB_BEHAVIORS:
            raise ValueError(
                f"unknown stub behavior {behavior!r}; expected one of {STUB_BEHAVIORS}"
            )
        if latency_ms < 0:
            raise ValueError("latency_ms must not be negative")
        self._behavior = behavior
        self._latency_ms = latency_ms
        self._model = model

    @property
    def name(self) -> str:
        return "stub"

    @property
    def model(self) -> str:
        return self._model

    @property
    def behavior(self) -> str:
        return self._behavior

    def complete(
        self, *, system: str, user: str, max_output_tokens: int, temperature: float
    ) -> Completion:
        if self._latency_ms:
            time.sleep(self._latency_ms / 1000.0)
        text = self._text(system)
        return Completion(
            text=text,
            provider=self.name,
            model=self._model,
            # Deterministic token accounting so latency/token aggregates are stable.
            input_tokens=len(system.split()),
            output_tokens=len(text.split()),
        )

    def _text(self, system: str) -> str:
        if self._behavior == "educational":
            return self._educational(system)
        if self._behavior == "prompt_leak":
            return f"{PROMPT_LEAK_MARKER}\n{system}"
        if self._behavior == "diagnosis_attempt":
            marker = DIAGNOSIS_MARKER
        elif self._behavior == "prescription_attempt":
            marker = PRESCRIPTION_MARKER
        elif self._behavior == "band_contradiction":
            marker = BAND_CONTRADICTION_MARKER.format(band=self._contradicting_band(system))
        else:
            marker = OFF_TOPIC_MARKER
        return f"{marker}{self._cite(system)}"

    @staticmethod
    def _cite(system: str) -> str:
        """Cite the first retrieved chunk, so a misbehaviour violates exactly ONE
        post-filter rule and the reason names it."""
        cited = _CHUNK_ID_RE.findall(system)
        return f" [{cited[0]}]" if cited else ""

    def _educational(self, system: str) -> str:
        """Cite the chunk ids present in the system prompt and echo the engine band
        label — the two properties every education answer must have."""
        cited = _CHUNK_ID_RE.findall(system)
        band_match = _BAND_RE.search(system)
        label_match = _BAND_LABEL_RE.search(system)
        band = band_match.group(1) if band_match else "UNKNOWN"
        label = label_match.group(1).strip() if label_match else "unknown"
        citations = ", ".join(f"[{chunk_id}]" for chunk_id in cited) or "[no-chunk]"
        return (
            f"SISI education (stub). The result from the SISI check is {band} ({label}); "
            "this is not a diagnosis. Here is the approved guidance for what you asked: "
            "talk to the school nurse or a health worker about what you notice. "
            f"Sources: {citations}."
        )

    @staticmethod
    def _contradicting_band(system: str) -> str:
        match = _BAND_RE.search(system)
        current = match.group(1) if match else ""
        for band in BAND_ALTERNATIVES:
            if band != current:
                return band
        return "RED"


class RecordingLLMProvider:
    """Test/eval wrapper: counts calls and records the exact prompts sent, so
    "the LLM was never called" and "no identifiers reached the prompt" are
    assertable properties rather than assumptions."""

    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner
        self.calls: list[tuple[str, str]] = []

    @property
    def inner(self) -> LLMProvider:
        return self._inner

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def model(self) -> str:
        return self._inner.model

    @property
    def count(self) -> int:
        return len(self.calls)

    @property
    def system_prompts(self) -> list[str]:
        return [system for system, _user in self.calls]

    def complete(
        self, *, system: str, user: str, max_output_tokens: int, temperature: float
    ) -> Completion:
        self.calls.append((system, user))
        return self._inner.complete(
            system=system, user=user, max_output_tokens=max_output_tokens, temperature=temperature
        )


class HostedProvider:
    """Hosted LLM behind an Anthropic-style `POST {base}/v1/messages` contract."""

    def __init__(
        self, settings: AISettings, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._settings = settings
        self._transport = transport

    @property
    def name(self) -> str:
        return "hosted"

    @property
    def model(self) -> str:
        return self._settings.ai_hosted_model

    def _require_config(self) -> tuple[str, str, str]:
        base_url = self._settings.ai_hosted_base_url.rstrip("/")
        api_key = self._settings.ai_hosted_api_key
        model = self._settings.ai_hosted_model
        if not api_key or not model:
            raise ProviderNotConfigured(
                "provider 'hosted' requires SISI_AI_HOSTED_API_KEY and SISI_AI_HOSTED_MODEL; "
                "no hosted key is configured on this host (H15)"
            )
        return base_url, api_key, model

    def complete(
        self, *, system: str, user: str, max_output_tokens: int, temperature: float
    ) -> Completion:
        base_url, api_key, model = self._require_config()
        payload = {
            "model": model,
            "max_tokens": max_output_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        with httpx.Client(
            timeout=self._settings.ai_llm_timeout_seconds, transport=self._transport
        ) as client:
            response = client.post(f"{base_url}/v1/messages", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        blocks = data.get("content", [])
        text = "".join(
            block.get("text", "") for block in blocks if block.get("type") == "text"
        )
        usage = data.get("usage", {})
        return Completion(
            text=text,
            provider=self.name,
            model=str(data.get("model", model)),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
        )


class OpenWeightProvider:
    """Self-hosted open-weight model behind a vLLM (OpenAI-compatible)
    `POST {base}/chat/completions` contract; serving the GPU host is H15."""

    def __init__(
        self, settings: AISettings, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._settings = settings
        self._transport = transport

    @property
    def name(self) -> str:
        return "openweight"

    @property
    def model(self) -> str:
        return self._settings.ai_openweight_model

    def _require_config(self) -> tuple[str, str]:
        base_url = self._settings.ai_openweight_base_url.rstrip("/")
        model = self._settings.ai_openweight_model
        if not base_url or not model:
            raise ProviderNotConfigured(
                "provider 'openweight' requires SISI_AI_OPENWEIGHT_BASE_URL and "
                "SISI_AI_OPENWEIGHT_MODEL; no vLLM host is configured on this machine (H15)"
            )
        return base_url, model

    def complete(
        self, *, system: str, user: str, max_output_tokens: int, temperature: float
    ) -> Completion:
        base_url, model = self._require_config()
        payload = {
            "model": model,
            "max_tokens": max_output_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        with httpx.Client(
            timeout=self._settings.ai_llm_timeout_seconds, transport=self._transport
        ) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers={"content-type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        choices = data.get("choices", [])
        text = choices[0].get("message", {}).get("content", "") if choices else ""
        usage = data.get("usage", {})
        return Completion(
            text=text,
            provider=self.name,
            model=str(data.get("model", model)),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
        )


def build_llm_provider(
    settings: AISettings, *, transport: httpx.BaseTransport | None = None
) -> LLMProvider:
    """Provider factory; an unknown name is a configuration error, not a fallback."""
    provider = settings.ai_llm_provider
    if provider == "stub":
        return StubProvider()
    if provider == "hosted":
        return HostedProvider(settings, transport=transport)
    if provider == "openweight":
        return OpenWeightProvider(settings, transport=transport)
    raise ProviderNotConfigured(
        f"unknown SISI_AI_LLM_PROVIDER {provider!r}; expected one of 'stub', 'hosted', 'openweight'"
    )
