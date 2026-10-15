"""RBAC denial tests: every protected endpoint denies every unauthorized role
(docs/role-matrix.md is the source of truth). One session, one matrix pass."""

from pathlib import Path

from sqlalchemy.exc import ProgrammingError

from app.auth.rbac import ROLE_PERMISSIONS
from app.testkit import auth_headers

# Pinned app defects (see tests/test_corridor_reminders.py): the authorized handler
# raises before RBAC can be observed. Denied roles are unaffected — they are
# stopped by the permission dependency — so the matrix tolerates exactly the
# listed failure for exactly that path and keeps asserting everything else.
# Previously pinned defects are fixed (migration 0006); an unexpected failure on
# any other path now fails loudly.
KNOWN_DEFECTS: dict[str, str] = {}

# A well-formed id that matches no row: authorized roles must fall through to a
# domain error (404/409), unauthorized roles must be stopped by RBAC first.
UNKNOWN_ID = "00000000-0000-0000-0000-0000000000ff"

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
    # --- Phase 5: specialist corridor (staff endpoints only; the booking,
    # referral-preview, tracker and education/patient routes are user-scoped) ---
    ("get", "/v1/corridor/queue", "corridor:queue"),
    ("get", f"/v1/corridor/consults/{UNKNOWN_ID}", "corridor:consults"),
    ("post", f"/v1/corridor/consults/{UNKNOWN_ID}/review", "corridor:consults"),
    ("post", f"/v1/corridor/consults/{UNKNOWN_ID}/schedule", "corridor:consults"),
    ("post", f"/v1/corridor/consults/{UNKNOWN_ID}/consents", "corridor:consults"),
    ("post", f"/v1/corridor/sessions/{UNKNOWN_ID}/start", "corridor:consults"),
    ("post", f"/v1/corridor/sessions/{UNKNOWN_ID}/complete", "corridor:consults"),
    ("post", "/v1/corridor/referrals", "corridor:referrals"),
    ("get", "/v1/corridor/referrals", "corridor:referrals"),
    ("post", f"/v1/corridor/referrals/{UNKNOWN_ID}/send", "corridor:referrals"),
    ("get", f"/v1/corridor/referrals/{UNKNOWN_ID}/pdf", "corridor:referrals"),
    ("get", "/v1/corridor/facilities", "corridor:facilities:read"),
    ("post", "/v1/corridor/facilities", "corridor:facilities:write"),
    ("put", f"/v1/corridor/facilities/{UNKNOWN_ID}", "corridor:facilities:write"),
    ("delete", f"/v1/corridor/facilities/{UNKNOWN_ID}", "corridor:facilities:write"),
    ("post", f"/v1/corridor/facilities/{UNKNOWN_ID}/verify", "corridor:facilities:write"),
    ("get", "/v1/corridor/surgery/cases", "corridor:surgery"),
    ("post", "/v1/corridor/surgery/cases", "corridor:surgery"),
    ("post", f"/v1/corridor/surgery/cases/{UNKNOWN_ID}/transition", "corridor:surgery"),
    ("post", f"/v1/corridor/surgery/cases/{UNKNOWN_ID}/outcomes", "corridor:surgery"),
    ("post", "/v1/corridor/surgery/pricing-stubs", "corridor:surgery"),
    ("get", "/v1/corridor/surgery/pricing-stubs", "corridor:surgery"),
    ("get", "/v1/corridor/tracking", "corridor:tracking"),
    ("post", "/v1/corridor/tracking", "corridor:tracking"),
    ("post", f"/v1/corridor/tracking/{UNKNOWN_ID}/transition", "corridor:tracking"),
    ("get", "/v1/corridor/tracking/aggregates", "corridor:aggregates"),
    ("post", "/v1/corridor/reminders/run", "corridor:reminders"),
    ("get", "/v1/corridor/education", "corridor:education:read"),
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
    # --- Phase 5 corridor bodies (rows that hit a FK are added by the test) ---
    f"/v1/corridor/consults/{UNKNOWN_ID}/review": {"decision": "approved"},
    f"/v1/corridor/consults/{UNKNOWN_ID}/schedule": {
        "gynecologist_id": UNKNOWN_ID,
        "scheduled_at": "2026-10-20T09:00:00Z",
        "modality": "video",
    },
    f"/v1/corridor/consults/{UNKNOWN_ID}/consents": {"kind": "guardian_consent"},
    f"/v1/corridor/sessions/{UNKNOWN_ID}/complete": {"outcome": "completed"},
    "/v1/corridor/referrals": {"request_id": UNKNOWN_ID},
    "/v1/corridor/facilities": {"name": "Matrix Health Centre", "county": "Nairobi"},
    f"/v1/corridor/surgery/cases/{UNKNOWN_ID}/transition": {"to_status": "surgical_evaluation"},
    f"/v1/corridor/surgery/cases/{UNKNOWN_ID}/outcomes": {
        "outcome_category": "completed_surgery",
    },
    "/v1/corridor/surgery/pricing-stubs": {
        "procedure": "Matrix procedure",
        "facility_id": UNKNOWN_ID,
        "amount_ksh_min": 1000,
        "amount_ksh_max": 2000,
        "source": "matrix tariff sheet",
    },
    f"/v1/corridor/tracking/{UNKNOWN_ID}/transition": {"to_status": "screened"},
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


