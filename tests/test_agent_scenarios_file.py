"""The committed A1 scenarios: 50, on the test companies only, every category covered."""

from collections import Counter
from pathlib import Path

from sec_agent.eval.agent.scenarios import CATEGORIES, read_scenarios
from sec_agent.golden.split import read_split
from sec_agent.tools.metrics import CONCEPT_NAMES
from sec_agent.tools.ratio_defs import GROWTH, RATIOS

SCENARIOS = Path("data") / "golden" / "agent_scenarios.jsonl"


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
