"""Auth throttle (CC-6, Phase 8): sliding window, lockout, clear-on-success, the
staff-login and totp/setup integration, and the staging/prod CORS guard.

Run this file alone: the session fixture rebuilds the shared `sisi_test`
database, so a concurrent pytest process would collide with it.
"""

import base64
import json
from datetime import timedelta

import pyotp
import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from app.auth.rate_limit import (
    check_and_record,
    clear,
    is_locked,
    staff_login_key,
    staff_totp_setup_key,
)
from app.auth.staff import login_staff, setup_totp
from app.config import Settings, get_settings
from app.core.errors import Locked, RateLimited, Unauthorized
from app.core.time import utc_now_naive
from app.models import AuditEvent, AuthThrottle

LOGIN_URL = "/v1/staff/auth/login"
SETUP_URL = "/v1/staff/auth/totp/setup"
CORRECT_PASSWORD = "correct-horse-battery"


def _row(db, key: str) -> AuthThrottle | None:
    return db.execute(select(AuthThrottle).where(AuthThrottle.key == key)).scalars().first()


def _limits(settings: Settings) -> dict[str, int]:
    return {
        "max_attempts": settings.staff_login_max_failures,
        "window_minutes": settings.staff_login_window_minutes,
        "lockout_minutes": settings.staff_login_lockout_minutes,
    }


def _staff_with_totp(db, provider, make_staff):
    staff = make_staff("nurse")
    uri = setup_totp(db, provider, staff)
    db.commit()
    return staff, pyotp.parse_uri(uri)


def _login(client, email: str, password: str, code: str):
    return client.post(LOGIN_URL, json={"email": email, "password": password, "totp_code": code})


def _setup(client, email: str, password: str):
    return client.post(SETUP_URL, json={"email": email, "password": password})


# --- the limiter itself ---------------------------------------------------------


def test_window_reset_restarts_the_count(db):
    key = "test:window"
    for _ in range(2):
        check_and_record(db, key, max_attempts=3, window_minutes=10, lockout_minutes=15)
    assert _row(db, key).count == 2

    row = _row(db, key)
    row.window_start = utc_now_naive() - timedelta(minutes=11)
    db.flush()
    check_and_record(db, key, max_attempts=3, window_minutes=10, lockout_minutes=15)

    assert not is_locked(db, key)  # the third attempt of the OLD window did not lock
    assert _row(db, key).count == 1


def test_lockout_after_max_failures(db):
    key = "test:lockout"
    for _ in range(4):
        check_and_record(db, key, max_attempts=5, window_minutes=10, lockout_minutes=15)
    assert not is_locked(db, key)

    with pytest.raises(Locked):
        check_and_record(db, key, max_attempts=5, window_minutes=10, lockout_minutes=15)
    assert is_locked(db, key)

    with pytest.raises(Locked):  # a further attempt never extends the lock
        check_and_record(db, key, max_attempts=5, window_minutes=10, lockout_minutes=15)


def test_lockout_expires_and_the_next_window_starts_clean(db):
    key = "test:expiry"
    for _ in range(4):
        check_and_record(db, key, max_attempts=5, window_minutes=10, lockout_minutes=15)
    with pytest.raises(Locked):
        check_and_record(db, key, max_attempts=5, window_minutes=10, lockout_minutes=15)

    row = _row(db, key)
    assert row.locked_until is not None
    row.locked_until = utc_now_naive() - timedelta(seconds=1)
    row.window_start = utc_now_naive() - timedelta(minutes=11)
    db.flush()

    assert not is_locked(db, key)
    check_and_record(db, key, max_attempts=5, window_minutes=10, lockout_minutes=15)
    assert _row(db, key).count == 1


def test_rate_limited_when_no_lockout_is_configured(db):
    key = "test:rate"
    check_and_record(db, key, max_attempts=2, window_minutes=10, lockout_minutes=0)
    with pytest.raises(RateLimited):
        check_and_record(db, key, max_attempts=2, window_minutes=10, lockout_minutes=0)
    assert not is_locked(db, key)


def test_clear_removes_the_counter(db):
    key = "test:clear"
    check_and_record(db, key, max_attempts=5, window_minutes=10, lockout_minutes=15)
    clear(db, key)
    assert not is_locked(db, key)
    assert _row(db, key) is None

    check_and_record(db, key, max_attempts=5, window_minutes=10, lockout_minutes=15)
    assert _row(db, key).count == 1


# --- staff login integration ----------------------------------------------------


