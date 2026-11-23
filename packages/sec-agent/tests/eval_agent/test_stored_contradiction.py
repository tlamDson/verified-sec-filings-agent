"""T-0004: A1 fails a stored transcript whose answer contradicts the passage it cites.

Each case keeps a real committed agent transcript (`results/agent/test/agent.jsonl`: its
evidence, oracle and real SEC passages) and replaces only the answer with one sentence
that cites a real passage and says the opposite of it. The same sentence agreeing with
the passage still passes, so the failure comes from the contradiction alone. The
replaced answers are written by the test; the passages are real filing text.
"""

from functools import cache
from pathlib import Path

import pytest

from sec_agent.eval.agent.checks import check_scenario
from sec_agent.eval.agent.scenarios import Scenario, Transcript, read_scenarios
from sec_agent.golden.jsonl import read_jsonl

ROOT = Path(__file__).resolve().parents[4]

# (scenario, contradicting answer, agreeing answer); every key is a passage the stored
# transcript retrieved for the scenario's search check.
CASES = (
    (
        "a1-033",
        "ConocoPhillips states that its operating results, ability to execute on its strategy, "
        "and the carrying value of its assets are not exposed to the effects of volatile "
        "commodity prices or prolonged periods of low commodity prices "
        "[0001163165-25-000012/risk_factors/0].",
        "ConocoPhillips states that its operating results, ability to execute on its strategy, "
        "and the carrying value of its assets are exposed to the effects of volatile "
        "commodity prices or prolonged periods of low commodity prices "
        "[0001163165-25-000012/risk_factors/0].",
    ),
    (
        "a1-033",
        "ConocoPhillips notes that its revenues, operating results, and future rate of growth "
        "are not dependent on the sales prices for crude oil, bitumen, LNG, natural gas, and "
        "NGLs [0001163165-25-000012/risk_factors/0].",
        "ConocoPhillips notes that its revenues, operating results, and future rate of growth "
        "are highly dependent on the sales prices for crude oil, bitumen, LNG, natural gas, "
        "and NGLs [0001163165-25-000012/risk_factors/0].",
    ),
    (
        "a1-030",
        "PMI states that its smoke-free products are not designed for, or directed toward, "
        "current adult smokers and adult users of nicotine-containing products "
        "[0001413329-25-000013/business/2].",
        "PMI states that its smoke-free products are designed for, and directed toward, "
        "current adult smokers and adult users of nicotine-containing products "
        "[0001413329-25-000013/business/2].",
    ),
    (
        "a1-031",
        "Visa is never required by its commercial agreements to indemnify other entities for "
        "litigation brought against them when Visa is not a defendant "
        "[0001403161-24-000058/risk_factors/16].",
        "Visa is required by its commercial agreements to indemnify other entities for "
        "litigation brought against them, even if Visa is not a defendant "
        "[0001403161-24-000058/risk_factors/16].",
    ),
)


@cache
def _scenarios() -> dict[str, Scenario]:
    path = ROOT / "data" / "golden" / "agent_scenarios.jsonl"
    return {s.id: s for s in read_scenarios(path) if s.split == "test"}


@cache
def _stored() -> dict[str, Transcript]:
    path = ROOT / "results" / "agent" / "test" / "agent.jsonl"
    return {t.scenario_id: t for t in read_jsonl(path, Transcript)}


def _kinds(scenario_id: str, text: str) -> list[str]:
    transcript = _stored()[scenario_id].model_copy(update={"text": text})
    return [f.kind for f in check_scenario(_scenarios()[scenario_id], transcript).failures]


@pytest.mark.parametrize("scenario_id", sorted({case[0] for case in CASES}))
def test_the_stored_answer_passes_a1(scenario_id: str) -> None:
    assert _kinds(scenario_id, _stored()[scenario_id].text) == []


@pytest.mark.parametrize(("scenario_id", "contradicting", "agreeing"), CASES)
def test_a_stored_transcript_citing_a_passage_that_contradicts_its_answer_fails_a1(
    scenario_id: str, contradicting: str, agreeing: str
) -> None:
    assert _kinds(scenario_id, agreeing) == []
    assert _kinds(scenario_id, contradicting) == ["outcome"]
