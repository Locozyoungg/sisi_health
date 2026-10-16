"""HTTP surface (spec 5.2, decision D7).

Three routes, all gated by the shared internal bearer token (A35):
`POST /v1/ai/ask` (education answers), `POST /v1/ai/rules/evaluate` (the REAL
deterministic engine — zero LLM involvement) and `POST /v1/ai/index` (re-index the
ontology library, audited with counts only).
"""

import secrets
from typing import Annotated, Any, Literal

from app.api.envelope import ok
from app.audit.service import record_event
from app.core.errors import Unauthorized
from app.db import get_db
from app.rules.engine import RuleEngine
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai_service.config import AISettings
from ai_service.deps import (
    get_embedder,
    get_rule_engine,
    get_service,
    get_settings_dep,
    get_store,
)
from ai_service.providers.embeddings import EmbeddingProvider
from ai_service.rag import EmbeddingStore, index_content
from ai_service.service import AskRequest, ConversationService

router = APIRouter()


def require_internal_token(
    settings: Annotated[AISettings, Depends(get_settings_dep)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Shared-secret gate for /v1/ai/* (A35). Constant-time compare; the caller is
    another internal service (mobile app or gateway), not a browser."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthorized("missing bearer token")
    if not secrets.compare_digest(token, settings.ai_internal_token):
        raise Unauthorized("invalid internal token")


AuthDep = Depends(require_internal_token)


@router.post("/ask", dependencies=[AuthDep])
def ask(
    body: AskRequest,
    service: Annotated[ConversationService, Depends(get_service)],
) -> dict[str, Any]:
    """Education / explanation / next-step guidance. Every routing decision made
    before the model is deterministic; the model's answer passes the post-filter or
    becomes a refusal."""
    return ok(service.ask(body).model_dump())


class RulesEvaluateRequest(BaseModel):
    age: int = Field(ge=13, le=120)
    features: dict[str, float | bool] = Field(default_factory=dict)
    mode: Literal["diary", "assessment"] = "assessment"
    diary_days: int = Field(default=0, ge=0)


@router.post("/rules/evaluate", dependencies=[AuthDep])
def rules_evaluate(
    body: RulesEvaluateRequest,
    engine: Annotated[RuleEngine, Depends(get_rule_engine)],
) -> dict[str, Any]:
    """The backend's deterministic engine, evaluated in-process: the same bands,
    indicators and escalations the app and the gateway use. The AI service never
    computes, adjusts, or second-guesses a band."""
    if body.mode == "diary":
        evaluation = engine.evaluate(
            age=body.age, diary_days=body.diary_days, features=body.features
        )
    else:
        evaluation = engine.evaluate_assessment(age=body.age, features=body.features)
    return ok(evaluation.model_dump(mode="json"))


class IndexRequest(BaseModel):
    language: Literal["en", "sw", "sheng"] | None = None


@router.post("/index", dependencies=[AuthDep])
def index(
    body: IndexRequest,
    db: Annotated[Session, Depends(get_db)],
    store: Annotated[EmbeddingStore, Depends(get_store)],
    embedder: Annotated[EmbeddingProvider, Depends(get_embedder)],
    settings: Annotated[AISettings, Depends(get_settings_dep)],
) -> dict[str, Any]:
    """(Re)index /ontology content. The audit event carries counts and the mode
    only — never chunk text (spec 6, non-negotiable 5)."""
    count = index_content(
        store,
        embedder,
        settings.ontology_dir,
        embedder.model,
        embedder.dim,
        language=body.language,
        max_chunk_chars=settings.ai_rag_max_chunk_chars,
    )
    record_event(
        db,
        event_type="ai_content_indexed",
        actor_type="system",
        actor_id=None,
        actor_role=None,
        resource_type="ai_content",
        resource_id=None,
        payload={
            "chunks_indexed": count,
            "embedding_mode": store.mode,
            "model": embedder.model,
            "language": body.language,
        },
    )
    db.commit()
    return ok(
        {
            "chunks_indexed": count,
            "embedding_mode": store.mode,
            "model": embedder.model,
        }
    )


__all__ = ["router", "require_internal_token"]