def test_staff_login_wrong_password_locks_out_even_correct_credentials(
    client, db, provider, make_staff
):
    staff, totp = _staff_with_totp(db, provider, make_staff)
    settings = get_settings()
    code = totp.now()

    for _ in range(settings.staff_login_max_failures - 1):
        resp = _login(client, staff.email, "wrong-password", code)
        assert resp.status_code == 401, resp.text

    locked = _login(client, staff.email, "wrong-password", code)
    assert locked.status_code == 423
    assert "try again later" in locked.json()["error"]["message"]

    # The lock is not a decoy: correct credentials are refused too (and the
    # counter survives the failed request — it is committed before the error).
    refused = _login(client, staff.email, CORRECT_PASSWORD, code)
    assert refused.status_code == 423
    assert is_locked(db, staff_login_key(staff.email))
    assert _row(db, staff_login_key(staff.email)).count == settings.staff_login_max_failures


def test_staff_login_wrong_totp_is_counted(db, provider, make_staff):
    staff, _totp = _staff_with_totp(db, provider, make_staff)
    for _ in range(3):
        with pytest.raises(Unauthorized):
            login_staff(
                db,
                provider,
                email=staff.email,
                password=CORRECT_PASSWORD,
                totp_code="000000",
            )
    assert _row(db, staff_login_key(staff.email)).count == 3


def test_staff_login_success_clears_the_counter(client, db, provider, make_staff):
    staff, totp = _staff_with_totp(db, provider, make_staff)

    for _ in range(2):
        # The TOTP is irrelevant while the password is wrong (the counter is
        # checked/recorded first); a static code keeps the test independent of
        # wall-clock drift on a loaded CI box.
        assert _login(client, staff.email, "wrong-password", "000000").status_code == 401
    assert _row(db, staff_login_key(staff.email)).count == 2

    # A code generated now, right before the request (TOTP windows are 30s).
    resp = _login(client, staff.email, CORRECT_PASSWORD, totp.now())
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["role"] == "nurse"
    assert _row(db, staff_login_key(staff.email)) is None


def test_lock_engages_writes_a_counts_only_audit_event(client, db, provider, make_staff):
    staff, totp = _staff_with_totp(db, provider, make_staff)
    settings = get_settings()
    code = totp.now()

    for _ in range(settings.staff_login_max_failures):
        _login(client, staff.email, "wrong-password", code)

    events = (
        db.execute(select(AuditEvent).where(AuditEvent.event_type == "staff_login_locked"))
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload == {
        "max_failures": settings.staff_login_max_failures,
        "window_minutes": settings.staff_login_window_minutes,
        "lockout_minutes": settings.staff_login_lockout_minutes,
    }
    assert staff.email not in json.dumps(payload)  # never the credential handle


# --- totp/setup throttle --------------------------------------------------------


def test_totp_setup_is_throttled_per_email(client, db, provider, make_staff):
    staff = make_staff("nurse")
    db.commit()
    settings = get_settings()

    for _ in range(settings.staff_login_max_failures - 1):
        assert _setup(client, staff.email, "wrong-password").status_code == 401

    # Email case must not buy a fresh budget: throttle keys are lowercased.
    assert _setup(client, staff.email.upper(), "wrong-password").status_code == 423
    assert is_locked(db, staff_totp_setup_key(staff.email))
    # Each auth surface keeps its own budget.
    assert not is_locked(db, staff_login_key(staff.email))


def test_totp_setup_success_clears_the_counter(client, db, provider, make_staff):
    staff = make_staff("nurse")
    db.commit()

    assert _setup(client, staff.email, "wrong-password").status_code == 401
    assert _row(db, staff_totp_setup_key(staff.email)).count == 1

    resp = _setup(client, staff.email, CORRECT_PASSWORD)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["otpauth_uri"].startswith("otpauth://")
    assert _row(db, staff_totp_setup_key(staff.email)) is None


# --- CORS origins guard (staging/prod) ------------------------------------------


def _prod_settings(**overrides) -> Settings:
    base = {
        "env": "prod",
        "allow_unvalidated_rules": False,
        "otp_dev_return": False,
        "jwt_secret": "prod-test-jwt-secret-not-a-real-one",
        "phone_pepper": "prod-test-pepper-not-a-real-one",
        "jitsi_app_secret": "prod-test-jitsi-secret-not-a-real-one",
        "master_key_b64": base64.b64encode(b"t" * 32).decode(),
    }
    base.update(overrides)
    return Settings(**base)


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_cors_origins_are_required_outside_dev_and_demo(env):
    with pytest.raises(PydanticValidationError, match="CORS"):
        _prod_settings(env=env, cors_origins="")
    with pytest.raises(PydanticValidationError, match="CORS"):
        _prod_settings(env=env, cors_origins="  ,  ")  # whitespace is not an origin

    settings = _prod_settings(env=env, cors_origins="https://console.sisi.test")
    assert settings.cors_origins.strip() == "https://console.sisi.test"


def test_cors_origins_may_stay_empty_in_dev():
    assert Settings(env="dev", cors_origins="").cors_origins == ""