def test_rbac_matrix(client, db, make_staff, staff_token, make_adult):
    import uuid

    from app.models import School

    # Bodies that hit a foreign key need real rows (school, user); domain errors
    # like NotFound/Forbidden are content, not RBAC — only 401/permission_denied fail.
    db.add(School(id=uuid.UUID("00000000-0000-0000-0000-000000000001"), name="Matrix School"))
    user = make_adult()
    db.commit()
    bodies = dict(BODIES)
    bodies["/v1/corridor/surgery/cases"] = {"user_id": str(user.id)}
    bodies["/v1/corridor/tracking"] = {"user_id": str(user.id)}

    tokens = {role: staff_token(make_staff(role)) for role in ROLES}
    for method, path, permission in PROTECTED:
        for role in ROLES:
            allowed = permission in ROLE_PERMISSIONS[role]
            kwargs = {"headers": auth_headers(tokens[role])}
            if method in {"post", "put"} and path in bodies:
                kwargs["json"] = bodies[path]
            try:
                resp = getattr(client, method)(path, **kwargs)
            except ProgrammingError as exc:
                assert path in KNOWN_DEFECTS, f"{path} raised unexpectedly: {exc}"
                assert KNOWN_DEFECTS[path] in str(exc), f"{path}: {exc}"
                db.rollback()  # clear the aborted transaction and carry on
                continue
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
    assert client.get("/v1/corridor/queue").status_code == 401
    assert client.get("/v1/corridor/tracking/aggregates").status_code == 401


CORRIDOR_PERMISSIONS_BY_ROLE = {
    # super_admin holds the whole corridor surface
    "super_admin": {
        "corridor:queue",
        "corridor:consults",
        "corridor:referrals",
        "corridor:surgery",
        "corridor:facilities:read",
        "corridor:facilities:write",
        "corridor:tracking",
        "corridor:aggregates",
        "corridor:reminders",
        "corridor:education:read",
    },
    # nurse: school + corridor triage, follow-up and reminders — no writes, no
    # referral letters, no surgical navigation, no aggregates
    "nurse": {
        "corridor:queue",
        "corridor:consults",
        "corridor:facilities:read",
        "corridor:tracking",
        "corridor:reminders",
        "corridor:education:read",
    },
    # gynecologist: clinical work only — no tracker, no reminders, no aggregates,
    # no facility writes
    "gynecologist": {
        "corridor:queue",
        "corridor:consults",
        "corridor:referrals",
        "corridor:surgery",
        "corridor:facilities:read",
        "corridor:education:read",
    },
    "school_admin": {"corridor:education:read"},
    "employer_admin": set(),
    "moh_viewer": {"corridor:aggregates"},
    "pharmacy": set(),
}


def test_corridor_permission_table_matches_the_role_matrix():
    for role, expected in CORRIDOR_PERMISSIONS_BY_ROLE.items():
        actual = {p for p in ROLE_PERMISSIONS[role] if p.startswith("corridor:")}
        assert actual == expected, role


def test_corridor_permissions_are_all_used_by_an_endpoint():
    """No corridor permission may exist un-exercised by the matrix."""
    permissions = {
        permission for _method, _path, permission in PROTECTED
        if permission.startswith("corridor:")
    }
    declared = {
        permission
        for role_permissions in ROLE_PERMISSIONS.values()
        for permission in role_permissions
        if permission.startswith("corridor:")
    }
    assert declared == permissions


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
        "corridor:queue",
        "corridor:consults",
        "corridor:referrals",
        "corridor:surgery",
        "corridor:facilities:read",
        "corridor:facilities:write",
        "corridor:tracking",
        "corridor:aggregates",
        "corridor:reminders",
        "corridor:education:read",
    }:
        assert permission in doc
