"""HTTP surface (D7/A35): the internal bearer gate, the response envelope, request
validation, /rules/evaluate parity with the real backend engine, and the audited
/index endpoint."""

import pytest
from app.rules.loader import build_engine
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from ai_service.config import AISettings
from ai_service.deps import get_service
from ai_service.errors import GuardrailRefused
from ai_service.providers.llm import HostedProvider, RecordingLLMProvider
from ai_service.rag import EmbeddingStore
from ai_service.service import ConversationService
from tests.conftest import auth_headers

GATED_REQUESTS = [
    ("/v1/ai/ask", {"text": "Nina maumivu ya hedhi"}),
    ("/v1/ai/rules/evaluate", {"age": 20, "features": {}}),
    ("/v1/ai/index", {}),
]


def test_health_needs_no_token(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(("path", "payload"), GATED_REQUESTS)
def test_every_ai_route_requires_the_internal_token(
    client: TestClient, path: str, payload: dict
) -> None:
    for headers in ({}, {"Authorization": "Bearer wrong-token"}, {"Authorization": "Basic x"}):
        response = client.post(path, json=payload, headers=headers)
        assert response.status_code == 401, (path, headers)
        body = response.json()
        assert body["success"] is False
        assert body["data"] is None
        assert body["error"]["code"] == "unauthorized"
        assert body["meta"]["status"] == 401


def test_ask_education_happy_path(client: TestClient, llm: RecordingLLMProvider) -> None:
    response = client.post(
        "/v1/ai/ask",
        json={"text": "Nina maumivu ya hedhi kila mwezi", "language": "sw", "band": "YELLOW"},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True and body["error"] is None
    data = body["data"]
    assert data["routing"] == "education"
    assert data["language"] == "sw"
    assert data["band"] == "YELLOW"
    assert data["citations"] and data["citations"][0]["chunk_id"]
    assert data["provider"] == "stub"
    assert data["postfilter_reason"] is None
    assert llm.count == 1


def test_ask_red_flag_routes_to_the_urgent_script(
    client: TestClient, llm: RecordingLLMProvider
) -> None:
    response = client.post(
        "/v1/ai/ask",
        json={"text": "I have sudden severe pain", "band": "RED"},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["routing"] == "urgent_script"
    assert "116" in data["text"] and "1195" in data["text"]
    assert llm.count == 0
    assert data["citations"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"text": ""},
        {"text": "   "},
        {"text": "hello", "language": "fr"},
        {"text": "hello", "age": 12},
        {"text": "hello", "age": 150},
        {"text": "x" * 2001},
        {"text": "hello", "band": "BLUE"},
        {"text": "hello", "indicators": ["Not A Rule Id"]},
    ],
)
def test_ask_rejects_invalid_requests(client: TestClient, payload: dict) -> None:
    response = client.post("/v1/ai/ask", json=payload, headers=auth_headers())
    assert response.status_code == 422


def test_ask_rejects_identifier_fields_the_schema_does_not_have(client: TestClient) -> None:
    """The contract has no identifier field: an extra field is ignored by pydantic
    (extra='ignore'), but it can never reach a prompt — asserted in test_service."""
    response = client.post(
        "/v1/ai/ask",
        json={"text": "Nina maumivu ya hedhi", "phone_number": "+254712345678"},
        headers=auth_headers(),
    )
    assert response.status_code == 200


def test_rules_evaluate_matches_the_backend_engine(client: TestClient, backend_settings) -> None:
    features = {"self_harm_signal": True}
    engine = build_engine(
        backend_settings.ontology_dir,
        allow_unvalidated=backend_settings.allow_unvalidated_rules,
    )
    expected = engine.evaluate_assessment(age=16, features=features)

    response = client.post(
        "/v1/ai/rules/evaluate",
        json={"age": 16, "features": features, "mode": "assessment"},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["band"] == expected.band == "RED"
    assert data["indicators"] == expected.indicators
    assert data["urgent"] is True
    assert data["safeguarding"] is True
    assert data["rule_set_version"] == expected.rule_set_version
    assert data["evaluated_at"]


def test_rules_evaluate_diary_mode_needs_the_diary_window(client: TestClient) -> None:
    features = {"self_harm_signal": True}
    too_early = client.post(
        "/v1/ai/rules/evaluate",
        json={"age": 20, "features": features, "mode": "diary", "diary_days": 3},
        headers=auth_headers(),
    )
    assert too_early.json()["data"]["band"] == "NOT_ENOUGH_DATA"
    later = client.post(
        "/v1/ai/rules/evaluate",
        json={"age": 20, "features": features, "mode": "diary", "diary_days": 30},
        headers=auth_headers(),
    )
    assert later.json()["data"]["band"] == "RED"


def test_rules_evaluate_refuses_under_13(client: TestClient) -> None:
    response = client.post(
        "/v1/ai/rules/evaluate", json={"age": 12, "features": {}}, headers=auth_headers()
    )
    assert response.status_code == 422  # users under 13 are blocked at the contract


def test_index_endpoint_indexes_content_and_writes_an_audit_event(
    client: TestClient, db: Session, store: EmbeddingStore
) -> None:
    response = client.post("/v1/ai/index", json={}, headers=auth_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["chunks_indexed"] > 0
    assert data["embedding_mode"] == store.mode
    assert data["model"]

    db.rollback()
    rows = (
        db.execute(
            text(
                "SELECT actor_type, resource_type, payload FROM audit.audit_events "
                "WHERE event_type = 'ai_content_indexed'"
            )
        )
        .mappings()
        .all()
    )
    assert len(rows) == 1
    event = rows[0]
    assert event["actor_type"] == "system"
    assert event["resource_type"] == "ai_content"
    payload = event["payload"]
    assert payload["chunks_indexed"] == data["chunks_indexed"]
    assert payload["embedding_mode"] == data["embedding_mode"]
    assert "text" not in payload and "content" not in payload  # counts only


def test_index_endpoint_filters_by_language(client: TestClient, store: EmbeddingStore) -> None:
    response = client.post("/v1/ai/index", json={"language": "sw"}, headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["data"]["chunks_indexed"] > 0
    invalid = client.post("/v1/ai/index", json={"language": "fr"}, headers=auth_headers())
    assert invalid.status_code == 422


def test_unconfigured_llm_provider_returns_a_503_envelope(
    client: TestClient,
    settings: AISettings,
    backend_settings,
    matcher,
    seeded_store: EmbeddingStore,
    embedder,
) -> None:
    from ai_service.main import app

    service = ConversationService(
        settings=settings,
        backend_settings=backend_settings,
        matcher=matcher,
        store=seeded_store,
        embedder=embedder,
        llm=HostedProvider(AISettings()),  # selected provider, no credentials (H15)
    )
    app.dependency_overrides[get_service] = lambda: service
    response = client.post(
        "/v1/ai/ask",
        json={"text": "Tell me about period pain", "band": "YELLOW"},
        headers=auth_headers(),
    )
    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "provider_not_configured"


def test_guardrail_refused_maps_to_a_422_envelope(client: TestClient) -> None:
    from ai_service.main import app

    def _boom() -> None:
        raise GuardrailRefused("refuse_diagnosis")

    app.dependency_overrides[get_service] = _boom
    response = client.post(
        "/v1/ai/ask", json={"text": "Nina maumivu ya hedhi"}, headers=auth_headers()
    )
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "guardrail_refused"
    assert body["error"]["message"]


def test_ask_is_deterministic_for_the_same_input(client: TestClient) -> None:
    payload = {"text": "Tell me about period pain", "band": "YELLOW"}
    first = client.post("/v1/ai/ask", json=payload, headers=auth_headers()).json()["data"]
    second = client.post("/v1/ai/ask", json=payload, headers=auth_headers()).json()["data"]
    assert first["text"] == second["text"]
    assert first["routing"] == second["routing"]
    assert [c["chunk_id"] for c in first["citations"]] == [
        c["chunk_id"] for c in second["citations"]
    ]
