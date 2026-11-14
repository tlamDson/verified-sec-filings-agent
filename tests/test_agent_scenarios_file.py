"""The committed A1 scenarios: 50, on the test companies only, every category covered."""

import json
from collections import Counter
from pathlib import Path

from sec_agent.eval.agent.scenarios import CATEGORIES, Transcript, read_scenarios
from sec_agent.eval.agent.tracing import scopes
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.golden.split import read_split
from sec_agent.tools.metrics import CONCEPT_NAMES
from sec_agent.tools.ratio_defs import GROWTH, RATIOS

SCENARIOS = Path("data") / "golden" / "agent_scenarios.jsonl"
TRANSCRIPTS = Path("results") / "agent" / "test"


def test_fifty_scenarios_with_unique_ids_cover_every_category(repo_root: Path) -> None:
    scenarios = read_scenarios(repo_root / SCENARIOS)
    assert len(scenarios) == 50
    assert len({s.id for s in scenarios}) == 50
    counts = Counter(s.category for s in scenarios)
    assert set(counts) == set(CATEGORIES)


def test_scenarios_name_only_test_companies(repo_root: Path) -> None:
    split = read_split(repo_root / "data" / "golden" / "company_split.json")
    test = {c.ticker for c in split.companies if c.split == "test"}
    for s in read_scenarios(repo_root / SCENARIOS):
        assert s.split == "test"
        assert set(s.companies) <= test, s.id
        for check in s.tools:
            for path, value in check.match.items():
                if path.endswith("ticker"):
                    assert value in test, s.id


def test_concepts_and_ratios_are_ones_the_tools_know(repo_root: Path) -> None:
    known = {*CONCEPT_NAMES, *RATIOS, GROWTH}
    for s in read_scenarios(repo_root / SCENARIOS):
        for check in s.tools:
            for path in ("concept", "ratio", "metric"):
                if path in check.match:
                    assert check.match[path] in known, s.id


def test_every_figure_check_names_the_oracle_call_that_answers_it(repo_root: Path) -> None:
    """A system without the tool (RAG) is judged against this call's figure."""
    for s in read_scenarios(repo_root / SCENARIOS):
        for check in s.tools:
            if check.figure is None:
                continue
            assert check.call is not None, s.id
            assert check.call["fiscal_year"] == check.match["fiscal_year"], s.id
            tickers = [v for k, v in check.match.items() if k.endswith("ticker")]
            named = check.call.get("company", check.call.get("companies"))
            assert all(t == named or (isinstance(named, list) and t in named) for t in tickers)


def test_every_growth_check_names_its_concept(repo_root: Path) -> None:
    """A growth result names its concept only in its formula: without it, the growth of
    net income would pass a revenue question."""
    for s in read_scenarios(repo_root / SCENARIOS):
        for check in s.tools:
            if check.match.get("ratio") != "yoy_growth":
                continue
            assert check.call is not None, s.id
            concept, year = check.call["concept"], check.match["fiscal_year"]
            assert isinstance(year, int), s.id
            assert check.match["formula"] == (
                f"({concept}[{year}] - {concept}[{year - 1}]) / |{concept}[{year - 1}]| * 100"
            ), s.id


def test_every_risk_diff_check_names_the_oracle_call_that_answers_it(repo_root: Path) -> None:
    """RAG has no diff tool: the oracle's diff names the two filings it must cite."""
    for s in read_scenarios(repo_root / SCENARIOS):
        for check in s.tools:
            if check.tool != "diff_risk_factors":
                continue
            assert check.call is not None, s.id
            assert check.call["company"] == check.match["company.ticker"], s.id
            for side, year in (("current", "fiscal_year"), ("previous", "compare_to")):
                if f"{side}.fiscal_year" in check.match:
                    assert check.call[year] == check.match[f"{side}.fiscal_year"], s.id


def test_the_fiscal_years_a_risk_diff_asks_for_are_checked(repo_root: Path) -> None:
    """a1-035 names fiscal 2023 and 2024: a diff of other years is not its answer."""
    by_id = {s.id: s for s in read_scenarios(repo_root / SCENARIOS)}
    match = by_id["a1-035"].tools[0].match
    assert (match["current.fiscal_year"], match["previous.fiscal_year"]) == (2024, 2023)


def test_every_recorded_oracle_run_of_a_checks_call_meets_the_check(repo_root: Path) -> None:
    """A check the pinned facts cannot meet fails every system alike. a1-021 once asked
    PM's fiscal 2023 effective tax rate: facts v1 has no pretax income, so the oracle said
    `not_reported` while the check required `computed`. Every committed oracle run of a
    check's own call (the same arguments) must be a result the check matches."""
    by_id = {s.id: s for s in read_scenarios(repo_root / SCENARIOS)}
    judged = 0
    for path in sorted((repo_root / TRANSCRIPTS).glob("*.jsonl")):
        if path.name.endswith(".cache.jsonl"):
            continue
        for t in read_jsonl(path, Transcript):
            for e in t.oracle:
                check = by_id[t.scenario_id].tools[int(e.call_id.removeprefix("oracle-"))]
                if check.call is None or json.loads(e.arguments) != check.call:
                    continue  # recorded for an earlier version of the check
                judged += 1
                assert scopes(check, e), f"{path.name} {t.scenario_id}: {e.result[:200]}"
    assert judged > 0


def test_every_risk_diff_oracle_asks_for_every_change(repo_root: Path) -> None:
    """RAG's claimed changes are matched to the oracle's paragraphs: it must hold them all."""
    for s in read_scenarios(repo_root / SCENARIOS):
        for check in s.tools:
            if check.tool == "diff_risk_factors":
                assert check.call is not None, s.id
                assert check.call["max_changes"] == 200, s.id
