"""G-judge sampler: equal strata (short ones give their share away), seeded, blind."""

from collections import Counter

import pytest

from sec_agent.eval.judge.models import BlindItem, Candidate, Stratum
from sec_agent.eval.judge.sample import allocate, sample_items


def test_allocate_splits_equally_and_hands_a_short_strata_share_to_the_others() -> None:
    available: dict[Stratum, int] = {
        "correct": 300,
        "wrong_number": 80,
        "wrong_period": 84,
        "citation": 11,
    }
    assert allocate(available, 100) == {
        "correct": 30,
        "wrong_number": 30,
        "wrong_period": 29,
        "citation": 11,
    }


def test_allocate_takes_everything_when_the_pool_is_small() -> None:
    available: dict[Stratum, int] = {"correct": 3, "citation": 2}
    assert allocate(available, 100) == {"correct": 3, "citation": 2}


def test_allocate_rejects_a_non_positive_total() -> None:
    with pytest.raises(ValueError, match="total"):
        allocate({"correct": 3}, 0)


def candidate(stratum: Stratum, system: str, n: int) -> Candidate:
    return Candidate(
        origin="numeric",
        record_id=f"gnum-{n:016x}",
        system=system,
        model=f"model-{system}",
        stratum=stratum,
        grader_error=None if stratum == "correct" else "wrong_value",
        turns=(f"Question {n}?",),
        asked_on=None,
        answer=f"Answer {n} from {system}.",
        sources=(),
    )


def pool() -> list[Candidate]:
    out: list[Candidate] = []
    n = 0
    counts: tuple[tuple[Stratum, int], ...] = (
        ("correct", 40),
        ("wrong_number", 12),
        ("wrong_period", 3),
    )
    for stratum, count in counts:
        for system in ("b0", "b1"):
            for _ in range(count):
                out.append(candidate(stratum, system, n))
                n += 1
    return out


def test_sample_meets_the_allocation_and_spreads_over_systems() -> None:
    items, key = sample_items(pool(), total=30, seed=7)
    assert len(items) == len(key) == 30
    strata = Counter(k.stratum for k in key)
    assert strata == {"correct": 12, "wrong_number": 12, "wrong_period": 6}
    correct_systems = Counter(k.system for k in key if k.stratum == "correct")
    assert correct_systems == {"b0": 6, "b1": 6}


def test_sample_is_seeded_and_ordered_by_opaque_id() -> None:
    first, _ = sample_items(pool(), total=30, seed=7)
    again, _ = sample_items(list(reversed(pool())), total=30, seed=7)
    other, _ = sample_items(pool(), total=30, seed=8)
    assert first == again
    assert [i.id for i in first] == sorted(i.id for i in first)
    assert {i.answer for i in first} != {i.answer for i in other}


def test_blind_items_hold_no_system_verdict_or_gold() -> None:
    items, key = sample_items(pool(), total=30, seed=7)
    assert set(BlindItem.model_fields) == {"id", "turns", "asked_on", "answer", "sources"}
    assert all(i.id.startswith("gj-") for i in items)
    for item in items:
        dumped = item.model_dump_json()
        assert "model-b" not in dumped
        assert "wrong_" not in dumped
    by_id = {k.id: k for k in key}
    assert set(by_id) == {i.id for i in items}
    for item in items:
        k = by_id[item.id]
        assert k.grader_verdict == ("correct" if k.stratum == "correct" else "incorrect")
        assert item.answer.endswith(f"from {k.system}.")
