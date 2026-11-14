"""The results block: every number is a formatted runs.csv value."""

from report_kit import run
from sec_agent.report.render import render_results


def test_fraction_shows_percent_interval_and_n() -> None:
    text = render_results([run("N1", "b2", 0.75, ci=(0.698, 0.796))])
    assert "75.0%" in text
    assert "69.8% to 79.6%" in text
    assert "300" in text


def test_p_value_difference_kappa_and_milliseconds() -> None:
    text = render_results(
        [
            run("N1_mcnemar_p", "b2_vs_b0", 1.3e-54, unit="p_value"),
            run("R1_ndcg@10_diff", "ft_vs_hybrid", 0.109, unit="difference", ci=(0.076, 0.144)),
            run("J1_kappa", "grader", 0.8724832, unit="kappa", n=38),
            run("L1_rerank_p50", "minilm", 961.839, unit="ms", n=200),
        ]
    )
    assert "p = 1.3e-54" in text
    assert "+0.109" in text
    assert "0.87" in text
    assert "962 ms" in text


def test_sections_are_grouped_by_metric_family_in_fixed_order() -> None:
    text = render_results([run("S1_attack_block", "g", 0.9), run("R1_mrr@10", "h", 0.5)])
    assert text.index("R1") < text.index("S1")


def test_superseded_rows_are_not_shown() -> None:
    text = render_results([run("N1", "b0", 0.0), run("N1", "b0", 0.15)])
    assert "15.0%" in text
    assert "| 0.0%" not in text


def test_simulated_cohort_is_labelled_and_kept_apart() -> None:
    text = render_results(
        [
            run("U1.sessions", "app", 120, unit="count", cohort="simulated", n=50),
            run("U1.sessions", "app", 3, unit="count", cohort="real", n=2),
        ]
    )
    assert "simulated" in text.lower()
    assert "real" in text
    assert "120" in text
    assert "3 " in text


def test_missing_families_are_listed_as_not_measured() -> None:
    text = render_results([run("N1", "b0", 0.15)])
    assert "Not measured yet" in text
    for family in ("LOAD", "CHAOS", "U1"):
        assert family in text.split("Not measured yet", 1)[1]


def test_group_with_caveat_for_llm_raters() -> None:
    text = render_results([run("J1_kappa", "grader", 1.0, unit="kappa", n=38)])
    assert "LLM raters" in text
