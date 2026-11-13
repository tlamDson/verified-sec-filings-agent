"""The N1 report: accuracy per system with a Wilson interval, errors by kind and by question
type, and an exact McNemar test for every pair of systems.

Systems are compared on the same questions: those of the set every system has an answer
for (the latest record of a question counts). How many each system lacks is reported, so
a short run shows as a smaller N, never as a better accuracy.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import combinations

from pydantic import BaseModel, ConfigDict

from sec_agent.eval.numeric.grade import ErrorKind, Graded, grade
from sec_agent.eval.numeric.reply import parse_reply
from sec_agent.eval.numeric.runner import AnswerRecord
from sec_agent.eval.stats.mcnemar import McNemarResult, mcnemar
from sec_agent.eval.stats.wilson import Interval, wilson_interval
from sec_agent.golden.gnum.models import NumQuestion, QuestionType

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class SystemAccuracy(BaseModel):
    model_config = _FROZEN

    system: str
    models: tuple[str, ...]
    n: int
    correct: int
    accuracy: float
    interval: Interval
    errors: dict[ErrorKind, int]
    by_qtype: dict[QuestionType, tuple[int, int]]
    """Question type -> (correct, n)."""


class NumericComparison(BaseModel):
    model_config = _FROZEN

    system: str
    other: str
    result: McNemarResult
    """`a_only`: questions only `system` got right; `b_only`: only `other`."""


class NumericReport(BaseModel):
    model_config = _FROZEN

    questions: int
    scored: int
    missing: dict[str, int]
    index_version: str
    systems: tuple[SystemAccuracy, ...]
    comparisons: tuple[NumericComparison, ...]


def numeric_report(
    questions: Sequence[NumQuestion], records: Mapping[str, Sequence[AnswerRecord]]
) -> NumericReport:
    """`records`: system -> its answer records, systems in the order to report them."""
    by_id = {q.id: q for q in questions}
    latest = {system: _latest(system, rs, by_id) for system, rs in records.items()}
    answered = set(by_id)
    for answers in latest.values():
        answered &= set(answers)
    scored = [q for q in questions if q.id in answered]
    if not scored:
        raise ValueError("no question has an answer from every system: nothing to score")
    versions = {q.index_version for q in scored}
    if len(versions) != 1:
        raise ValueError(f"questions come from several index versions: {sorted(versions)}")
    graded = {
        system: [grade(q, parse_reply(answers[q.id].output)) for q in scored]
        for system, answers in latest.items()
    }
    systems = tuple(_accuracy(system, scored, graded[system], latest[system]) for system in latest)
    comparisons = tuple(
        NumericComparison(
            system=later,
            other=earlier,
            result=mcnemar(
                [g.correct for g in graded[later]], [g.correct for g in graded[earlier]]
            ),
        )
        for earlier, later in combinations(latest, 2)
    )
    return NumericReport(
        questions=len(questions),
        scored=len(scored),
        missing={system: len(set(by_id) - set(answers)) for system, answers in latest.items()},
        index_version=versions.pop(),
        systems=systems,
        comparisons=comparisons,
    )


def _latest(
    system: str, records: Sequence[AnswerRecord], questions: Mapping[str, NumQuestion]
) -> dict[str, AnswerRecord]:
    out: dict[str, AnswerRecord] = {}
    for record in sorted(records, key=lambda r: r.answered_at):
        if record.system != system:
            raise ValueError(f"results of {system} hold an answer of {record.system}")
        if record.qid in questions:
            out[record.qid] = record
    return out


def _accuracy(
    system: str,
    scored: Sequence[NumQuestion],
    graded: Sequence[Graded],
    answers: Mapping[str, AnswerRecord],
) -> SystemAccuracy:
    correct = sum(g.correct for g in graded)
    by_type: dict[QuestionType, tuple[int, int]] = {}
    for q, g in zip(scored, graded, strict=True):
        right, n = by_type.get(q.qtype, (0, 0))
        by_type[q.qtype] = (right + g.correct, n + 1)
    errors: Counter[ErrorKind] = Counter(g.error for g in graded if g.error is not None)
    return SystemAccuracy(
        system=system,
        models=tuple(sorted({answers[q.id].model for q in scored})),
        n=len(scored),
        correct=correct,
        accuracy=correct / len(scored),
        interval=wilson_interval(correct, len(scored)),
        errors=dict(errors),
        by_qtype=by_type,
    )
