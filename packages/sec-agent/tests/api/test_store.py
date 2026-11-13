"""What the API keeps: questions per user per day, the turns asked, and their feedback.

Runs on the in-memory store and on Postgres. Every user here is made up for a test; the
`real` and `simulated` cohorts are counted apart and never added together.
"""

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

from api_kit import NOW, OTHER, REAL, SIM, THREAD, TODAY

from sec_agent.api.identity import Identity
from sec_agent.api.store import ApiStore, CohortCounts, Feedback, TurnRecord
from sec_agent.api.store_postgres import PostgresApiStore

TOMORROW = TODAY + dt.timedelta(days=1)


def _turn(
    user: Identity, turn: int = 1, *, thread: str = THREAD, degraded: bool = False
) -> TurnRecord:
    return TurnRecord(
        user_id=user.user_id,
        cohort=user.cohort,
        thread_id=thread,
        turn=turn,
        asked_at=NOW,
        status="degraded" if degraded else "answered",
        degraded=degraded,
    )


def _feedback(user: Identity, rating: str, turn: int = 1, *, thread: str = THREAD) -> Feedback:
    return Feedback.model_validate(
        {
            "user_id": user.user_id,
            "cohort": user.cohort,
            "thread_id": thread,
            "turn": turn,
            "rating": rating,
            "at": NOW,
        }
    )


def test_questions_are_counted_up_to_the_daily_limit_and_no_further(store: ApiStore) -> None:
    assert [store.charge_question(REAL, TODAY, 3) for _ in range(5)] == [1, 2, 3, None, None]
    assert store.questions_used(REAL.user_id, TODAY) == 3


def test_each_user_and_each_day_has_its_own_count(store: ApiStore) -> None:
    assert store.charge_question(REAL, TODAY, 1) == 1
    assert store.charge_question(REAL, TODAY, 1) is None
    assert store.charge_question(OTHER, TODAY, 1) == 1
    assert store.charge_question(REAL, TOMORROW, 1) == 1
    assert store.questions_used("github:nobody", TODAY) == 0


def test_replicas_racing_for_the_last_questions_never_pass_the_limit(api_db: str) -> None:
    with PostgresApiStore.connect(api_db) as a, PostgresApiStore.connect(api_db) as b:

        def charge(i: int) -> int | None:
            return (a if i % 2 else b).charge_question(REAL, TODAY, 5)

        with ThreadPoolExecutor(max_workers=8) as pool:
            counts = list(pool.map(charge, range(24)))
        assert sorted(c for c in counts if c is not None) == [1, 2, 3, 4, 5]
        assert a.questions_used(REAL.user_id, TODAY) == 5


def test_feedback_is_kept_only_for_a_turn_the_same_user_asked(store: ApiStore) -> None:
    store.record_turn(_turn(REAL))
    assert store.save_feedback(_feedback(REAL, "up")) is True
    assert store.save_feedback(_feedback(OTHER, "down")) is False, "another user's turn"
    assert store.save_feedback(_feedback(REAL, "up", turn=2)) is False, "no such turn"
    assert store.save_feedback(_feedback(REAL, "up", thread="thread-0002")) is False
    assert store.cohort_counts(TODAY, TODAY)["real"].thumbs_up == 1


def test_rating_a_turn_again_replaces_the_earlier_rating(store: ApiStore) -> None:
    store.record_turn(_turn(REAL))
    store.save_feedback(_feedback(REAL, "up"))
    store.save_feedback(_feedback(REAL, "down"))
    counts = store.cohort_counts(TODAY, TODAY)["real"]
    assert (counts.thumbs_up, counts.thumbs_down) == (0, 1)


def test_recording_a_turn_twice_keeps_one_row(store: ApiStore) -> None:
    store.record_turn(_turn(REAL))
    store.record_turn(_turn(REAL))
    assert store.cohort_counts(TODAY, TODAY)["real"].turns == 1


def test_simulated_users_are_counted_apart_from_real_ones(store: ApiStore) -> None:
    store.record_turn(_turn(REAL, 1))
    store.record_turn(_turn(REAL, 2, degraded=True))
    store.record_turn(_turn(OTHER, 1, thread="thread-0002"))
    for turn in (1, 2, 3):
        store.record_turn(_turn(SIM, turn, thread="thread-0003"))
    store.save_feedback(_feedback(REAL, "up"))
    store.save_feedback(_feedback(SIM, "down", thread="thread-0003"))
    store.save_feedback(_feedback(SIM, "down", turn=2, thread="thread-0003"))

    counts = store.cohort_counts(TODAY, TODAY)
    assert counts == {
        "real": CohortCounts(
            users=2, conversations=2, turns=3, degraded_turns=1, thumbs_up=1, thumbs_down=0
        ),
        "simulated": CohortCounts(
            users=1, conversations=1, turns=3, degraded_turns=0, thumbs_up=0, thumbs_down=2
        ),
    }


def test_counts_cover_only_the_days_asked_for(store: ApiStore) -> None:
    store.record_turn(_turn(REAL))
    empty = CohortCounts(
        users=0, conversations=0, turns=0, degraded_turns=0, thumbs_up=0, thumbs_down=0
    )
    assert store.cohort_counts(TOMORROW, TOMORROW) == {"real": empty, "simulated": empty}
