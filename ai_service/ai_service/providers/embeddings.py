"""EmbeddingProvider interface (D3/D5, assumption A34).

The default provider is a deterministic, deliberately NON-SEMANTIC stub: FNV-1a
feature hashing over word trigrams, L2-normalized. It exercises the whole
chunk -> index -> search -> cite pipeline in CI without a model server; the real
multilingual model (bge-m3, 768-d) is served behind `bge_m3` and is human task H15.
"""

import math
import re
from collections.abc import Sequence
from typing import Protocol

import httpx

from ai_service.config import AISettings
from ai_service.errors import ProviderNotConfigured

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_FEATURE_SEP = "\x1f"

_FNV_OFFSET_64 = 0xCBF29CE484222325
_FNV_PRIME_64 = 0x100000001B3
_FNV_MASK_64 = 0xFFFFFFFFFFFFFFFF


def fnv1a_64(data: bytes) -> int:
    """64-bit FNV-1a hash (deterministic across processes and platforms)."""
    digest = _FNV_OFFSET_64
    for byte in data:
        digest ^= byte
        digest = (digest * _FNV_PRIME_64) & _FNV_MASK_64
    return digest


def feature_hashes(text: str) -> list[str]:
    """Word trigrams of `text`; short texts fall back to bigrams/unigrams so short
    questions still produce a usable (still non-semantic) vector."""
    words = _WORD_RE.findall(text.lower())
    if len(words) >= 3:
        windows = [words[i : i + 3] for i in range(len(words) - 2)]
    elif len(words) == 2:
        windows = [words]
    else:
        windows = [[word] for word in words]
    return [_FEATURE_SEP.join(window) for window in windows]


class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class StubEmbeddingProvider:
    """Deterministic feature-hash embeddings (A34). Non-semantic by design."""

    def __init__(self, *, dim: int = 768, model: str = "stub-fnv1a-trigram") -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self._dim = dim
        self._model = model

    @property
    def name(self) -> str:
        return "stub"

    @property
    def model(self) -> str:
        return self._model

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        for feature in feature_hashes(text):
            digest = fnv1a_64(feature.encode("utf-8"))
            index = digest % self._dim
            sign = 1.0 if (digest >> 63) & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector  # empty/degenerate text: zero vector, cosine 0 (never NaN)
        return [value / norm for value in vector]


class BgeM3Provider:
    """Self-hosted multilingual embedding server (OpenAI-compatible
    `POST {base}/embeddings`); the deployment itself is human task H15."""

    def __init__(
        self, settings: AISettings, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._settings = settings
        self._transport = transport

    @property
    def name(self) -> str:
        return "bge_m3"

    @property
    def model(self) -> str:
        return self._settings.ai_embedding_model

    @property
    def dim(self) -> int:
        return self._settings.ai_embedding_dim

    def _require_config(self) -> tuple[str, str]:
        base_url = self._settings.ai_embedding_base_url.rstrip("/")
        model = self._settings.ai_embedding_model
        if not base_url or not model:
            raise ProviderNotConfigured(
                "embedding provider 'bge_m3' requires SISI_AI_EMBEDDING_BASE_URL and "
                "SISI_AI_EMBEDDING_MODEL; no model server is configured on this host (H15)"
            )
        return base_url, model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        base_url, model = self._require_config()
        headers = {"content-type": "application/json"}
        if self._settings.ai_embedding_api_key:
            headers["authorization"] = f"Bearer {self._settings.ai_embedding_api_key}"
        with httpx.Client(
            timeout=self._settings.ai_llm_timeout_seconds, transport=self._transport
        ) as client:
            response = client.post(
                f"{base_url}/embeddings",
                headers=headers,
                json={"model": model, "input": list(texts)},
            )
            response.raise_for_status()
            payload = response.json()
        entries = payload.get("data", [])
        if len(entries) != len(texts):
            raise ProviderNotConfigured(
                "embedding server returned "
                f"{len(entries)} vectors for {len(texts)} inputs (H15)"
            )
        ordered = sorted(entries, key=lambda entry: entry.get("index", 0))
        return [[float(value) for value in entry["embedding"]] for entry in ordered]


def build_embedding_provider(
    settings: AISettings, *, transport: httpx.BaseTransport | None = None
) -> EmbeddingProvider:
    """Provider factory; an unknown name is a configuration error, not a fallback."""
    provider = settings.ai_embedding_provider
    if provider == "stub":
        return StubEmbeddingProvider(
            dim=settings.ai_embedding_dim, model=settings.ai_embedding_model
        )
    if provider == "bge_m3":
        return BgeM3Provider(settings, transport=transport)
    raise ProviderNotConfigured(
        f"unknown SISI_AI_EMBEDDING_PROVIDER {provider!r}; expected one of "
        "'stub', 'bge_m3'"
    )
