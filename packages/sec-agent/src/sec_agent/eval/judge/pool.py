"""The G-judge pool: committed eval answers with their stratum from the code graders.

Numeric answers (N1 grading): correct; a wrong value, unit or company is a wrong number;
a wrong period is a wrong period. Unparsed, not-found and wrong-kind replies fit no
stratum and stay out. Agent transcripts (A1 checks): a passing scenario is correct; a
figure failure is a wrong number; a missing citation, an untraced figure or a text
outcome the cited passages do not support is a citation failure. Other failures (wrong
tool, status, phrasing) fit no stratum. Numeric records keep no tool evidence, so their
items show no sources.
"""

from collections.abc import Sequence

from sec_agent.eval.agent.checks import FailureKind, ScenarioResult, check_scenario
from sec_agent.eval.agent.scenarios import Scenario, Transcript
from sec_agent.eval.judge.models import Candidate, Source, Stratum
from sec_agent.eval.numeric.grade import Graded, grade
from sec_agent.eval.numeric.reply import parse_reply
from sec_agent.eval.numeric.runner import AnswerRecord
from sec_agent.golden.gnum.models import NumQuestion

_WRONG_NUMBER = frozenset({"wrong_value", "wrong_unit", "wrong_company"})
_FIGURE: frozenset[FailureKind] = frozenset({"figure", "oracle"})
_CITATION: frozenset[FailureKind] = frozenset({"citation", "unfaithful", "outcome"})


def numeric_stratum(graded: Graded) -> Stratum | None:
    if graded.correct:
        return "correct"
    if graded.error == "wrong_period":
        return "wrong_period"
    return "wrong_number" if graded.error in _WRONG_NUMBER else None


def agent_stratum(result: ScenarioResult) -> Stratum | None:
    if result.passed:
        return "correct"
    kinds = {f.kind for f in result.failures}
    if kinds & _FIGURE:
        return "wrong_number"
    return "citation" if kinds & _CITATION else None


def numeric_candidates(
    questions: Sequence[NumQuestion], records: Sequence[AnswerRecord]
) -> list[Candidate]:
    by_id = {q.id: q for q in questions}
    out: list[Candidate] = []
    for r in records:
        q = by_id.get(r.qid)
        if q is None:
            continue
        graded = grade(q, parse_reply(r.output))
        stratum = numeric_stratum(graded)
        if stratum is None:
            continue
        out.append(
            Candidate(
                origin="numeric",
                record_id=r.qid,
                system=r.system,
                model=r.model,
                stratum=stratum,
                grader_error=graded.error,
                turns=(q.question,),
                asked_on=None,
                answer=r.output,
                sources=(),
            )
        )
    return out


def agent_candidates(
    scenarios: Sequence[Scenario], transcripts: Sequence[Transcript]
) -> list[Candidate]:
    by_id = {s.id: s for s in scenarios}
    out: list[Candidate] = []
    for t in transcripts:
        scenario = by_id.get(t.scenario_id)
        if scenario is None:
            continue
        result = check_scenario(scenario, t)
        stratum = agent_stratum(result)
        if stratum is None:
            continue
        kinds = sorted({f.kind for f in result.failures})
        out.append(
            Candidate(
                origin="agent",
                record_id=t.scenario_id,
                system=t.system,
                model=t.model,
                stratum=stratum,
                grader_error=",".join(kinds) or None,
                turns=scenario.turns,
                asked_on=t.asked_on,
                answer=t.text,
                sources=tuple(
                    Source(tool=e.name, arguments=e.arguments, result=e.result) for e in t.evidence
                ),
            )
        )
    return out
