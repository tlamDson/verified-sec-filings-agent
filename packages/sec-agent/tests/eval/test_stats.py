"""Wilson interval, exact McNemar, and the paired bootstrap over companies."""

import pytest

from sec_agent.eval.stats.bootstrap import bootstrap_mean, paired_bootstrap
from sec_agent.eval.stats.mcnemar import mcnemar
from sec_agent.eval.stats.wilson import wilson_interval


@pytest.mark.parametrize(
    ("successes", "n", "low", "high"),
    [
        (240, 300, 0.751071, 0.841343),  # the plan's "about +-4.5 points at 80% on 300"
        (7, 10, 0.396778, 0.892209),
        (0, 10, 0.0, 0.277533),
        (10, 10, 0.722467, 1.0),
    ],
)
def test_wilson_matches_reference_values(successes: int, n: int, low: float, high: float) -> None:
    interval = wilson_interval(successes, n)
    assert interval.low == pytest.approx(low, abs=1e-6)
    assert interval.high == pytest.approx(high, abs=1e-6)


def test_wilson_bounds_are_exact_at_the_edges() -> None:
    assert wilson_interval(0, 5).low == 0.0
    assert wilson_interval(5, 5).high == 1.0


@pytest.mark.parametrize(("successes", "n"), [(0, 0), (-1, 5), (6, 5)])
def test_wilson_rejects_impossible_counts(successes: int, n: int) -> None:
    with pytest.raises(ValueError, match="successes"):
        wilson_interval(successes, n)


def test_mcnemar_counts_only_discordant_pairs() -> None:
    a = [True, True, False, False, True]
    b = [True, False, True, False, False]
    result = mcnemar(a, b)
    assert (result.n, result.a_only, result.b_only) == (5, 2, 1)


def test_mcnemar_exact_p_value() -> None:
    # 1 vs 9 discordant: p = 2 * (C(10,0) + C(10,1)) / 2**10
    a = [True] * 1 + [False] * 9 + [True] * 20
    b = [False] * 1 + [True] * 9 + [True] * 20
    assert mcnemar(a, b).p_value == pytest.approx(22 / 1024)


@pytest.mark.parametrize(("a_only", "b_only"), [(0, 0), (5, 5)])
def test_mcnemar_balanced_or_empty_is_p_one(a_only: int, b_only: int) -> None:
    a = [True] * a_only + [False] * b_only
    b = [False] * a_only + [True] * b_only
    assert mcnemar(a, b).p_value == 1.0


def test_mcnemar_needs_paired_outcomes() -> None:
    with pytest.raises(ValueError, match="paired"):
        mcnemar([True], [True, False])


CLUSTERS = {
    "AAA": [1.0, 0.0, 1.0],
    "BBB": [0.5, 0.5],
    "CCC": [0.0, 0.0, 0.0, 1.0],
    "DDD": [1.0],
}


def test_bootstrap_mean_is_the_mean_over_questions() -> None:
    result = bootstrap_mean(CLUSTERS, resamples=500, seed=1)
    assert result.estimate == pytest.approx(5.0 / 10)
    assert result.low <= result.estimate <= result.high
    assert (result.n, result.clusters, result.resamples) == (10, 4, 500)


def test_bootstrap_is_reproducible_by_seed() -> None:
    first = bootstrap_mean(CLUSTERS, resamples=300, seed=7)
    assert bootstrap_mean(CLUSTERS, resamples=300, seed=7) == first
    assert bootstrap_mean(CLUSTERS, resamples=300, seed=8) != first


def test_bootstrap_of_one_cluster_has_no_spread() -> None:
    result = bootstrap_mean({"AAA": [0.2, 0.4]}, resamples=100, seed=1)
    assert (result.low, result.estimate, result.high) == pytest.approx((0.3, 0.3, 0.3))


def test_bootstrap_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="no values"):
        bootstrap_mean({"AAA": []}, resamples=10, seed=1)


def test_paired_bootstrap_of_a_system_better_everywhere() -> None:
    a = {"AAA": [1.0, 1.0], "BBB": [1.0, 0.5], "CCC": [0.8]}
    b = {"AAA": [0.0, 0.5], "BBB": [0.5, 0.0], "CCC": [0.1]}
    result = paired_bootstrap(a, b, resamples=999, seed=3)
    assert result.estimate == pytest.approx((1.0 + 0.5 + 0.5 + 0.5 + 0.7) / 5)
    assert result.low > 0
    assert result.p_value == pytest.approx(2 / 1000)


def test_paired_bootstrap_of_identical_systems() -> None:
    result = paired_bootstrap(CLUSTERS, CLUSTERS, resamples=200, seed=3)
    assert (result.estimate, result.low, result.high, result.p_value) == (0.0, 0.0, 0.0, 1.0)


def test_paired_bootstrap_needs_the_same_questions() -> None:
    with pytest.raises(ValueError, match="paired"):
        paired_bootstrap({"AAA": [1.0]}, {"AAA": [1.0, 0.0]}, resamples=10, seed=1)
