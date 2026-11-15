"""Seeded ranking: stable across runs and Python versions, independent per key."""

from sec_agent.golden.ranking import round_robin, seeded_key


def test_seeded_key_is_a_fixed_sha256_of_seed_and_parts() -> None:
    # sha256 of the compact JSON array [7,"a","1"] (parts as strings): pinned so a
    # change of the hashing scheme (which would reshuffle every split) fails loudly.
    assert (
        seeded_key(7, "a", 1) == "65dd50c66877d6d11e48a1c35e0899398702fcf1d3a0d4bfa7a0cbcee32697dc"
    )


def test_seeded_key_depends_on_seed_and_every_part() -> None:
    base = seeded_key(7, "a", 1)
    assert seeded_key(7, "a", 1) == base
    assert seeded_key(8, "a", 1) != base
    assert seeded_key(7, "b", 1) != base
    assert seeded_key(7, "a", 2) != base
    assert seeded_key(7, "a|1") != base  # parts are separated, not concatenated


def test_round_robin_takes_one_from_each_group_in_turn() -> None:
    assert round_robin([["a1", "a2", "a3"], ["b1"], [], ["c1", "c2"]]) == [
        "a1",
        "b1",
        "c1",
        "a2",
        "c2",
        "a3",
    ]
