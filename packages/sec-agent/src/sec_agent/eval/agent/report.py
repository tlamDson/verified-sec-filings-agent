"""The A1 report: task success per system with a Wilson interval, failures by check and by
category, and an exact McNemar test for every pair of systems.

As in N1, systems are compared on the scenarios every one of them has a transcript for, and
each system's missing count is reported. A results file with two transcripts of one
scenario, or transcripts from two models, is refused.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import combinations

from pydantic import BaseModel, ConfigDict

from sec_agent.eval.agent.checks import FailureKind, ScenarioResult, check_scenario
from sec_agent.eval.agent.scenarios import Category, Scenario, Transcript
from sec_agent.eval.numeric.report import NumericComparison
from sec_agent.eval.stats.mcnemar import mcnemar
from sec_agent.eval.stats.wilson import Interval, wilson_interval

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class SystemSuccess(BaseModel):
    model_config = _FROZEN

    system: str
    models: tuple[str, ...]
    n: int
    passed: int
    rate: float
    interval: Interval
    failures: dict[FailureKind, int]
    """Scenarios failing each kind of check (a scenario may fail several)."""
    by_category: dict[Category, tuple[int, int]]
    """Category -> (passed, n)."""
    results: tuple[ScenarioResult, ...]


class AgentReport(BaseModel):
    model_config = _FROZEN

    scenarios: int
    scored: int
    missing: dict[str, int]
    systems: tuple[SystemSuccess, ...]
    comparisons: tuple[NumericComparison, ...]
    """`result.a_only`: scenarios only `system` passed; `b_only`: only `other`."""


def agent_report(
    scenarios: Sequence[Scenario], records: Mapping[str, Sequence[Transcript]]
) -> AgentReport:
    """`records`: system -> its transcripts, systems in the order to report them."""
    by_id = {s.id: s for s in scenarios}
    latest = {system: _transcripts(system, ts, by_id) for system, ts in records.items()}
    answered = set(by_id)
    for transcripts in latest.values():
        answered &= set(transcripts)
    scored = [s for s in scenarios if s.id in answered]
    if not scored:
        raise ValueError("no scenario has a transcript from every system: nothing to score")
    results = {
        system: [check_scenario(s, transcripts[s.id]) for s in scored]
        for system, transcripts in latest.items()
    }
    return AgentReport(
        scenarios=len(scenarios),
        scored=len(scored),
        missing={system: len(set(by_id) - set(ts)) for system, ts in latest.items()},
        systems=tuple(
            _success(system, scored, results[system], latest[system]) for system in latest
        ),
        comparisons=tuple(
            NumericComparison(
                system=later,
                other=earlier,
                result=mcnemar(
                    [r.passed for r in results[later]], [r.passed for r in results[earlier]]
                ),
            )
            for earlier, later in combinations(latest, 2)
        ),
    )


def _transcripts(
    system: str, records: Sequence[Transcript], scenarios: Mapping[str, Scenario]
) -> dict[str, Transcript]:
    out: dict[str, Transcript] = {}
    for record in records:
        if record.system != system:
            raise ValueError(f"results of {system} hold a transcript of {record.system}")
        if record.scenario_id not in scenarios:
            continue
        if record.scenario_id in out:
            raise ValueError(
                f"results of {system} hold two answers to {record.scenario_id}; rerun the system"
            )
        out[record.scenario_id] = record
    models = sorted({t.model for t in out.values()})
    if len(models) > 1:
        raise ValueError(f"results of {system} mix models {models}; rerun with one model")
    return out


def _success(
    system: str,
    scored: Sequence[Scenario],
    results: Sequence[ScenarioResult],
    transcripts: Mapping[str, Transcript],
) -> SystemSuccess:
    passed = sum(r.passed for r in results)
    by_category: dict[Category, tuple[int, int]] = {}
    for scenario, result in zip(scored, results, strict=True):
        right, n = by_category.get(scenario.category, (0, 0))
        by_category[scenario.category] = (right + result.passed, n + 1)
    failures: Counter[FailureKind] = Counter()
    for r in results:
        kinds: set[FailureKind] = {f.kind for f in r.failures}
        failures.update(kinds)
    return SystemSuccess(
        system=system,
        models=tuple(sorted({transcripts[s.id].model for s in scored})),
        n=len(scored),
        passed=passed,
        rate=passed / len(scored),
        interval=wilson_interval(passed, len(scored)),
        failures=dict(failures),
        by_category=by_category,
        results=tuple(results),
    )
