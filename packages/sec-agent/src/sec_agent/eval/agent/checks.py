"""A1 for one transcript: every check of the scenario must pass (task success).

The shown text is traced again against the turn's evidence by the faithfulness checker
(s-10), the same code for the agent and the RAG baseline: "right figure" means a figure
traced to the expected tool field, and "faithful" means no figure is shown untraced.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sec_agent.agent.answer import Evidence
from sec_agent.eval.agent.scenarios import (
    Scenario,
    ToolCheck,
    Transcript,
    matching_elements,
    result_values,
)
from sec_agent.faithfulness.check import check_answer
from sec_agent.faithfulness.models import FaithfulnessReport

FailureKind = Literal["status", "tool", "figure", "citation", "unfaithful", "says", "not_says"]
_FROZEN = ConfigDict(frozen=True, extra="forbid")


class Failure(BaseModel):
    model_config = _FROZEN

    kind: FailureKind
    detail: str


class ScenarioResult(BaseModel):
    model_config = _FROZEN

    scenario_id: str
    passed: bool
    failures: tuple[Failure, ...]


def check_scenario(scenario: Scenario, transcript: Transcript) -> ScenarioResult:
    report = check_answer(transcript.text, transcript.evidence, asked_on=transcript.asked_on)
    failures: list[Failure] = []
    if transcript.status not in scenario.status:
        failures.append(Failure(kind="status", detail=transcript.status))
    for index, check in enumerate(scenario.tools):
        calls = {e.call_id: scopes for e in transcript.evidence if (scopes := _scopes(check, e))}
        if not calls:
            failures.append(Failure(kind="tool", detail=f"tools[{index}]"))
        elif check.figure is not None and not _figure_traced(check.figure, calls, report):
            failures.append(Failure(kind="figure", detail=f"tools[{index}]: {check.figure}"))
    if scenario.cite and not _cites(report):
        failures.append(Failure(kind="citation", detail="no valid citation"))
    if not report.faithful:
        failures.append(Failure(kind="unfaithful", detail=f"{report.traced}/{report.mentions}"))
    for pattern in scenario.says:
        if re.search(pattern, transcript.text, re.IGNORECASE) is None:
            failures.append(Failure(kind="says", detail=pattern))
    for pattern in scenario.not_says:
        if re.search(pattern, transcript.text, re.IGNORECASE) is not None:
            failures.append(Failure(kind="not_says", detail=pattern))
    return ScenarioResult(scenario_id=scenario.id, passed=not failures, failures=tuple(failures))


def _scopes(check: ToolCheck, evidence: Evidence) -> set[str]:
    """Where in this call's result a figure of the check may trace: {""} anywhere, or the
    list elements ("rows[1]") whose values match every `*` path; empty when the call does
    not match. A peer check on HD is thus met by HD's row, never by another company's."""
    if check.tool is not None and evidence.name != check.tool:
        return set()
    if evidence.ok != check.ok:
        return set()
    scopes = {""}
    for path, expected in check.match.items():
        if "*" in path:
            rows = matching_elements(evidence.result, path, expected)
            scopes = rows if scopes == {""} else scopes & rows
        elif expected not in result_values(evidence.result, path):
            return set()
        if not scopes:
            return set()
    return scopes


def _cites(report: FaithfulnessReport) -> bool:
    return any(c.status == "valid" for s in report.sentences for c in s.citations)


def _figure_traced(figure: str, calls: dict[str, set[str]], report: FaithfulnessReport) -> bool:
    pattern = re.compile(figure)
    return any(
        m.status == "traced"
        and m.source is not None
        and m.source.call_id in calls
        and pattern.fullmatch(m.source.field) is not None
        and _within(m.source.field, calls[m.source.call_id])
        for s in report.sentences
        for m in s.mentions
    )


def _within(field: str, scopes: set[str]) -> bool:
    return "" in scopes or any(field.startswith(f"{scope}.") for scope in scopes)
