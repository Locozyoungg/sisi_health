"""Gateway test fixtures. Env pinned BEFORE app imports: test DB + master key,
matching the backend conftest; the session store uses the Postgres fallback
(Redis is unavailable in this environment — assumption A19)."""

import base64
import os

os.environ["SISI_ENV"] = "dev"
os.environ["SISI_DATABASE_URL"] = "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi_test"
os.environ["SISI_TEST_DATABASE_URL"] = (
    "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi_test"
)
os.environ["SISI_ALLOW_UNVALIDATED_RULES"] = "true"
os.environ["SISI_MASTER_KEY_B64"] = base64.b64encode(b"t" * 32).decode()
os.environ["SISI_USSD_SESSION_BACKEND"] = "postgres"

import pytest  # noqa: E402
from app.models import Base  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from gateway.main import app  # noqa: E402

ADMIN_URL = "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/postgres"
TEST_URL = os.environ["SISI_TEST_DATABASE_URL"]


@pytest.fixture(scope="session")
def test_engine():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS sisi_test WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE sisi_test"))
    admin.dispose()

    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig("../backend/alembic.ini")
    cfg.set_main_option("script_location", "../backend/migrations")
    cfg.set_main_option("sqlalchemy.url", TEST_URL)
    command.upgrade(cfg, "head")

    engine = create_engine(TEST_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(test_engine):
    factory = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    session = factory()
    yield session
    session.rollback()
    with test_engine.begin() as conn:
        names = ", ".join(
            f'"{t.schema}"."{t.name}"' for t in Base.metadata.sorted_tables if t.schema is not None
        )
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    session.close()


@pytest.fixture()
def recording_sms():
    from gateway.providers.messaging import RecordingProvider

    return RecordingProvider()


@pytest.fixture()
def flow(test_engine, recording_sms):
    """A FlowEngine on the Postgres session fallback + recording SMS provider."""
    from app.config import get_settings as backend_settings
    from app.crypto.key_provider import DatabaseKeyProvider
    from app.rules.loader import build_engine

    from gateway.config import GatewaySettings
    from gateway.flows.engine import FlowEngine
    from gateway.sessions.store import PostgresSessionStore

    backend = backend_settings()
    return FlowEngine(
        store=PostgresSessionStore(),
        settings=GatewaySettings(),
        engine=build_engine(backend.ontology_dir, allow_unvalidated=True),
        provider=DatabaseKeyProvider(backend),
        sms=recording_sms,
    )


@pytest.fixture()
def gateway_client(test_engine, recording_sms):
    """TestClient with the flow dependency overridden to the Postgres-backed engine."""
    from gateway.deps import get_flow_engine

    app.dependency_overrides[get_flow_engine] = lambda: flow_engine_for_test()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def flow_engine_for_test():
    from app.config import get_settings as backend_settings
    from app.crypto.key_provider import DatabaseKeyProvider
    from app.rules.loader import build_engine

    from gateway.config import GatewaySettings
    from gateway.flows.engine import FlowEngine
    from gateway.providers.messaging import RecordingProvider
    from gateway.sessions.store import PostgresSessionStore

    backend = backend_settings()
    return FlowEngine(
        store=PostgresSessionStore(),
        settings=GatewaySettings(),
        engine=build_engine(backend.ontology_dir, allow_unvalidated=True),
        provider=DatabaseKeyProvider(backend),
        sms=RecordingProvider(),
    )


def ussd_post(client, session_id: str, phone: str, text: str = "") -> str:
    resp = client.post(
        "/ussd/callback",
        data={
            "sessionId": session_id,
            "serviceCode": "*384*01#",
            "phoneNumber": phone,
            "text": text,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.text
