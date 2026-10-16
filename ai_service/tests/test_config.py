"""AISettings: dev defaults and the staging/prod boot guards (D8, A33, A35, A37)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_service.config import DEFAULT_INTERNAL_TOKEN, AISettings

STRONG_TOKEN = "prod-internal-token-0123456789"


def test_dev_defaults_are_stub_and_safe() -> None:
    settings = AISettings()
    assert settings.env == "dev"
    assert settings.ai_llm_provider == "stub"
    assert settings.ai_embedding_provider == "stub"
    assert settings.ai_embedding_dim == 768  # must match ai.chunk_embeddings
    assert settings.ai_rag_top_k == 4
    assert settings.ai_rag_max_chunk_chars == 2400
    assert settings.ai_internal_token == DEFAULT_INTERNAL_TOKEN
    assert settings.ai_hosted_api_key == ""
    assert settings.ai_openweight_model == ""
    assert settings.ai_price_hosted_in == 0.0  # placeholders until H15 (A37)


def test_ontology_dir_is_absolute_repo_path() -> None:
    settings = AISettings()
    assert settings.ontology_dir.is_absolute()
    assert (settings.ontology_dir / "content").is_dir()
    assert Path(settings.ontology_dir).name == "ontology"


def test_env_overrides_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SISI_AI_LLM_PROVIDER", "hosted")
    monkeypatch.setenv("SISI_AI_HOSTED_MODEL", "some-model")
    monkeypatch.setenv("SISI_AI_RAG_TOP_K", "7")
    settings = AISettings()
    assert settings.ai_llm_provider == "hosted"
    assert settings.ai_hosted_model == "some-model"
    assert settings.ai_rag_top_k == 7


def test_prod_refuses_stub_llm_provider() -> None:
    with pytest.raises(ValidationError, match="SISI_AI_LLM_PROVIDER must not be 'stub'"):
        AISettings(env="prod", ai_internal_token=STRONG_TOKEN)


def test_staging_refuses_stub_embedding_provider() -> None:
    with pytest.raises(ValidationError, match="SISI_AI_EMBEDDING_PROVIDER must not be 'stub'"):
        AISettings(
            env="staging",
            ai_llm_provider="hosted",
            ai_hosted_api_key="k",
            ai_hosted_model="m",
            ai_internal_token=STRONG_TOKEN,
        )


@pytest.mark.parametrize("token", ["", DEFAULT_INTERNAL_TOKEN])
def test_prod_refuses_default_or_empty_internal_token(token: str) -> None:
    with pytest.raises(ValidationError, match="SISI_AI_INTERNAL_TOKEN must be set"):
        AISettings(
            env="prod",
            ai_llm_provider="hosted",
            ai_hosted_api_key="k",
            ai_hosted_model="m",
            ai_embedding_provider="bge_m3",
            ai_embedding_model="bge-m3",
            ai_internal_token=token,
        )


def test_prod_refuses_hosted_without_key() -> None:
    with pytest.raises(ValidationError, match="SISI_AI_HOSTED_API_KEY must be set"):
        AISettings(
            env="prod",
            ai_llm_provider="hosted",
            ai_embedding_provider="bge_m3",
            ai_embedding_model="bge-m3",
            ai_internal_token=STRONG_TOKEN,
        )


def test_prod_refuses_hosted_without_model() -> None:
    with pytest.raises(ValidationError, match="SISI_AI_HOSTED_MODEL must be set"):
        AISettings(
            env="prod",
            ai_llm_provider="hosted",
            ai_hosted_api_key="k",
            ai_embedding_provider="bge_m3",
            ai_embedding_model="bge-m3",
            ai_internal_token=STRONG_TOKEN,
        )


def test_prod_refuses_openweight_without_model() -> None:
    with pytest.raises(ValidationError, match="SISI_AI_OPENWEIGHT_MODEL must be set"):
        AISettings(
            env="prod",
            ai_llm_provider="openweight",
            ai_embedding_provider="bge_m3",
            ai_embedding_model="bge-m3",
            ai_internal_token=STRONG_TOKEN,
        )


def test_prod_accepts_a_fully_configured_provider() -> None:
    settings = AISettings(
        env="prod",
        ai_llm_provider="hosted",
        ai_hosted_api_key="k",
        ai_hosted_model="m",
        ai_embedding_provider="bge_m3",
        ai_embedding_model="bge-m3",
        ai_internal_token=STRONG_TOKEN,
    )
    assert settings.ai_llm_provider == "hosted"
    assert settings.ai_internal_token == STRONG_TOKEN


@pytest.mark.parametrize("env", ["dev", "demo"])
def test_dev_and_demo_allow_stubs(env: str) -> None:
    settings = AISettings(env=env)
    assert settings.ai_llm_provider == "stub"
    assert settings.ai_internal_token == DEFAULT_INTERNAL_TOKEN
