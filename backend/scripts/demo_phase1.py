"""Phase 1 demo: proves the non-negotiables live, end to end, against a seeded
dev database. Every step prints PASS/FAIL and the script exits non-zero on any
failure — this is `make demo-phase1`."""

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.audit.verifier import verify_chain
from app.config import get_settings
from app.db import SessionLocal
from app.main import app

DEMO_PHONES = {"adult": "+254700000101", "minor_few_days": "+254700000103"}

STEP = 0
FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global STEP
    STEP += 1
    mark = "PASS" if condition else "FAIL"
    print(f"[{STEP:02d}] {mark}  {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def main() -> int:
    settings = get_settings()
    if settings.env not in {"dev", "demo"}:
        print("demo_phase1 refuses to run outside dev/demo")
        return 1

    with TestClient(app) as client:
        # 1. OTP registration (dev-return path) for the seeded adult.
        resp = client.post("/v1/auth/otp/request", json={"phone": DEMO_PHONES["adult"]})
        code = resp.json()["data"]["dev_otp"]
        resp = client.post(
            "/v1/auth/otp/verify",
            json={
                "phone": DEMO_PHONES["adult"],
                "code": code,
                "device_id": str(uuid.uuid4()),
                "birth_date": "1998-05-02",
            },
        )
        check(
            "OTP verify (existing synthetic adult)",
            resp.status_code == 200,
            f"status={resp.status_code}",
        )
        user_headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}

        # 2. Consent state: adult self-consent active.
        resp = client.get("/v1/consent/grants/state", headers=user_headers)
        state = resp.json()["data"]
        check(
            "Consent state satisfied (adult, self-consent)",
            state["satisfied"] is True,
            json.dumps(state["held"]),
        )

        # 3. Diary has the 90 synthetic days.
        resp = client.get("/v1/diary/entries", headers=user_headers)
        check("Diary sync/readback (90 synthetic days)", len(resp.json()["data"]) == 90)

        # 4. Rules engine: deterministic band with indicators (never a diagnosis).
        resp = client.post("/v1/rules/evaluate", headers=user_headers)
        eval_data = resp.json()["data"]
        check(
            "Rules engine returns a band + indicators",
            eval_data["band"] in ("GREEN", "YELLOW", "ORANGE", "RED", "NOT_ENOUGH_DATA"),
            f"band={eval_data['band']} indicators={eval_data['indicators']}",
        )

        # 5. Minor with 13 days -> NOT_ENOUGH_DATA, never a band.
        resp = client.post("/v1/auth/otp/request", json={"phone": DEMO_PHONES["minor_few_days"]})
        code = resp.json()["data"]["dev_otp"]
        resp = client.post(
            "/v1/auth/otp/verify",
            json={
                "phone": DEMO_PHONES["minor_few_days"],
                "code": code,
                "device_id": str(uuid.uuid4()),
                "birth_date": "2012-06-01",
            },
        )
        minor_headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
        resp = client.post("/v1/rules/evaluate", headers=minor_headers)
        check(
            "Insufficient data (<14 days) returns NOT_ENOUGH_DATA",
            resp.json()["data"]["band"] == "NOT_ENOUGH_DATA",
        )

        # 6. Under-13 blocked at the age check.
        resp = client.post("/v1/auth/otp/request", json={"phone": "+254700000199"})
        code = resp.json()["data"]["dev_otp"]
        resp = client.post(
            "/v1/auth/otp/verify",
            json={
                "phone": "+254700000199",
                "code": code,
                "device_id": str(uuid.uuid4()),
                "birth_date": "2014-01-01",
            },
        )
        check("Users under 13 are blocked", resp.status_code == 422)

        # 7. RBAC: nurse token cannot read the admin queue.
        with SessionLocal() as db:
            from sqlalchemy import select

            from app.auth.tokens import create_staff_access_token
            from app.models import StaffUser

            nurse = (
                db.execute(select(StaffUser).where(StaffUser.email == "nurse@sisi.demo"))
                .scalars()
                .first()
            )
            # Fresh activity, exactly as a real login would set it (idle timeout is
            # enforced per request; a stale last_active_at would 401 the demo).
            from app.auth.staff import touch_activity

            touch_activity(db, nurse)
            db.commit()
            nurse_token = create_staff_access_token(nurse.id, nurse.role, settings)
        resp = client.get("/v1/admin/users", headers={"Authorization": f"Bearer {nurse_token}"})
        check("RBAC denies nurse on admin endpoints", resp.status_code == 403)
        resp = client.get("/v1/rules", headers={"Authorization": f"Bearer {nurse_token}"})
        check("RBAC allows nurse to read rules", resp.status_code == 200)

        # 8. Red-flag text matching routes urgent (deterministic, pre-LLM).
        from app.rules.loader import build_matcher

        matcher = build_matcher(settings.ontology_dir)
        hits = matcher.match_text("maumivu ni 10 kati ya 10 na naweweseka")
        escalations = matcher.escalations(hits)
        check(
            "Kiswahili red-flag text routes urgent",
            escalations["urgent"] is True,
            f"hits={[h.pattern_id for h in hits]}",
        )

        # 9. Audit chain verifies.
        with SessionLocal() as db:
            report = verify_chain(db)
            check(
                "Audit hash chain verifies",
                report["ok"] is True,
                f"{report['events_checked']} events",
            )

        # 10. Erasure pipeline: DSR erasure destroys the synthetic adult's data.
        resp = client.post("/v1/dsr/requests", json={"type": "erasure"}, headers=user_headers)
        dsr_id = resp.json()["data"]["id"]
        with SessionLocal() as db:
            from sqlalchemy import select

            from app.auth.tokens import create_staff_access_token
            from app.models import StaffUser

            admin = (
                db.execute(select(StaffUser).where(StaffUser.email == "super_admin@sisi.demo"))
                .scalars()
                .first()
            )
            from app.auth.staff import touch_activity

            touch_activity(db, admin)
            db.commit()
            admin_token = create_staff_access_token(admin.id, admin.role, settings)
        resp = client.post(
            f"/v1/dsr/requests/{dsr_id}/process",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        check(
            "Erasure pipeline completes via DSR",
            resp.status_code == 200 and resp.json()["data"]["result"]["erased"],
        )
        resp = client.get("/v1/diary/entries", headers=user_headers)
        check("Erased user cannot read diary", resp.status_code == 401)
        with SessionLocal() as db:
            report = verify_chain(db)
            check(
                "Audit chain intact after erasure",
                report["ok"] is True,
                f"{report['events_checked']} events",
            )

    print()
    if FAILURES:
        print(f"DEMO FAILED: {len(FAILURES)} step(s) failed")
        return 1
    print(f"DEMO PASSED: {STEP} steps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
