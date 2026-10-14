"""Staff auth: TOTP setup/login, idle timeout, and token scoping."""

from datetime import timedelta

import pyotp

from app.auth.staff import login_staff, setup_totp
from app.auth.tokens import decode_token
from app.config import get_settings
from app.core.errors import Unauthorized
from app.core.time import utc_now_naive
from tests.conftest import auth_headers


def test_staff_totp_setup_and_login(db, provider, make_staff):
    staff = make_staff("nurse")
    uri = setup_totp(db, provider, staff)
    db.commit()
    assert uri.startswith("otpauth://")
    code = pyotp.parse_uri(uri).now()
    logged_in = login_staff(
        db, provider, email=staff.email, password="correct-horse-battery", totp_code=code
    )
    assert logged_in.id == staff.id
    assert logged_in.totp_confirmed is True


def test_staff_login_wrong_password(db, provider, make_staff):
    staff = make_staff("nurse")
    setup_totp(db, provider, staff)
    db.commit()
    import pytest

    with pytest.raises(Unauthorized):
        login_staff(db, provider, email=staff.email, password="wrong-password", totp_code="123456")


def test_staff_login_requires_confirmed_totp(db, provider, make_staff):
    staff = make_staff("nurse")
    db.commit()
    import pytest

    with pytest.raises(Unauthorized, match="not set up"):
        login_staff(
            db, provider, email=staff.email, password="correct-horse-battery", totp_code="123456"
        )


def test_staff_token_scopes(client, db, make_staff, staff_token):
    staff = make_staff("nurse")
    token = staff_token(staff)
    payload = decode_token(token, get_settings())
    assert payload["scope"] == "staff"
    assert payload["role"] == "nurse"
    # staff tokens cannot access user-scope endpoints
    resp = client.get("/v1/users/me", headers=auth_headers(token))
    assert resp.status_code == 401


def test_staff_idle_timeout(client, db, make_staff, staff_token):
    from app.auth.staff import touch_activity

    staff = make_staff("nurse")
    touch_activity(db, staff)
    db.commit()
    token = staff_token(staff)
    staff.last_active_at = utc_now_naive() - timedelta(minutes=20)
    db.commit()
    resp = client.get("/v1/rules", headers=auth_headers(token))
    assert resp.status_code == 401
    assert "idle" in resp.json()["error"]["message"]


def test_staff_password_min_length(db, provider):
    import pytest

    from app.auth.staff import create_staff
    from app.core.errors import ValidationError

    with pytest.raises(ValidationError, match="12"):
        create_staff(db, provider, email="shortpw@sisi.test", password="short", role="nurse")
