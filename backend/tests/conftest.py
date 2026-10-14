"""Test fixtures. Env is pinned BEFORE any app import: fixed master key, test DB,
dev flags (never leaked into staging/prod by the settings guards)."""

import base64
import os
import uuid

os.environ["SISI_ENV"] = "dev"
os.environ["SISI_DATABASE_URL"] = "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi_test"
os.environ["SISI_TEST_DATABASE_URL"] = (
    "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi_test"
)
os.environ["SISI_ALLOW_UNVALIDATED_RULES"] = "true"
os.environ["SISI_OTP_DEV_RETURN"] = "true"
os.environ["SISI_MASTER_KEY_B64"] = base64.b64encode(b"t" * 32).decode()

from datetime import date  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.consent.service import ensure_consent_texts, grant_consent  # noqa: E402
from app.crypto.key_provider import DatabaseKeyProvider  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, StaffUser  # noqa: E402
from app.users.service import age_of, create_user  # noqa: E402

ADMIN_URL = "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/postgres"
TEST_URL = os.environ["SISI_TEST_DATABASE_URL"]

_phone_counter = 0


def _next_phone() -> str:
    global _phone_counter
    _phone_counter += 1
    return f"+2547{_phone_counter:08d}"


@pytest.fixture(scope="session")
def test_engine():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS sisi_test WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE sisi_test"))
    admin.dispose()

    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", TEST_URL)
    command.upgrade(cfg, "head")

    engine = create_engine(TEST_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(test_engine) -> Session:
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
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def provider() -> DatabaseKeyProvider:
    return DatabaseKeyProvider(get_settings())


@pytest.fixture()
def settings():
    return get_settings()


@pytest.fixture()
def make_adult(db, provider):
    def _make() -> tuple:
        ensure_consent_texts(db)
        user = create_user(
            db,
            provider,
            phone=_next_phone(),
            birth_date=date(2000, 1, 15),
            language="en",
            settings=get_settings(),
        )
        db.commit()
        return user

    return _make


@pytest.fixture()
def make_minor(db, provider):
    def _make() -> tuple:
        ensure_consent_texts(db)
        user = create_user(
            db,
            provider,
            phone=_next_phone(),
            birth_date=date(2010, 3, 10),
            language="en",
            settings=get_settings(),
        )
        db.commit()
        return user

    return _make


@pytest.fixture()
def adult_with_consent(make_adult, db, provider):
    user = make_adult()
    grant_consent(
        db,
        user,
        event_type="self_grant",
        method="digital",
        age=age_of(provider, db, user),
    )
    db.commit()
    return user


@pytest.fixture()
def minor_with_consent(make_minor, db, provider):
    user = make_minor()
    age = age_of(provider, db, user)
    grant_consent(db, user, event_type="guardian_grant", method="digital", age=age)
    grant_consent(db, user, event_type="minor_assent", method="digital", age=age)
    db.commit()
    return user


@pytest.fixture()
def make_staff(db, provider):
    from app.auth.staff import create_staff
    from app.core.time import utc_now_naive

    def _make(role: str) -> StaffUser:
        ensure_consent_texts(db)
        staff = create_staff(
            db,
            provider,
            email=f"{role}-{uuid.uuid4().hex[:8]}@sisi.test",
            password="correct-horse-battery",  # noqa: S106 — synthetic test credential
            role=role,
        )
        staff.last_active_at = utc_now_naive()  # freshly issued account = active session
        db.commit()
        return staff

    return _make


@pytest.fixture()
def staff_token():
    from app.auth.tokens import create_staff_access_token

    def _make(staff: StaffUser) -> str:
        return create_staff_access_token(staff.id, staff.role, get_settings())

    return _make


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_via_otp(client, *, phone: str, birth_date: str) -> dict:
    """Full OTP registration; returns the auth header dict."""
    resp = client.post("/v1/auth/otp/request", json={"phone": phone})
    assert resp.status_code == 200, resp.text
    code = resp.json()["data"]["dev_otp"]
    resp = client.post(
        "/v1/auth/otp/verify",
        json={
            "phone": phone,
            "code": code,
            "device_id": str(uuid.uuid4()),
            "birth_date": birth_date,
        },
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
