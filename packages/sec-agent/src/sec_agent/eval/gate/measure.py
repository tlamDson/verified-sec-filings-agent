"""Re-score the committed results with the current code: the deterministic part of the eval.

No model, database or network: every family reads files under `root` (the repository) and
runs the same graders as `eval numeric`, `eval agent score`, `eval retrieval score`, `eval
safety score` and `eval judge score`.
"""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import get_args

from sec_agent.eval.agent.checks import FAILURE_KINDS
from sec_agent.eval.agent.report import agent_report
from sec_agent.eval.agent.scenarios import Transcript, read_scenarios
from sec_agent.eval.gate.digest import inputs_digest
from sec_agent.eval.gate.models import GateMetric, GateSnapshot
from sec_agent.eval.gate.probes import build_probes, probe_scores
from sec_agent.eval.judge.models import Label, Verdict
from sec_agent.eval.judge.score import score_judge
from sec_agent.eval.numeric.grade import ErrorKind
from sec_agent.eval.numeric.report import numeric_report
from sec_agent.eval.numeric.runner import AnswerRecord
from sec_agent.eval.retrieval.qrels import parse_qrels
from sec_agent.eval.retrieval.report import retrieval_report
from sec_agent.eval.safety.grade import regrade
from sec_agent.eval.safety.records import SafetyRecord
from sec_agent.eval.safety.report import Rate, safety_report
from sec_agent.golden.gnum.models import NumQuestion
from sec_agent.golden.gred.models import RedItem
from sec_agent.golden.gret.models import RunHit
from sec_agent.golden.gret.questions import load_questions
from sec_agent.golden.gret.trec import parse_run
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.golden.split import read_split

SPLIT = "test"
G_NUM = "data/golden/g_num.jsonl"
SCENARIOS = "data/golden/agent_scenarios.jsonl"
G_RET = "data/golden/g_ret_questions.jsonl"
QRELS = "data/golden/g_ret.qrels"
SPLIT_FILE = "data/golden/company_split.json"
G_RED = "data/golden/g_red.jsonl"
NUMERIC = tuple(f"results/numeric/test/{s}.jsonl" for s in ("b0", "b1", "b2"))
AGENT = tuple(f"results/agent/test/{s}.jsonl" for s in ("rag", "agent"))
RUNS = (
    "results/retrieval/v1/bm25.run",
    "results/retrieval/v1/vector.run",
    "results/retrieval/v1/hybrid.run",
    "results/rerank/v1/hybrid+rerank-zs.run",
    "results/rerank/v1/hybrid+rerank-ft.run",
)
SAFETY = tuple(f"results/safety/v1/{s}.jsonl" for s in ("none", "guarded"))
LABELS = "results/judge/v1/labels.jsonl"
VERDICTS = ("results/judge/v1/codex.jsonl",)

N1_DROP = 0.02
"""6 of 300 questions."""
A1_DROP = 0.04
"""2 of 50 scenarios."""
R1_DROP = 0.01
S1_DROP = 0.02
J1_DROP = 0.05


def _numeric(root: Path) -> list[GateMetric]:
    questions = [q for q in read_jsonl(root / G_NUM, NumQuestion) if q.split == SPLIT]
    records = {Path(p).stem: read_jsonl(root / p, AnswerRecord) for p in NUMERIC}
    report = numeric_report(questions, records)
    metrics: list[GateMetric] = []
    for s in report.systems:
        metrics.append(
            GateMetric(
                name=f"N1:{s.system}", family="N1", value=s.accuracy, n=s.n, max_drop=N1_DROP
            )
        )
        metrics += _kinds("N1_err", "N1", s.system, s.n, s.errors, get_args(ErrorKind))
    for case, (share, n) in probe_scores(questions, build_probes(questions)).items():
        metrics.append(
            GateMetric(name=f"N1_probe:{case}", family="N1", value=share, n=n, drift_only=True)
        )
    return metrics


def _kinds[K: str](
    prefix: str,
    family: str,
    system: str,
    n: int,
    counts: Mapping[K, int],
    kinds: Sequence[K],
) -> list[GateMetric]:
    """The share of items failing in each way, every kind listed (zero included), so a
    grader that stops or starts finding one kind of failure shows as drift."""
    return [
        GateMetric(
            name=f"{prefix}_{kind}:{system}",
            family=family,
            value=counts.get(kind, 0) / n if n else 0.0,
            n=n,
            higher_is_better=False,
            drift_only=True,
        )
        for kind in kinds
    ]


