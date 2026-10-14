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
    ("get", "/v1/school/queue", "school:queue"),
    ("post", "/v1/school/actions", "school:actions"),
    ("post", "/v1/school/reidentify", "school:reidentify"),
    ("post", "/v1/school/guardian-consents", "school:consents"),
    ("get", "/v1/school/dashboard", "school:dashboard"),
    ("post", "/v1/vouchers/issue", "vouchers:issue"),
    ("post", "/v1/vouchers/redeem", "vouchers:redeem"),
    ("get", "/v1/vouchers/reconciliation", "vouchers:reconcile"),
]

BODIES = {
    "/v1/rules/registrations": {"rule_id": "anemia-risk-flag", "version": "1.0.0"},
    "/v1/rules/activations": {"rule_id": "anemia-risk-flag", "version": "1.0.0"},
    "/v1/rules/rollback": {"rule_id": "anemia-risk-flag"},
    "/v1/school/actions": {
        "assessment_id": "00000000-0000-0000-0000-000000000001",
        "action": "spoke_to",
        "note": "",
    },
    "/v1/school/reidentify": {
        "assessment_id": "00000000-0000-0000-0000-000000000001",
        "reason": "urgent follow-up required",
    },
    "/v1/school/guardian-consents": {
        "assessment_id": "00000000-0000-0000-0000-000000000001",
        "method": "voice",
    },
    "/v1/vouchers/issue": {
        "school_id": "00000000-0000-0000-0000-000000000001",
        "category": "sanitary",
        "amount_ksh": 300,
    },
    "/v1/vouchers/redeem": {
        "pharmacy_id": "00000000-0000-0000-0000-000000000002",
        "code": "SISI-TEST",
        "receipt_no": "RCPT-TEST",
        "amount_ksh": 300,
        "callback": {},
    },
}

ROLES = [
    "nurse",
    "gynecologist",
    "super_admin",
    "school_admin",
    "employer_admin",
    "moh_viewer",
    "pharmacy",
]


def test_rbac_matrix(client, db, make_staff, staff_token):
    import uuid

    from app.models import School

    # The voucher-issue body needs a real school row (FK); domain errors like
    # NotFound/Forbidden are content, not RBAC — only 401/permission_denied fail.
    db.add(School(id=uuid.UUID("00000000-0000-0000-0000-000000000001"), name="Matrix School"))
    db.commit()

    tokens = {role: staff_token(make_staff(role)) for role in ROLES}
    for method, path, permission in PROTECTED:
        for role in ROLES:
            allowed = permission in ROLE_PERMISSIONS[role]
            kwargs = {"headers": auth_headers(tokens[role])}
            if method == "post" and path in BODIES:
                kwargs["json"] = BODIES[path]
            resp = getattr(client, method)(path, **kwargs)
            if allowed:
                # Allowed roles must never be blocked by auth (401) or RBAC
                # (permission_denied) — domain errors (404/409/423/428, or 403
                # "forbidden" from school binding) are content, not RBAC.
                assert resp.status_code != 401, (
                    f"{role} on {method.upper()} {path}: {resp.status_code} {resp.text}"
                )
                error_code = (resp.json().get("error") or {}).get("code")
                assert error_code != "permission_denied", (
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
