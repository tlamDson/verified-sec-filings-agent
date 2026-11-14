"""J1: how far a judge's verdicts agree with the blind labels.

Positive means "correct". TPR is the share of answers labelled correct that the judge
calls correct; TNR the share labelled incorrect that it calls incorrect; both carry a
Wilson 95% interval. Cohen's kappa is (p_o - p_e) / (1 - p_e), undefined when p_e = 1
(both sides give one value only). `unsure` labels and items without a verdict are
counted, never scored. The code grader is scored the same way from the key ("grader").
"""

from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from sec_agent.eval.judge.models import KeyEntry, Label, Verdict, VerdictValue
from sec_agent.eval.stats.wilson import Interval, wilson_interval

GRADER = "grader"
Pair = tuple[VerdictValue, VerdictValue]
"""(label, verdict) for one item."""


class JudgeScore(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    judge: str
    n: int
    positives: int
    negatives: int
    agreement: float | None
    kappa: float | None
    tpr: float | None
    tpr_interval: Interval | None
    tnr: float | None
    tnr_interval: Interval | None
    unsure: int
    missing: int


def cohen_kappa(pairs: Sequence[Pair]) -> float | None:
    n = len(pairs)
    if n == 0:
        return None
    observed = sum(label == verdict for label, verdict in pairs) / n
    label_yes = sum(label == "correct" for label, _ in pairs) / n
    verdict_yes = sum(verdict == "correct" for _, verdict in pairs) / n
    expected = label_yes * verdict_yes + (1 - label_yes) * (1 - verdict_yes)
    if expected >= 1:
        return None
    return (observed - expected) / (1 - expected)


def grader_verdicts(key: Sequence[KeyEntry]) -> list[Verdict]:
    return [Verdict(id=k.id, verdict=k.grader_verdict, judge=GRADER) for k in key]


def score_judge(labels: Sequence[Label], verdicts: Sequence[Verdict], *, judge: str) -> JudgeScore:
    by_label = _unique({lb.id: lb for lb in labels}, [lb.id for lb in labels], "label")
    by_verdict = _unique({v.id: v for v in verdicts}, [v.id for v in verdicts], "verdict")
    if others := sorted({v.judge for v in verdicts} - {judge}):
        raise ValueError(f"verdicts of {judge} hold verdicts of {', '.join(others)}")
    if unknown := sorted(set(by_verdict) - set(by_label)):
        raise ValueError(f"verdicts for unlabelled items: {', '.join(unknown[:5])}")
    pairs: list[Pair] = []
    unsure = missing = 0
    for item_id, label in by_label.items():
        if label.label == "unsure":
            unsure += 1
        elif (verdict := by_verdict.get(item_id)) is None:
            missing += 1
        else:
            pairs.append((label.label, verdict.verdict))
    tp = sum(pair == ("correct", "correct") for pair in pairs)
    tn = sum(pair == ("incorrect", "incorrect") for pair in pairs)
    positives = sum(label == "correct" for label, _ in pairs)
    negatives = len(pairs) - positives
    return JudgeScore(
        judge=judge,
        n=len(pairs),
        positives=positives,
        negatives=negatives,
        agreement=(tp + tn) / len(pairs) if pairs else None,
        kappa=cohen_kappa(pairs),
        tpr=tp / positives if positives else None,
        tpr_interval=wilson_interval(tp, positives) if positives else None,
        tnr=tn / negatives if negatives else None,
        tnr_interval=wilson_interval(tn, negatives) if negatives else None,
        unsure=unsure,
        missing=missing,
    )


def _unique[T](rows: dict[str, T], ids: Sequence[str], what: str) -> dict[str, T]:
    if len(rows) != len(ids):
        twice = sorted(i for i, count in Counter(ids).items() if count > 1)
        raise ValueError(f"two {what}s for {', '.join(twice[:5])}")
    return rows
