"""Embedding providers (A34): the stub is deterministic and L2-normalized but
deliberately non-semantic; bge-m3 (H15) is contract-tested against its
OpenAI-compatible request shape."""

import json
import math

import httpx
import pytest

from ai_service.config import AISettings
from ai_service.errors import ProviderNotConfigured
from ai_service.providers.embeddings import (
    BgeM3Provider,
    StubEmbeddingProvider,
    build_embedding_provider,
    feature_hashes,
    fnv1a_64,
)


def test_fnv1a_64_is_stable_and_distinct() -> None:
    assert fnv1a_64(b"hedhi") == fnv1a_64(b"hedhi")
    assert fnv1a_64(b"hedhi") != fnv1a_64(b"damu")
    assert fnv1a_64(b"") == 0xCBF29CE484222325  # offset basis


def test_feature_hashes_trigrams_and_short_text_fallbacks() -> None:
    assert feature_hashes("period pain today") == ["period\x1fpain\x1ftoday"]
    assert feature_hashes("period pain") == ["period\x1fpain"]
    assert feature_hashes("hedhi") == ["hedhi"]
    assert feature_hashes("") == []


def test_stub_embedding_is_deterministic_and_normalized() -> None:
    provider = StubEmbeddingProvider(dim=768)
    first = provider.embed(["Nina maumivu ya hedhi"])[0]
    second = provider.embed(["Nina maumivu ya hedhi"])[0]
    assert first == second
    assert len(first) == 768
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0, rel_tol=1e-9)
    other = provider.embed(["How do I cook chapati?"])[0]
    assert other != first


def test_stub_embedding_of_empty_text_is_a_safe_zero_vector() -> None:
    vector = StubEmbeddingProvider(dim=8).embed([""])[0]
    assert vector == [0.0] * 8
    assert not any(math.isnan(value) for value in vector)


def test_stub_embedding_dim_and_model_are_configurable() -> None:
    provider = StubEmbeddingProvider(dim=16, model="stub-test")
    assert provider.dim == 16
    assert provider.model == "stub-test"
    assert len(provider.embed(["damu"])[0]) == 16
    with pytest.raises(ValueError, match="dim must be positive"):
        StubEmbeddingProvider(dim=0)


def test_bge_m3_request_shape_and_ordering() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ],
                "model": "bge-m3",
            },
        )

    settings = AISettings(
        ai_embedding_provider="bge_m3",
        ai_embedding_base_url="http://embed.example.test:8001/v1/",
        ai_embedding_model="bge-m3",
        ai_embedding_api_key="embed-key-not-real",
        ai_embedding_dim=2,
    )
    provider = BgeM3Provider(settings, transport=httpx.MockTransport(handler))
    vectors = provider.embed(["kwanza", "pili"])

    assert seen["url"] == "http://embed.example.test:8001/v1/embeddings"
    headers = seen["headers"]  # type: ignore[assignment]
    assert headers["authorization"] == "Bearer embed-key-not-real"
    body = seen["body"]  # type: ignore[assignment]
    assert body == {"model": "bge-m3", "input": ["kwanza", "pili"]}
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]  # re-ordered by `index`
    assert provider.name == "bge_m3"
    assert provider.dim == 2


def test_bge_m3_requires_model_and_base_url() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []}))
    without_model = BgeM3Provider(AISettings(ai_embedding_model=""), transport=transport)
    with pytest.raises(ProviderNotConfigured, match="SISI_AI_EMBEDDING_BASE_URL"):
        without_model.embed(["damu"])


def test_bge_m3_rejects_a_mismatched_vector_count() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})
    )
    settings = AISettings(ai_embedding_model="bge-m3", ai_embedding_dim=1)
    provider = BgeM3Provider(settings, transport=transport)
    with pytest.raises(ProviderNotConfigured, match="returned 1 vectors for 2 inputs"):
        provider.embed(["damu", "maumivu"])


def test_build_embedding_provider_selects_and_refuses_unknown() -> None:
    assert isinstance(build_embedding_provider(AISettings()), StubEmbeddingProvider)
    bge = build_embedding_provider(AISettings(ai_embedding_provider="bge_m3"))
    assert isinstance(bge, BgeM3Provider)
    with pytest.raises(ProviderNotConfigured, match="unknown SISI_AI_EMBEDDING_PROVIDER"):
        build_embedding_provider(AISettings(ai_embedding_provider="openai"))
