"""Phase 5 follow-up tracker tests (spec 5.4.1): the tracker walks the documented
cervical pathway with due dates recomputed from the ontology config, the staff view
is status-only (no results detail exists anywhere), sharing is patient-consented,
and aggregates go through the shared k-anonymity module only."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.errors import Conflict, NotFound
from app.core.time import utc_now_naive
from app.corridor import reminders, tracking
from app.corridor.config import reminder_interval_days, screening_schedule
from app.models import FollowUpTracker, TrackerEvent
from app.testkit import auth_headers

PATH = ["screened", "result_received", "further_assessment", "treatment", "follow_up",
        "completed"]
# Every hop except the terminal one; `completed` clears due_at instead of
# recomputing it (see test_completing_a_tracker_clears_due_at).
WALKABLE = PATH[:-1]

STAFF_KEYS = {
    "id",
    "pseudonym",
    "facility_id",
    "status",
    "consent_to_share",
    "due_at",
    "lost_to_follow_up",
    "updated_at",
}


def add_tracker(db, staff, user, *, facility_id=None) -> FollowUpTracker:
    created = tracking.create_tracker(
        db, user_id=user.id, facility_id=facility_id, staff_id=staff.id
    )
    return db.get(FollowUpTracker, uuid.UUID(created["id"]))


def walk(db, staff, tracker, statuses) -> None:
    for to_status in statuses:
        tracking.transition_tracker(
            db, staff_id=staff.id, tracker_id=tracker.id, to_status=to_status
        )


def assert_due_at_matches_config(tracker, status: str) -> None:
    expected = utc_now_naive() + timedelta(days=reminder_interval_days(status))
    assert abs((tracker.due_at - expected).total_seconds()) < 30


# --- transitions -------------------------------------------------------------


def test_create_tracker_starts_referred_with_configured_due_date(db, make_staff,
                                                                 adult_with_consent):
    staff = make_staff("nurse")
    tracker = add_tracker(db, staff, adult_with_consent)
    assert tracker.status == "referred"
    assert tracker.consent_to_share is False
    assert tracker.reminders_sent == 0
    assert tracker.lost_to_follow_up is False
    assert_due_at_matches_config(tracker, "referred")
    events = db.execute(
        select(TrackerEvent).where(TrackerEvent.tracker_id == tracker.id)
    ).scalars().all()
    assert [(e.status_from, e.status_to) for e in events] == [(None, "referred")]


def test_walking_the_documented_path_recomputes_due_at(db, make_staff, adult_with_consent):
    staff = make_staff("nurse")
    tracker = add_tracker(db, staff, adult_with_consent)
    for to_status in WALKABLE:
        result = tracking.transition_tracker(
            db, staff_id=staff.id, tracker_id=tracker.id, to_status=to_status
        )
        assert result["status"] == to_status
        assert_due_at_matches_config(tracker, to_status)
    assert tracker.status == "follow_up"


def test_completing_a_tracker_clears_due_at(db, make_staff, adult_with_consent):
    """The final follow_up -> completed hop reaches the terminal state and clears
    the next-reminder clock (a completed tracker is never nudged again)."""
    staff = make_staff("nurse")
    tracker = add_tracker(db, staff, adult_with_consent)
    walk(db, staff, tracker, WALKABLE)
    assert tracker.status == "follow_up"
    result = tracking.transition_tracker(
        db, staff_id=staff.id, tracker_id=tracker.id, to_status="completed"
    )
    assert result["status"] == "completed"
    assert tracker.status == "completed"
    assert tracker.due_at is None


def test_completed_is_terminal(db, make_staff, adult_with_consent):
    """`completed` is the terminal state: no transition leaves it (reached through
    the service in the test above)."""
    staff = make_staff("nurse")
    tracker = add_tracker(db, staff, adult_with_consent)
    walk(db, staff, tracker, PATH)
    assert tracker.status == "completed"
    with pytest.raises(Conflict, match="cannot move a tracker"):
        tracking.transition_tracker(
            db, staff_id=staff.id, tracker_id=tracker.id, to_status="follow_up"
        )


@pytest.mark.parametrize(
    "from_index,to_status",
    [
        (0, "result_received"),
        (0, "completed"),
        (1, "treatment"),
        (2, "screened"),
        (3, "follow_up"),
        (4, "completed"),
        (5, "treatment"),
    ],
)
def test_skipped_or_backward_transitions_are_conflicts(db, make_staff, adult_with_consent,
                                                       from_index, to_status):
    staff = make_staff("nurse")
    tracker = add_tracker(db, staff, adult_with_consent)
    walk(db, staff, tracker, PATH[:from_index])
    with pytest.raises(Conflict, match="cannot move a tracker"):
        tracking.transition_tracker(
            db, staff_id=staff.id, tracker_id=tracker.id, to_status=to_status
        )


def test_transition_unknown_tracker_is_not_found(db, make_staff):
    with pytest.raises(NotFound):
        tracking.transition_tracker(
            db, staff_id=make_staff("nurse").id, tracker_id=uuid.uuid4(), to_status="screened"
        )


def test_tracker_state_machine_is_exactly_as_specified():
    assert tracking.TRACKER_TRANSITIONS == {
        "referred": {"screened"},
        "screened": {"result_received"},
        "result_received": {"further_assessment"},
        "further_assessment": {"treatment"},
        "treatment": {"follow_up"},
        "follow_up": {"completed"},
    }
    assert tracking.TERMINAL_TRACKER == {"completed"}


# --- staff view: status only -------------------------------------------------


def test_staff_list_exposes_status_only(db, make_staff, adult_with_consent):
    staff = make_staff("nurse")
    tracker = add_tracker(db, staff, adult_with_consent)
    rows = tracking.list_trackers(db)
    assert len(rows) == 1
    assert set(rows[0].keys()) == STAFF_KEYS
    assert rows[0]["pseudonym"] == str(adult_with_consent.id)[:8]
    assert rows[0]["status"] == "referred"
    assert rows[0]["consent_to_share"] is False
    assert rows[0]["lost_to_follow_up"] is False
    # no result detail key of any kind may exist in the staff projection
    assert "results" not in rows[0]
    assert "result" not in rows[0]
    assert "indicators" not in rows[0]
    assert tracker.status == rows[0]["status"]


def test_staff_list_filters_by_status(db, make_staff, adult_with_consent):
    staff = make_staff("nurse")
    first = add_tracker(db, staff, adult_with_consent)
    second = add_tracker(db, staff, adult_with_consent)
    tracking.transition_tracker(
        db, staff_id=staff.id, tracker_id=second.id, to_status="screened"
    )
    assert {r["id"] for r in tracking.list_trackers(db)} == {str(first.id), str(second.id)}
    screened = tracking.list_trackers(db, status="screened")
    assert [r["id"] for r in screened] == [str(second.id)]
    assert tracking.list_trackers(db, status="completed") == []


def test_my_trackers_is_user_scoped(db, make_staff, adult_with_consent, make_adult):
    staff = make_staff("nurse")
    tracker = add_tracker(db, staff, adult_with_consent)
    other = make_adult()
    add_tracker(db, staff, other)
    mine = tracking.my_trackers(db, adult_with_consent)
    assert [row["id"] for row in mine] == [str(tracker.id)]
    assert set(mine[0].keys()) == {
        "id",
        "status",
        "consent_to_share",
        "due_at",
        "lost_to_follow_up",
    }
    assert len(tracking.my_trackers(db, other)) == 1


# --- consent to share --------------------------------------------------------


def test_set_sharing_toggles_for_the_owner_only(db, make_staff, adult_with_consent,
                                                make_adult):
    staff = make_staff("nurse")
    tracker = add_tracker(db, staff, adult_with_consent)
    with pytest.raises(NotFound):
        tracking.set_sharing(
            db, make_adult(), tracker_id=tracker.id, consent_to_share=True
        )
    enabled = tracking.set_sharing(
        db, adult_with_consent, tracker_id=tracker.id, consent_to_share=True
    )
    assert enabled["consent_to_share"] is True
    db.flush()
    assert tracking.list_trackers(db)[0]["consent_to_share"] is True
    disabled = tracking.set_sharing(
        db, adult_with_consent, tracker_id=tracker.id, consent_to_share=False
    )
    assert disabled["consent_to_share"] is False
    with pytest.raises(NotFound):
        tracking.set_sharing(
            db, adult_with_consent, tracker_id=uuid.uuid4(), consent_to_share=True
        )


# --- lost to follow-up (derived by the reminders job) ------------------------


def test_lost_to_follow_up_is_derived_by_the_tracker_sweep(db, make_staff,
                                                           adult_with_consent):
    """The follow-up sweep (called by the tracker reminders job) derives the flag.
    `reminders.run_reminders` also runs the screening sweep, which is pinned as
    broken in test_corridor_reminders.py, so it is called directly here."""
    config = screening_schedule()
    grace = config["reminder_grace_days"]
    max_missed = config["max_missed_reminders"]
    staff = make_staff("nurse")
    tracker = add_tracker(db, staff, adult_with_consent)
    now = utc_now_naive()
    tracker.due_at = now - timedelta(days=grace + 1)
    tracker.reminders_sent = max_missed - 1
    db.flush()
    sent: list[tuple[str, str]] = []

    report = reminders.send_tracker_reminders(db, lambda p, m: sent.append((p, m)), now)
    assert tracker.reminders_sent == max_missed
    assert tracker.lost_to_follow_up is True
    tracker_rows = [r for r in report if r["tracker"] == str(tracker.id)]
    assert tracker_rows[0]["lost_to_follow_up"] is True
    assert len(sent) == 1
    assert sent[0][1] == reminders.GENERIC_REMINDER_TEXT


def test_not_due_tracker_is_left_alone_by_the_reminders_job(db, make_staff,
                                                            adult_with_consent):
    staff = make_staff("nurse")
    tracker = add_tracker(db, staff, adult_with_consent)  # due in 30 days
    now = utc_now_naive()
    report = reminders.send_tracker_reminders(db, lambda p, m: None, now)
    assert report == []
    assert tracker.reminders_sent == 0
    assert tracker.lost_to_follow_up is False


def test_completed_tracker_gets_no_reminders(db, make_staff, adult_with_consent):
    staff = make_staff("nurse")
    tracker = add_tracker(db, staff, adult_with_consent)
    tracker.status = "completed"  # seeded: see test_completing_a_tracker_...
    tracker.due_at = utc_now_naive() - timedelta(days=60)
    db.flush()
    report = reminders.send_tracker_reminders(db, lambda p, m: None, utc_now_naive())
    assert report == []
    assert tracker.reminders_sent == 0


# --- aggregates (k-anonymity only) -------------------------------------------


def test_aggregates_below_threshold_publish_nothing(db, make_staff, adult_with_consent):
    staff = make_staff("nurse")
    add_tracker(db, staff, adult_with_consent)
    public = tracking.aggregates(db)
    assert public["enough_data"] is False
    assert public["message"] == "not_enough_data"
    assert public["cells"] == {}  # never a zero below the threshold


def seed_many(db, staff, adult_with_consent, statuses: list[str]) -> None:
    for status in statuses:
        tracker = add_tracker(db, staff, adult_with_consent)
        tracker.status = status
        db.flush()


def test_aggregates_at_threshold_publish_and_suppress_small_cells(db, make_staff,
                                                                  adult_with_consent):
    staff = make_staff("nurse")
    seed_many(db, staff, adult_with_consent, ["referred"] * 15 + ["screened"] * 3
              + ["completed"] * 2)
    public = tracking.aggregates(db)
    assert public["enough_data"] is True
    assert public["message"] is None
    cells = public["cells"]
    assert cells["status_referred"] == 15
    assert cells["status_screened"] is None  # 3 < k, suppressed
    assert cells["status_completed"] is None  # complementary partner
    assert cells["status_treatment"] == 0  # zero reveals nothing
    published = [v for v in cells.values() if v is not None]
    assert all(v == 0 or v >= 5 for v in published)
    assert cells["lost_to_follow_up"] == 0


def test_aggregates_publish_a_large_lost_to_follow_up_cell(db, make_staff,
                                                           adult_with_consent):
    staff = make_staff("nurse")
    seed_many(db, staff, adult_with_consent, ["referred"] * 20)
    trackers = db.execute(
        select(FollowUpTracker).where(FollowUpTracker.status == "referred")
    ).scalars().all()
    for tracker in trackers[:5]:
        tracker.lost_to_follow_up = True
    db.flush()
    cells = tracking.aggregates(db)["cells"]
    assert cells["status_referred"] == 20
    assert cells["lost_to_follow_up"] == 5  # >= k, so it publishes


def test_aggregates_suppress_a_small_lost_to_follow_up_cell(db, make_staff,
                                                            adult_with_consent):
    staff = make_staff("nurse")
    seed_many(db, staff, adult_with_consent, ["referred"] * 20)
    tracker = db.execute(
        select(FollowUpTracker).where(FollowUpTracker.status == "referred")
    ).scalars().first()
    tracker.lost_to_follow_up = True
    db.flush()
    cells = tracking.aggregates(db)["cells"]
    # one lost row among twenty would be identifiable: suppressed with a partner
    assert cells["lost_to_follow_up"] is None
    assert cells["status_referred"] is None


# --- endpoints ---------------------------------------------------------------


def test_tracking_endpoints_round_trip(client, db, make_staff, staff_token,
                                       adult_with_consent):
    from app.auth.tokens import create_access_token
    from app.config import get_settings

    staff = make_staff("nurse")
    db.commit()
    headers = auth_headers(staff_token(staff))
    resp = client.post(
        "/v1/corridor/tracking",
        json={"user_id": str(adult_with_consent.id)},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    tracker_id = resp.json()["data"]["id"]
    assert resp.json()["data"]["status"] == "referred"

    resp = client.post(
        f"/v1/corridor/tracking/{tracker_id}/transition",
        json={"to_status": "result_received"},
        headers=headers,
    )
    assert resp.status_code == 409

    resp = client.get("/v1/corridor/tracking", headers=headers)
    assert resp.status_code == 200, resp.text
    assert set(resp.json()["data"][0].keys()) == STAFF_KEYS

    user_headers = auth_headers(
        create_access_token(adult_with_consent.id, get_settings())
    )
    resp = client.get("/v1/corridor/tracking/me", headers=user_headers)
    assert resp.status_code == 200, resp.text
    assert [t["id"] for t in resp.json()["data"]] == [tracker_id]

    resp = client.post(
        f"/v1/corridor/tracking/me/{tracker_id}/sharing",
        json={"consent_to_share": True},
        headers=user_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["consent_to_share"] is True

    resp = client.get("/v1/corridor/tracking/aggregates", headers=headers)
    assert resp.status_code == 403  # nurse holds tracking but not aggregates
    assert resp.json()["error"]["code"] == "permission_denied"

    moh = make_staff("moh_viewer")
    db.commit()
    resp = client.get(
        "/v1/corridor/tracking/aggregates", headers=auth_headers(staff_token(moh))
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["enough_data"] is False


def test_tracker_table_has_no_result_detail_column():
    """Guard: the tracker table itself has no results-detail column (spec 5.4.1)."""
    columns = {c.name for c in FollowUpTracker.__table__.columns}
    assert columns == {
        "id",
        "user_id",
        "facility_id",
        "status",
        "consent_to_share",
        "due_at",
        "reminders_sent",
        "last_reminder_at",
        "lost_to_follow_up",
        "created_at",
        "updated_at",
    }
    assert not any("result" in name for name in columns)
