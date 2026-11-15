"""A re-run of a measurement replaces the earlier row for the same key."""

from report_kit import run

from sec_agent.report.latest import latest_rows


def test_last_row_per_key_wins() -> None:
    old = run("N1", "b0", 0.1, sha="aaaaaaa")
    other = run("N1", "b1", 0.2)
    new = run("N1", "b0", 0.15, sha="bbbbbbb")
    assert latest_rows([old, other, new]) == [new, other]


def test_split_and_cohort_are_part_of_the_key() -> None:
    real = run("U1.x", "app", 1.0, cohort="real")
    sim = run("U1.x", "app", 2.0, cohort="simulated")
    dev = run("N1", "b0", 0.3, split="dev")
    test = run("N1", "b0", 0.4)
    assert latest_rows([real, sim, dev, test]) == [real, sim, dev, test]
