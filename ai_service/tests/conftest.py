"""AI service test fixtures. Env is pinned BEFORE any app import (test DB, master
key, dev flags, dev internal token) exactly like the gateway/backend conftests, so
a developer .env can never change what CI exercises. The session database is
dropped/recreated and migrated to head, giving whichever embedding mode the server
supports: vector(768) on a pgvector server, JSONB on the portable dev Postgres."""

import base64
import os

os.environ["SISI_ENV"] = "dev"
os.environ["SISI_DATABASE_URL"] = "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi_test"
os.environ["SISI_TEST_DATABASE_URL"] = (
    "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi_test"
)
os.environ["SISI_ALLOW_UNVALIDATED_RULES"] = "true"
os.environ["SISI_MASTER_KEY_B64"] = base64.b64encode(b"t" * 32).decode()
os.environ["SISI_AI_LLM_PROVIDER"] = "stub"
os.environ["SISI_AI_EMBEDDING_PROVIDER"] = "stub"
os.environ["SISI_AI_INTERNAL_TOKEN"] = "dev-only-ai-token-change-me"

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from app.config import Settings as BackendSettings  # noqa: E402
from app.config import get_settings as get_backend_settings  # noqa: E402
from app.rules.loader import build_matcher  # noqa: E402
from app.rules.redflags import RedFlagMatcher  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from ai_service.config import AISettings  # noqa: E402
from ai_service.deps import get_embedder, get_service, get_store  # noqa: E402
from ai_service.providers.embeddings import EmbeddingProvider, StubEmbeddingProvider  # noqa: E402
from ai_service.providers.llm import RecordingLLMProvider, StubProvider  # noqa: E402
from ai_service.rag import EmbeddingStore, build_store, index_content  # noqa: E402
from ai_service.service import ConversationService  # noqa: E402

AI_SERVICE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = AI_SERVICE_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"

ADMIN_URL = "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/postgres"
TEST_URL = os.environ["SISI_TEST_DATABASE_URL"]
INTERNAL_TOKEN = os.environ["SISI_AI_INTERNAL_TOKEN"]


def auth_headers(token: str = INTERNAL_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS sisi_test WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE sisi_test"))
    admin.dispose()

    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", TEST_URL)
    command.upgrade(cfg, "head")

    engine = create_engine(TEST_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(test_engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    session = factory()
    yield session
    session.rollback()
    # ai.* is truncated (tests re-index per test); audit_events too so the audit
    # assertions see only this test's rows (TRUNCATE bypasses the append-only
    # row triggers, which is fine in a test database).
    with test_engine.begin() as conn:
        conn.execute(text("TRUNCATE ai.chunk_embeddings, ai.content_chunks RESTART IDENTITY"))
        conn.execute(text("TRUNCATE audit.audit_events RESTART IDENTITY"))
    session.close()


@pytest.fixture(scope="session")
def settings() -> AISettings:
    """Session-scoped: the store fixture (and its engine) is shared across tests."""
    return AISettings()


@pytest.fixture()
def backend_settings() -> BackendSettings:
    return get_backend_settings()


@pytest.fixture()
def matcher(backend_settings: BackendSettings) -> RedFlagMatcher:
    return build_matcher(backend_settings.ontology_dir)


@pytest.fixture(scope="session")
def embedder() -> EmbeddingProvider:
    return StubEmbeddingProvider(dim=768)


@pytest.fixture(scope="session")
def store(settings: AISettings) -> EmbeddingStore:
    """The DB's real mode: pgvector where the extension is installed, else JSONB."""
    return build_store(settings)


@pytest.fixture()
def seeded_store(
    store: EmbeddingStore, embedder: EmbeddingProvider, settings: AISettings
) -> EmbeddingStore:
    """The real store, indexed from /ontology content for this test."""
    index_content(
        store,
        embedder,
        settings.ontology_dir,
        embedder.model,
        embedder.dim,
        max_chunk_chars=settings.ai_rag_max_chunk_chars,
    )
    return store


@pytest.fixture()
def llm() -> RecordingLLMProvider:
    return RecordingLLMProvider(StubProvider())


@pytest.fixture()
def service(
    settings: AISettings,
    backend_settings: BackendSettings,
    matcher: RedFlagMatcher,
    seeded_store: EmbeddingStore,
    embedder: EmbeddingProvider,
    llm: RecordingLLMProvider,
) -> ConversationService:
    return ConversationService(
        settings=settings,
        backend_settings=backend_settings,
        matcher=matcher,
        store=seeded_store,
        embedder=embedder,
        llm=llm,
    )


@pytest.fixture()
def client(
    service: ConversationService, seeded_store: EmbeddingStore, embedder: EmbeddingProvider
) -> Iterator[TestClient]:
    """TestClient with the service/store/embedder dependencies overridden."""
    from ai_service.main import app

    app.dependency_overrides[get_service] = lambda: service
    app.dependency_overrides[get_store] = lambda: seeded_store
    app.dependency_overrides[get_embedder] = lambda: embedder
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
