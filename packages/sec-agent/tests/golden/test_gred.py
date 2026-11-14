"""G-red: at least 100 attacks (direct, injected into filing text, requests for advice)
and at least 100 benign questions, generated from templates with a fixed seed.

Every item is synthetic: written for the test set, never a real user's question, and its
planted passages are simulated filing text, never real.
"""

from collections import Counter
from pathlib import Path

from sec_agent.golden.gred.generate import generate_gred
from sec_agent.golden.gred.models import RedItem
from sec_agent.golden.jsonl import read_jsonl

COMMITTED = Path(__file__).parents[4] / "data" / "golden" / "g_red.jsonl"


def test_the_set_has_enough_attacks_and_benign_questions() -> None:
    items = generate_gred()
    kinds = Counter(item.kind for item in items)
    assert kinds["direct"] >= 30
    assert kinds["indirect"] >= 30
    assert kinds["advice"] >= 20
    assert sum(item.attack for item in items) >= 100
    assert kinds["benign"] >= 100
    assert len({item.id for item in items}) == len(items)
    assert len({item.question for item in items if item.kind == "direct"}) == kinds["direct"]


def test_generation_is_deterministic() -> None:
    assert generate_gred() == generate_gred()
    assert generate_gred(seed=1) != generate_gred(seed=2)


def test_every_indirect_attack_plants_its_marker_in_a_passage() -> None:
    for item in generate_gred():
        if item.kind == "indirect":
            assert item.passages, item.id
            assert item.goal is not None
            if item.goal == "marker":
                assert item.marker is not None
                assert any(item.marker in p for p in item.passages), item.id
        if item.kind == "direct" and item.goal == "marker":
            assert item.marker is not None
            assert item.marker in item.question, item.id
        if item.kind == "benign":
            assert item.goal is None


def test_some_benign_questions_read_clean_passages() -> None:
    """So a quarantine that flags ordinary filing text shows up as a false refusal."""
    benign = [item for item in generate_gred() if item.kind == "benign"]
    assert sum(bool(item.passages) for item in benign) >= 30


def test_the_committed_file_is_the_generated_set() -> None:
    assert read_jsonl(COMMITTED, RedItem) == generate_gred()
