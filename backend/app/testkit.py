"""Shared test helpers, importable as a package module (CI-safe: does not depend
on pytest's sys.path rootdir insertion)."""

import uuid


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_via_otp(client, *, phone: str, birth_date: str) -> dict[str, str]:
    """Full OTP registration against the API; returns the auth header dict."""
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