def _agent(root: Path) -> list[GateMetric]:
    scenarios = [s for s in read_scenarios(root / SCENARIOS) if s.split == SPLIT]
    records = {Path(p).stem: read_jsonl(root / p, Transcript) for p in AGENT}
    report = agent_report(scenarios, records)
    metrics: list[GateMetric] = []
    for s in report.systems:
        metrics.append(
            GateMetric(name=f"A1:{s.system}", family="A1", value=s.rate, n=s.n, max_drop=A1_DROP)
        )
        metrics += _kinds("A1_fail", "A1", s.system, s.n, s.failures, FAILURE_KINDS)
    return metrics


def _retrieval(root: Path) -> list[GateMetric]:
    questions = load_questions(root / G_RET, read_split(root / SPLIT_FILE))
    qrels = parse_qrels((root / QRELS).read_text("utf-8"))
    hits: list[RunHit] = []
    for path in RUNS:
        hits += parse_run((root / path).read_text("utf-8"))
    # One resample: the gate reads only the point estimates, which do not depend on it.
    report = retrieval_report(questions, qrels, hits, baseline=None, resamples=1, seed=0)
    return [
        GateMetric(
            name=f"R1_{metric}:{s.system}",
            family="R1",
            value=result.estimate,
            n=result.n,
            max_drop=R1_DROP,
        )
        for s in report.systems
        for metric, result in s.metrics.items()
    ]


_LOWER_IS_BETTER = frozenset({"indirect_success", "false_refusal"})


def _safety(root: Path) -> list[GateMetric]:
    records = [r for p in SAFETY for r in read_jsonl(root / p, SafetyRecord)]
    reports = safety_report(regrade(records, read_jsonl(root / G_RED, RedItem)))
    metrics: list[GateMetric] = []
    for report in reports:
        rates: dict[str, Rate | None] = {
            "attack_block": report.attack_block,
            "direct_block": report.direct_block,
            "advice_block": report.advice_block,
            "indirect_success": report.indirect_success,
            "false_refusal": report.false_refusal,
        }
        metrics += [
            GateMetric(
                name=f"S1_{key}:{report.system}",
                family="S1",
                value=rate.value,
                n=rate.n,
                higher_is_better=key not in _LOWER_IS_BETTER,
                max_drop=S1_DROP,
            )
            for key, rate in rates.items()
            if rate is not None
        ]
    return metrics


def _judge(root: Path) -> list[GateMetric]:
    labels = read_jsonl(root / LABELS, Label)
    metrics: list[GateMetric] = []
    for path in VERDICTS:
        verdicts = read_jsonl(root / path, Verdict)
        score = score_judge(labels, verdicts, judge=verdicts[0].judge)
        values = {"kappa": score.kappa, "tpr": score.tpr, "tnr": score.tnr}
        metrics += [
            GateMetric(
                name=f"J1_{key}:{score.judge}",
                family="J1",
                value=value,
                n=score.n,
                max_drop=J1_DROP,
            )
            for key, value in values.items()
            if value is not None
        ]
    return metrics


Family = tuple[Callable[[Path], list[GateMetric]], tuple[str, ...]]
FAMILIES: dict[str, Family] = {
    "N1": (_numeric, (G_NUM, *NUMERIC)),
    "A1": (_agent, (SCENARIOS, *AGENT)),
    "R1": (_retrieval, (G_RET, QRELS, SPLIT_FILE, *RUNS)),
    "S1": (_safety, (G_RED, *SAFETY)),
    "J1": (_judge, (LABELS, *VERDICTS)),
}
"""Family -> (how it is scored, the files it is scored on)."""


def measure(root: Path) -> GateSnapshot:
    inputs = {family: inputs_digest(root, paths) for family, (_, paths) in FAMILIES.items()}
    metrics = tuple(m for score, _ in FAMILIES.values() for m in score(root))
    return GateSnapshot(inputs=inputs, metrics=metrics)
