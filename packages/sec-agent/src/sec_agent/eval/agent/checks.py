"""A1 for one transcript: every check of the scenario must pass (task success).

The shown text is traced again against the turn's evidence by the faithfulness checker
(s-10), the same code for the agent and the RAG baseline: "right figure" means a figure
traced to the expected tool field, and "faithful" means no figure is shown untraced. A
check of a tool the system does not offer is judged on its outcome (`tracing`): the
oracle's figure stated from a cited passage, or, without a figure, the other checks alone.
`oracle` fails a figure check whose oracle call is missing from the transcript.
"""

import re
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict

from sec_agent.eval.agent.scenarios import Scenario, ToolCheck, Transcript
from sec_agent.eval.agent.tracing import (
    figure_starts,
    matching_calls,
    offers,
    oracle_figure_cited,
)
from sec_agent.faithfulness.check import check_answer
from sec_agent.faithfulness.models import FaithfulnessReport

FailureKind = Literal[
    "status", "tool", "figure", "oracle", "citation", "unfaithful", "says", "not_says"
]
FAILURE_KINDS: tuple[FailureKind, ...] = get_args(FailureKind)
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
        failure = _tool_failure(check, transcript, report)
        if failure is not None:
            failures.append(Failure(kind=failure, detail=f"tools[{index}]"))
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


def _tool_failure(
    check: ToolCheck, transcript: Transcript, report: FaithfulnessReport
) -> FailureKind | None:
    if not offers(check, transcript.offered_tools):
        if check.figure is None:
            return None  # the scenario's other checks judge the outcome
        cited = oracle_figure_cited(
            check, transcript.text, transcript.oracle, report, transcript.asked_on
        )
        return "oracle" if cited is None else (None if cited else "figure")
    calls = matching_calls(check, transcript.evidence)
    if not calls:
        return "tool"
    if check.figure is not None and not figure_starts(check.figure, calls, report):
        return "figure"
    return None


def _cites(report: FaithfulnessReport) -> bool:
    return any(c.status == "valid" for s in report.sentences for c in s.citations)
