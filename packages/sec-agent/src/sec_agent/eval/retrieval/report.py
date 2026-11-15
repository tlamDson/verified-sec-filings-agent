"""The R1 report: each system's mean metrics with company-bootstrap intervals, and paired
differences against a baseline system.

Scored questions are those with at least one relevant judged chunk, the same set for every
system; a question a run has no hits for scores 0 there. Every bootstrap uses the same seed,
so all systems and comparisons see the same company resamples.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from sec_agent.eval.retrieval.metrics import METRICS, query_scores
from sec_agent.eval.retrieval.rankers import ORACLE, oracle_ranking
from sec_agent.eval.stats.bootstrap import (
    BootstrapResult,
    PairedResult,
    bootstrap_mean,
    paired_bootstrap,
)
from sec_agent.golden.gret.models import RetQuestion, RunHit

_FROZEN = ConfigDict(frozen=True, extra="forbid")
ORACLE_DEPTH = 10
Judgements = Mapping[str, Mapping[str, int]]
"""qid -> docid -> grade, as `qrels.parse_qrels` reads them."""


class SystemRetrieval(BaseModel):
    model_config = _FROZEN

    system: str
    metrics: dict[str, BootstrapResult]


class RetrievalComparison(BaseModel):
    model_config = _FROZEN

    system: str
    baseline: str
    metric: str
    result: PairedResult
    """Mean of system minus baseline."""


class RetrievalReport(BaseModel):
    model_config = _FROZEN

    questions: int
    scored: int
    unscored: tuple[str, ...]
    """Questions with no relevant judged chunk (or none judged): left out of every mean."""
    companies: int
    resamples: int
    seed: int
    systems: tuple[SystemRetrieval, ...]
    comparisons: tuple[RetrievalComparison, ...]


def rankings(hits: Sequence[RunHit]) -> dict[str, dict[str, list[str]]]:
    """system -> qid -> docids by rank (ties by docid)."""
    grouped: defaultdict[str, defaultdict[str, list[RunHit]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for hit in hits:
        grouped[hit.system][hit.qid].append(hit)
    return {
        system: {
            qid: [h.chunk.docid for h in sorted(qh, key=lambda h: (h.rank, h.chunk.docid))]
            for qid, qh in by_qid.items()
        }
        for system, by_qid in grouped.items()
    }


def retrieval_report(
    questions: Sequence[RetQuestion],
    qrels: Judgements,
    hits: Sequence[RunHit],
    *,
    baseline: str | None,
    resamples: int,
    seed: int,
    oracle: bool = False,
) -> RetrievalReport:
    known = {q.id for q in questions}
    for source, qids in (("runs have hits", {h.qid for h in hits}), ("qrels have", set(qrels))):
        if unknown := sorted(qids - known):
            raise ValueError(f"{source} for questions not in the questions file: {unknown}")
    runs = rankings(hits)
    if oracle:
        runs[ORACLE] = {
            qid: oracle_ranking(judged, depth=ORACLE_DEPTH) for qid, judged in qrels.items()
        }
    if baseline is not None and baseline not in runs:
        raise ValueError(f"baseline {baseline!r} has no run; systems: {sorted(runs)}")
    scored = [q for q in questions if query_scores([], qrels.get(q.id, {})) is not None]
    if not scored:
        raise ValueError("no question has a relevant chunk in the qrels: nothing to score")
    order = sorted(s for s in runs if s != ORACLE) + ([ORACLE] if oracle else [])
    per_question = {s: _per_question(scored, qrels, runs[s]) for s in order}
    systems = tuple(
        SystemRetrieval(
            system=s,
            metrics={
                m: bootstrap_mean(per_question[s][m], resamples=resamples, seed=seed)
                for m in METRICS
            },
        )
        for s in order
    )
    comparisons = tuple(
        RetrievalComparison(
            system=s,
            baseline=baseline,
            metric=m,
            result=paired_bootstrap(
                per_question[s][m], per_question[baseline][m], resamples=resamples, seed=seed
            ),
        )
        for s in order
        if baseline is not None and s != baseline
        for m in METRICS
    )
    return RetrievalReport(
        questions=len(questions),
        scored=len(scored),
        unscored=tuple(q.id for q in questions if q not in scored),
        companies=len({q.ticker for q in scored}),
        resamples=resamples,
        seed=seed,
        systems=systems,
        comparisons=comparisons,
    )


def _per_question(
    scored: Sequence[RetQuestion], qrels: Judgements, run: Mapping[str, list[str]]
) -> dict[str, dict[str, list[float]]]:
    """metric -> company ticker -> one value per scored question, in question order."""
    out: dict[str, dict[str, list[float]]] = {m: defaultdict(list) for m in METRICS}
    for q in scored:
        values = query_scores(run.get(q.id, []), qrels[q.id])
        assert values is not None
        for metric in METRICS:
            out[metric][q.ticker].append(values[metric])
    return out
