"""OTP: dev-return flow, rate limiting, lockout, expiry, and the API e2e."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.auth.otp import normalize_phone, request_otp, verify_otp
from app.config import get_settings
from app.core.errors import Locked, RateLimited, Unauthorized, ValidationError
from app.models import OtpRequest
from tests.conftest import register_via_otp


def test_normalize_phone():
    assert normalize_phone("0712 345 678") == "+0712345678"  # digits preserved as-entered
    assert normalize_phone("+254712345678") == "+254712345678"
    with pytest.raises(ValidationError):
        normalize_phone("123")


def test_dev_return_and_verify(db):
    settings = get_settings()
    code = request_otp(db, "+254700000001", settings)
    assert code is not None and len(code) == 6
    verify_otp(db, "+254700000001", code, settings)  # must not raise
    # second verify with the same code fails (code consumed)
    with pytest.raises(Unauthorized):
        verify_otp(db, "+254700000001", code, settings)


def test_rate_limit_per_phone_hash(db):
    settings = get_settings()
    phone = "+254700000002"
    for _ in range(settings.otp_max_requests_per_window):
        request_otp(db, phone, settings)
    with pytest.raises(RateLimited):
        request_otp(db, phone, settings)


def test_lockout_after_failures(db):
    settings = get_settings()
    phone = "+254700000003"
    request_otp(db, phone, settings)
    for _ in range(settings.otp_max_failures):
        with pytest.raises(Unauthorized):
            verify_otp(db, phone, "000000", settings)
    with pytest.raises(Locked):
        verify_otp(db, phone, "000000", settings)


def test_expiry(db):
    settings = get_settings()
    phone = "+254700000004"
    code = request_otp(db, phone, settings)
    row = db.execute(select(OtpRequest)).scalars().first()
    row.expires_at = row.expires_at - timedelta(seconds=settings.otp_ttl_seconds + 10)
    db.flush()
    with pytest.raises(Unauthorized, match="expired"):
        verify_otp(db, phone, code, settings)


def test_otp_survives_across_sessions(test_engine, settings):
    """Regression: request in one session, verify in a fresh one (real request
    lifecycle — the shared-session test client cannot catch this)."""
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    with factory() as s1:
        code = request_otp(s1, "+254700000005", settings)
        s1.commit()
    with factory() as s2:
        verify_otp(s2, "+254700000005", code, settings)  # must not raise
        s2.commit()


def test_otp_api_e2e_registration(client):
    headers = register_via_otp(client, phone="+254711111111", birth_date="2000-01-15")
    resp = client.get("/v1/users/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["data"]["age_band"] == "18+"
    assert "phone" not in resp.json()["data"]


def test_otp_api_rejects_minor_under_13(client):
    resp = client.post("/v1/auth/otp/request", json={"phone": "+254722222222"})
    code = resp.json()["data"]["dev_otp"]
    resp = client.post(
        "/v1/auth/otp/verify",
        json={
            "phone": "+254722222222",
            "code": code,
            "device_id": str(uuid.uuid4()),
            "birth_date": "2015-01-01",  # 11 years old
        },
    )
    assert resp.status_code == 422
    assert "under 13" in resp.json()["error"]["message"]


def test_otp_api_wrong_code(client):
    client.post("/v1/auth/otp/request", json={"phone": "+254733333333"})
    resp = client.post(
        "/v1/auth/otp/verify",
        json={
            "phone": "+254733333333",
            "code": "999999",
            "device_id": str(uuid.uuid4()),
            "birth_date": "2000-01-15",
        },
    )
    assert resp.status_code == 401


def test_refresh_rotation_and_reuse_revocation(client):
    register_via_otp(client, phone="+254744444444", birth_date="2000-01-15")
    resp = client.post("/v1/auth/otp/request", json={"phone": "+254744444444"})
    code = resp.json()["data"]["dev_otp"]
    resp = client.post(
        "/v1/auth/otp/verify",
        json={
            "phone": "+254744444444",
            "code": code,
            "device_id": str(uuid.uuid4()),
            "birth_date": "2000-01-15",
        },
    )
    refresh_token = resp.json()["data"]["refresh_token"]
    rotated = client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert rotated.status_code == 200
    new_refresh = rotated.json()["data"]["refresh_token"]
    # reuse of the OLD token revokes the family
    reused = client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert reused.status_code == 401
    # and the NEW token is dead too
    after = client.post("/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert after.status_code == 401


def test_user_endpoints_need_auth(client):
    assert client.get("/v1/diary/entries").status_code == 401
    assert client.get("/v1/users/me").status_code == 401


def test_envelope_shape(client):
    resp = client.get("/v1/health")
    body = resp.json()
    assert body["success"] is True
    assert body["data"] == {"status": "ok", "version": "0.1.0"}
    assert body["error"] is None
    assert body["meta"] == {}
