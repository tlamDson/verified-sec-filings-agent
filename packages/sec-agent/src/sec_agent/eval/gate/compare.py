"""Baseline against a fresh measurement.

When a family's inputs are the committed ones (same digest), the code is the only thing
that changed, so every number must come out exactly as before, in either direction: a
grader that turns lenient is as wrong as one that turns strict (`drift`). A deliberate
change of a grader refreshes the baseline (`eval gate --update`) in the same pull request.

When the inputs were re-generated (a night run), a number may move by chance: it may get
worse by at most its `max_drop` (`regression` beyond), and it must cover at least as many
items as before (`coverage`), so a short run never passes as a better one. Breakdowns
(`drift_only`, e.g. failures by kind) are watched only for drift.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from sec_agent.eval.gate.models import GateMetric, GateSnapshot

FindingKind = Literal["drift", "regression", "coverage", "missing"]
EXACT = 1e-9


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str
    kind: FindingKind
    message: str


def compare(baseline: GateSnapshot, current: GateSnapshot) -> list[Finding]:
    now = {m.name: m for m in current.metrics}
    findings: list[Finding] = []
    for base in baseline.metrics:
        cur = now.get(base.name)
        if cur is None:
            findings.append(Finding(metric=base.name, kind="missing", message="not measured"))
            continue
        same_inputs = baseline.inputs.get(base.family) == current.inputs.get(base.family)
        if finding := _check(base, cur, same_inputs=same_inputs):
            findings.append(finding)
    return findings


def _check(base: GateMetric, cur: GateMetric, *, same_inputs: bool) -> Finding | None:
    shown = f"{base.value:.3f} (n {base.n}) -> {cur.value:.3f} (n {cur.n})"
    if same_inputs:
        if cur.n != base.n or abs(cur.value - base.value) > EXACT:
            return Finding(metric=base.name, kind="drift", message=f"same inputs, {shown}")
        return None
    if base.drift_only:
        return None
    if cur.n < base.n:
        return Finding(metric=base.name, kind="coverage", message=f"fewer items, {shown}")
    worse = base.value - cur.value if base.higher_is_better else cur.value - base.value
    if worse > base.max_drop + EXACT:
        return Finding(
            metric=base.name,
            kind="regression",
            message=f"{shown}, worse by {worse:.3f} > {base.max_drop:.3f}",
        )
    return None
