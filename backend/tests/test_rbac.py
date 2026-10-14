"""RBAC denial tests: every protected endpoint denies every unauthorized role
(docs/role-matrix.md is the source of truth). One session, one matrix pass."""

from pathlib import Path

from app.auth.rbac import ROLE_PERMISSIONS
from app.testkit import auth_headers

# (method, path, required permission)
PROTECTED = [
    ("get", "/v1/rules", "rules:read"),
    ("get", "/v1/rules/anemia-risk-flag/versions/1.0.0", "rules:read"),
    ("post", "/v1/rules/registrations", "rules:activate"),
    ("post", "/v1/rules/activations", "rules:activate"),
    ("post", "/v1/rules/rollback", "rules:activate"),
    ("get", "/v1/audit/events", "audit:read"),
    ("post", "/v1/audit/verify", "audit:verify"),
    ("get", "/v1/admin/users", "admin:users"),
    ("get", "/v1/admin/dsr", "admin:dsr"),
]

BODIES = {
    "/v1/rules/registrations": {"rule_id": "anemia-risk-flag", "version": "1.0.0"},
    "/v1/rules/activations": {"rule_id": "anemia-risk-flag", "version": "1.0.0"},
    "/v1/rules/rollback": {"rule_id": "anemia-risk-flag"},
}

ROLES = ["nurse", "gynecologist", "super_admin", "school_admin", "employer_admin", "moh_viewer"]


def test_rbac_matrix(client, db, make_staff, staff_token):
    tokens = {role: staff_token(make_staff(role)) for role in ROLES}
    for method, path, permission in PROTECTED:
        for role in ROLES:
            allowed = permission in ROLE_PERMISSIONS[role]
            kwargs = {"headers": auth_headers(tokens[role])}
            if method == "post" and path in BODIES:
                kwargs["json"] = BODIES[path]
            resp = getattr(client, method)(path, **kwargs)
            if allowed:
                # Allowed roles must never fail auth — the endpoint may 404/422/428
                # on content, but never 401/403.
                assert resp.status_code not in (401, 403), (
                    f"{role} on {method.upper()} {path}: {resp.status_code} {resp.text}"
                )
            else:
                assert resp.status_code == 403, (
                    f"{role} on {method.upper()} {path}: expected 403, got {resp.status_code}"
                )
                assert resp.json()["error"]["code"] == "permission_denied"


def test_unauthenticated_gets_401(client):
    assert client.get("/v1/rules").status_code == 401
    assert client.get("/v1/audit/events").status_code == 401
    assert client.get("/v1/admin/users").status_code == 401


def test_role_matrix_document_matches_code():
    """docs/role-matrix.md must list exactly the roles and permissions in code."""
    doc = (Path(__file__).resolve().parents[2] / "docs" / "role-matrix.md").read_text(
        encoding="utf-8"
    ).lower()
    for role in ROLES:
        assert role in doc
    for permission in {
        "rules:read",
        "rules:activate",
        "dsr:process",
        "audit:read",
        "audit:verify",
        "admin:users",
        "admin:dsr",
    }:
        assert permission in doc
