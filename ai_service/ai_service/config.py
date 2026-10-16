"""AI service settings (spec 5.2, decisions D7/D8, assumptions A33/A35/A37).

Providers default to deterministic stubs so no credential ever lives in the repo
(non-negotiable 7); staging/prod refuse to boot with stubs, with the default
internal token, or with a hosted provider that has no key — the guards mirror the
backend's `_prod_guards` pattern.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ai_service/ai_service/config.py -> ai_service/ -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_INTERNAL_TOKEN = "dev-only-ai-token-change-me"  # noqa: S105 — dev default; prod-guarded below

LLM_PROVIDERS = ("stub", "hosted", "openweight")
EMBEDDING_PROVIDERS = ("stub", "bge_m3")


class AISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_prefix="SISI_", extra="ignore"
    )

    env: str = "dev"  # dev | demo | staging | prod
    database_url: str = "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi"
    ontology_dir: Path = REPO_ROOT / "ontology"

    # LLM provider (D8/A33): stub | hosted | openweight
    ai_llm_provider: str = "stub"
    ai_hosted_api_key: str = ""
    ai_hosted_base_url: str = "https://api.anthropic.com"
    ai_hosted_model: str = ""
    ai_openweight_base_url: str = "http://localhost:8000/v1"
    ai_openweight_model: str = ""
    ai_llm_timeout_seconds: float = 30.0
    ai_max_output_tokens: int = 700
    ai_temperature: float = 0.2

    # Embeddings (A34): stub | bge_m3
    ai_embedding_provider: str = "stub"
    ai_embedding_dim: int = 768  # must match ai.chunk_embeddings (migration 0007)
    ai_embedding_model: str = "stub-fnv1a-trigram"
    ai_embedding_base_url: str = "http://localhost:8001/v1"
    ai_embedding_api_key: str = ""

    # RAG
    ai_rag_top_k: int = 4
    ai_rag_max_chunk_chars: int = 2400

    # Internal auth (A35): /v1/ai/* is an internal-only surface
    ai_internal_token: str = DEFAULT_INTERNAL_TOKEN

    # Comparison-report price sheet, USD per 1,000 tokens — PLACEHOLDERS (A37)
    ai_price_hosted_in: float = 0.0
    ai_price_hosted_out: float = 0.0
    ai_price_openweight_in: float = 0.0
    ai_price_openweight_out: float = 0.0

    @model_validator(mode="after")
    def _prod_guards(self) -> "AISettings":
        if self.env in {"staging", "prod"}:
            if self.ai_llm_provider == "stub":
                raise ValueError("SISI_AI_LLM_PROVIDER must not be 'stub' in staging/prod")
            if self.ai_embedding_provider == "stub":
                raise ValueError("SISI_AI_EMBEDDING_PROVIDER must not be 'stub' in staging/prod")
            if self.ai_internal_token in {"", DEFAULT_INTERNAL_TOKEN}:
                raise ValueError("SISI_AI_INTERNAL_TOKEN must be set in staging/prod")
            if self.ai_llm_provider == "hosted":
                if not self.ai_hosted_api_key:
                    raise ValueError("SISI_AI_HOSTED_API_KEY must be set in staging/prod")
                if not self.ai_hosted_model:
                    raise ValueError("SISI_AI_HOSTED_MODEL must be set in staging/prod")
            if self.ai_llm_provider == "openweight" and not self.ai_openweight_model:
                raise ValueError("SISI_AI_OPENWEIGHT_MODEL must be set in staging/prod")
            if self.ai_embedding_provider == "bge_m3" and not self.ai_embedding_model:
                raise ValueError("SISI_AI_EMBEDDING_MODEL must be set in staging/prod")
        return self


@lru_cache
def get_ai_settings() -> AISettings:
    return AISettings()
