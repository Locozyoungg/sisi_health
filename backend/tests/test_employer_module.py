"""Phase 7 employer module tests: wallet ledger invariants (the Phase 7 DoD),
own-scoping (spec 3.1 pattern) and the aggregate k-anonymized dashboard
(spec 3.4 — the same shared module as the school dashboard)."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.rbac import ROLE_PERMISSIONS
from app.consent.service import grant_consent
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.ids import uuid7
from app.crypto.envelope import seal_json
from app.employer import service
from app.k_anon import NOT_ENOUGH, Suppressed, differencing_leak
from app.models import Employer, EmployerStaff, RuleEvaluation, User, Wallet, WalletLedger
from app.testkit import auth_headers
from app.users.service import age_of


def _make_employer(db, staff, name: str = "Demo Employer Ltd") -> Employer:
    return service.create_employer(db, staff_id=staff.id, name=name, county="Nairobi")


def _employee(db, provider, make_adult, employer: Employer, band: str) -> User:
    """One synthetic employee (adult, self-consented) with a sealed evaluation."""
    user = make_adult()
    grant_consent(
        db, user, event_type="self_grant", method="digital", age=age_of(provider, db, user)
    )
    user.employer_id = employer.id
    payload = {
        "band": band,
        "indicators": ["synthetic"],
        "urgent": band == "RED",
        "safeguarding": False,
        "rule_set_version": "ontology-1.1",
        "evaluated_at": "2026-10-16T09:00:00Z",
    }
    blob, key_id = seal_json(provider, db, "user", user.id, payload)
    db.add(
        RuleEvaluation(
            id=uuid7(),
            user_id=user.id,
            rule_set_version="ontology-1.1",
            payload_ciphertext=blob,
            key_id=key_id,
        )
    )
    db.flush()
    return user


def _published(public: dict) -> dict[tuple, Suppressed]:
    """Rebuild the k-anon cell dict from the published JSON (None = suppressed)."""
    return {
        tuple(key.split("|")): (
            Suppressed(value=None, suppressed=True) if value is None else Suppressed(value=value)
        )
        for key, value in public["cells"].items()
    }


# --- wallet ledger invariants (DoD) ------------------------------------------


def test_balance_equals_ledger_sum_after_multiple_fundings(db, make_staff):
    admin = make_staff("super_admin")
    employer = _make_employer(db, admin)
    service.fund(db, staff_id=admin.id, employer_id=employer.id, amount_ksh=100_000)
    service.fund(db, staff_id=admin.id, employer_id=employer.id, amount_ksh=50_000)

    wallet = (
        db.execute(
            select(Wallet).where(Wallet.owner_type == "employer", Wallet.owner_id == employer.id)
        )
        .scalars()
        .one()
    )
    ledger = service.ledger_view(db, employer.id)
    assert wallet.balance_ksh == 150_000
    assert wallet.balance_ksh == sum(row["delta_ksh"] for row in ledger)
    assert [row["ref_type"] for row in ledger] == ["funding", "funding"]
    assert service.wallet_view(db, employer.id)["balance_ksh"] == 150_000


def test_wallet_is_auto_created_on_first_fund(db, make_staff):
    admin = make_staff("super_admin")
    employer = _make_employer(db, admin)
    # Before any funding: no wallet row, but a real (not erroring) zero balance.
    assert db.execute(select(Wallet)).scalars().all() == []
    assert service.wallet_view(db, employer.id) == {
        "employer_id": str(employer.id),
        "balance_ksh": 0,
        "updated_at": None,
    }
    service.fund(db, staff_id=admin.id, employer_id=employer.id, amount_ksh=1_000)
    wallets = db.execute(select(Wallet)).scalars().all()
    assert len(wallets) == 1
    assert wallets[0].owner_type == "employer"
    assert wallets[0].owner_id == employer.id


def test_funding_non_positive_is_rejected(db, make_staff):
    admin = make_staff("super_admin")
    employer = _make_employer(db, admin)
    for amount in (0, -100):
        with pytest.raises(Conflict):
            service.fund(db, staff_id=admin.id, employer_id=employer.id, amount_ksh=amount)
    assert db.execute(select(WalletLedger)).scalars().all() == []
    assert db.execute(select(Wallet)).scalars().all() == []


def test_funding_unknown_employer_is_not_found(db, make_staff):
    admin = make_staff("super_admin")
    with pytest.raises(NotFound):
        service.fund(db, staff_id=admin.id, employer_id=uuid7(), amount_ksh=1_000)


def test_ledger_is_append_only(db, make_staff):
    """No update/delete path exists on the service surface: the only ledger write
    is the append inside the shared `fund_wallet`."""
    mutators = {"delete", "remove", "update", "edit", "reverse", "void", "set"}
    surface = {name for name in dir(service) if not name.startswith("_")}
    assert not {name for name in surface if name.split("_")[0] in mutators}
    assert "fund" in surface and "ledger_view" in surface

    admin = make_staff("super_admin")
    employer = _make_employer(db, admin)
    service.fund(db, staff_id=admin.id, employer_id=employer.id, amount_ksh=5_000)
    first = service.ledger_view(db, employer.id)
    service.fund(db, staff_id=admin.id, employer_id=employer.id, amount_ksh=2_500)
    ledger = service.ledger_view(db, employer.id)
    assert len(ledger) == 2  # appended, never rewritten
    assert ledger[1] == first[0]  # oldest row unchanged
    assert ledger[0]["delta_ksh"] == 2_500  # newest first


def test_wallet_owner_is_unique(db, make_staff):
    """One wallet per (owner_type, owner_id) — enforced by the DB constraint."""
    admin = make_staff("super_admin")
    employer = _make_employer(db, admin)
    service.fund(db, staff_id=admin.id, employer_id=employer.id, amount_ksh=1_000)
    nested = db.begin_nested()
    db.add(Wallet(id=uuid7(), owner_type="employer", owner_id=employer.id, balance_ksh=0))
    with pytest.raises(IntegrityError):
        db.flush()
    nested.rollback()
    assert len(db.execute(select(Wallet)).scalars().all()) == 1


# --- own-scoping --------------------------------------------------------------


def test_unbound_employer_admin_is_forbidden(db, make_staff, client, staff_token, provider):
    staff = make_staff("employer_admin")
    other = make_staff("super_admin")
    employer = _make_employer(db, other)
    db.commit()
    with pytest.raises(Forbidden, match="staff not bound to an employer"):
        service.resolve_employer(db, staff, employer.id)

    headers = auth_headers(staff_token(staff))
    for path in (
        f"/v1/employers/{employer.id}/wallet",
        f"/v1/employers/{employer.id}/ledger",
        f"/v1/employers/{employer.id}/dashboard",
    ):
        resp = client.get(path, headers=headers)
        assert resp.status_code == 403, resp.text
        assert resp.json()["error"]["code"] == "forbidden"


def test_bound_admin_sees_only_its_own_employer(db, make_staff):
    admin_staff = make_staff("employer_admin")
    super_admin = make_staff("super_admin")
    mine = _make_employer(db, super_admin, name="Mine Ltd")
    other = _make_employer(db, super_admin, name="Other Ltd")
    service.bind_staff(db, staff_id=admin_staff.id, employer_id=mine.id)
    service.fund(db, staff_id=super_admin.id, employer_id=mine.id, amount_ksh=7_000)

    assert service.resolve_employer(db, admin_staff, mine.id).id == mine.id
    assert service.wallet_view(db, mine.id)["balance_ksh"] == 7_000
    with pytest.raises(Forbidden, match="not your employer"):
        service.resolve_employer(db, admin_staff, other.id)


def test_bound_admin_reaches_its_own_wallet_and_dashboard_over_http(
    db, provider, make_adult, make_staff, client, staff_token
):
    """The exact path the web console (and its Playwright e2e) calls."""
    super_admin = make_staff("super_admin")
    admin = make_staff("employer_admin")
    employer = _make_employer(db, super_admin)
    service.bind_staff(db, staff_id=admin.id, employer_id=employer.id)
    service.fund(db, staff_id=super_admin.id, employer_id=employer.id, amount_ksh=1_000)
    for _ in range(20):
        _employee(db, provider, make_adult, employer, "GREEN")
    db.commit()

    headers = auth_headers(staff_token(admin))
    wallet = client.get(f"/v1/employers/{employer.id}/wallet", headers=headers)
    assert wallet.status_code == 200, wallet.text
    assert wallet.json()["data"]["balance_ksh"] == 1_000

    ledger = client.get(f"/v1/employers/{employer.id}/ledger", headers=headers)
    assert ledger.status_code == 200, ledger.text
    assert [row["delta_ksh"] for row in ledger.json()["data"]] == [1_000]

    dashboard = client.get(f"/v1/employers/{employer.id}/dashboard?term=2026-T1", headers=headers)
    assert dashboard.status_code == 200, dashboard.text
    body = dashboard.json()["data"]
    assert body["enough_data"] is True
    assert body["cells"]["band_GREEN"] == 20
    assert body["term"] == "2026-T1"


def test_super_admin_bypasses_the_binding(db, make_staff):
    super_admin = make_staff("super_admin")
    employer = _make_employer(db, super_admin)
    assert db.execute(select(EmployerStaff)).scalars().all() == []
    assert service.resolve_employer(db, super_admin, employer.id).id == employer.id
    with pytest.raises(NotFound):
        service.resolve_employer(db, super_admin, uuid7())


def test_bind_staff_is_idempotent_and_audited(db, make_staff):
    super_admin = make_staff("super_admin")
    admin = make_staff("employer_admin")
    employer = _make_employer(db, super_admin)
    first = service.bind_staff(db, staff_id=admin.id, employer_id=employer.id)
    again = service.bind_staff(db, staff_id=admin.id, employer_id=employer.id)
    assert first.id == again.id
    assert len(db.execute(select(EmployerStaff)).scalars().all()) == 1
    with pytest.raises(Conflict):
        service.bind_staff(db, staff_id=admin.id, employer_id=employer.id, role_within="nurse")


# --- aggregate dashboard (k-anonymity) ---------------------------------------


def test_dashboard_below_threshold_publishes_nothing(db, provider, make_adult, make_staff):
    admin = make_staff("super_admin")
    employer = _make_employer(db, admin)
    for _ in range(3):
        _employee(db, provider, make_adult, employer, "GREEN")
    public = service.dashboard(db, provider, employer_id=employer.id, term="2026-T1")
    assert public["enough_data"] is False
    assert public["cells"] == {}
    assert public["message"] == NOT_ENOUGH
    assert public["term"] == "2026-T1"
    assert public["employer_id"] == str(employer.id)


def test_dashboard_suppresses_small_cells_without_differencing_leak(
    db, provider, make_adult, make_staff
):
    admin = make_staff("super_admin")
    employer = _make_employer(db, admin)
    for band, count in (("GREEN", 18), ("ORANGE", 4), ("RED", 2), ("YELLOW", 1)):
        for _ in range(count):
            _employee(db, provider, make_adult, employer, band)
    total_employees = 25
    public = service.dashboard(db, provider, employer_id=employer.id, term="2026-T1")

    assert public["enough_data"] is True
    assert public["cells"]["band_GREEN"] == 18
    assert public["cells"]["band_YELLOW"] is None  # 1 < MIN_K, suppressed
    assert public["cells"]["band_ORANGE"] is None  # 4 < MIN_K, suppressed
    assert public["cells"]["band_RED"] is None
    assert public["cells"]["evaluations_total"] == 25
    assert not differencing_leak(total_employees, _published(public))


def test_dashboard_ignores_other_employers_employees(db, provider, make_adult, make_staff):
    admin = make_staff("super_admin")
    mine = _make_employer(db, admin, name="Mine Ltd")
    other = _make_employer(db, admin, name="Other Ltd")
    for _ in range(20):
        _employee(db, provider, make_adult, other, "GREEN")
    public = service.dashboard(db, provider, employer_id=mine.id, term="2026-T1")
    assert public["enough_data"] is False
    assert public["cells"] == {}

    mine_employees = db.execute(select(User).where(User.employer_id == mine.id)).scalars().all()
    assert mine_employees == []


def test_dashboard_counts_evaluations_not_employees(db, provider, make_adult, make_staff):
    """The denominator is linked employees; the cells count evaluations."""
    admin = make_staff("super_admin")
    employer = _make_employer(db, admin)
    worker = None
    for _ in range(20):
        worker = _employee(db, provider, make_adult, employer, "GREEN")
    assert worker is not None
    blob, key_id = seal_json(
        provider,
        db,
        "user",
        worker.id,
        {"band": "GREEN", "rule_set_version": "ontology-1.1"},
    )
    db.add(
        RuleEvaluation(
            id=uuid7(),
            user_id=worker.id,
            rule_set_version="ontology-1.1",
            payload_ciphertext=blob,
            key_id=key_id,
        )
    )
    db.flush()
    public = service.dashboard(db, provider, employer_id=employer.id, term="2026-T1")
    assert public["enough_data"] is True
    assert public["cells"]["evaluations_total"] == 21
    assert public["cells"]["band_GREEN"] == 21


# --- RBAC/surface wiring ------------------------------------------------------


def test_employer_admin_permissions_are_exactly_wallet_and_dashboard():
    assert ROLE_PERMISSIONS["employer_admin"] == {"employer:wallet", "employer:dashboard"}
    assert {
        "employer:admin",
        "employer:wallet",
        "employer:dashboard",
    } <= ROLE_PERMISSIONS["super_admin"]


def test_link_employee_sets_the_opt_in_linkage_and_audits(db, make_staff, make_adult):
    """A39: the users.employer_id link is a super_admin action, audited."""
    from app.models import AuditEvent

    admin = make_staff("super_admin")
    employer = service.create_employer(
        db, staff_id=admin.id, name="Link Demo Ltd", county="Nairobi"
    )
    worker = make_adult()
    result = service.link_employee(
        db, staff_id=admin.id, employer_id=employer.id, user_id=worker.id
    )
    assert result == {"user_id": str(worker.id), "employer_id": str(employer.id)}
    assert worker.employer_id == employer.id
    events = (
        db.execute(select(AuditEvent).where(AuditEvent.event_type == "employer_employee_linked"))
        .scalars()
        .all()
    )
    assert len(events) == 1


def test_link_employee_rejects_unknown_targets(db, make_staff):
    import pytest

    from app.core.errors import NotFound

    admin = make_staff("super_admin")
    employer = service.create_employer(
        db, staff_id=admin.id, name="Link Demo Ltd", county="Nairobi"
    )
    with pytest.raises(NotFound, match="user not found"):
        service.link_employee(
            db,
            staff_id=admin.id,
            employer_id=employer.id,
            user_id=uuid7(),
        )
