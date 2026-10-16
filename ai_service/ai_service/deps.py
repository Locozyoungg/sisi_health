"""Dependency wiring for the AI service: the conversation service, the store, the
providers, the matcher and the (real) rules engine used by /v1/ai/rules/evaluate.
Everything is built once per process and overridable in tests."""

from functools import lru_cache

from app.config import Settings as BackendSettings
from app.config import get_settings as get_backend_settings
from app.rules.engine import RuleEngine
from app.rules.loader import build_engine, build_matcher
from app.rules.redflags import RedFlagMatcher

from ai_service.config import AISettings, get_ai_settings
from ai_service.providers.embeddings import EmbeddingProvider, build_embedding_provider
from ai_service.providers.llm import LLMProvider, build_llm_provider
from ai_service.rag import EmbeddingStore, build_store
from ai_service.service import ConversationService


@lru_cache(maxsize=1)
def get_settings_dep() -> AISettings:
    return get_ai_settings()


@lru_cache(maxsize=1)
def get_store() -> EmbeddingStore:
    return build_store(get_settings_dep())


@lru_cache(maxsize=1)
def get_embedder() -> EmbeddingProvider:
    return build_embedding_provider(get_settings_dep())


@lru_cache(maxsize=1)
def get_llm() -> LLMProvider:
    return build_llm_provider(get_settings_dep())


@lru_cache(maxsize=1)
def get_matcher() -> RedFlagMatcher:
    return build_matcher(get_backend_settings().ontology_dir)


@lru_cache(maxsize=1)
def get_rule_engine() -> RuleEngine:
    """The REAL deterministic engine (non-negotiable 1): /rules/evaluate runs this,
    never an LLM, and the LLM never assigns a band."""
    backend = get_backend_settings()
    return build_engine(
        backend.ontology_dir, allow_unvalidated=backend.allow_unvalidated_rules
    )


def get_backend() -> BackendSettings:
    return get_backend_settings()


def get_service() -> ConversationService:
    return ConversationService(
        settings=get_settings_dep(),
        backend_settings=get_backend(),
        matcher=get_matcher(),
        store=get_store(),
        embedder=get_embedder(),
        llm=get_llm(),
    )
