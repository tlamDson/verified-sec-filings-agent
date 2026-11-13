"""Pick G-num questions: a per-split quota, shared equally by the five question types.

Per split and type, every candidate is built from that split's companies only (peers: two
companies of one split and one sector). Candidates are grouped by company (peers: by pair);
each group is put in a seeded order, the groups in a seeded order, and the quota is taken
one group at a time in turn, so no company dominates a stratum. A stratum with fewer
candidates than its quota keeps them all and reports the shortfall; quotas never move to
another type, so the strata stay comparable.
"""

from collections import defaultdict
from collections.abc import Sequence
from itertools import combinations

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.golden.gnum.candidates import GNumCompany, growth_questions, value_questions
from sec_agent.golden.gnum.models import NumQuestion, QuestionType
from sec_agent.golden.gnum.peers import peer_questions
from sec_agent.golden.gnum.ratios import ratio_questions
from sec_agent.golden.ranking import round_robin, seeded_key
from sec_agent.golden.split import CompanySplitName

QUESTION_TYPES: tuple[QuestionType, ...] = (
    "value",
    "yoy_growth",
    "ratio",
    "peer_comparison",
    "fiscal_period",
)
SPLITS: tuple[CompanySplitName, ...] = ("train", "dev", "test")
GNUM_SEED = 20261114


class GNumConfig(BaseModel):
    """Defaults follow the plan: FY2020-FY2024, 1,500 questions, 300 of them on test."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int = GNUM_SEED
    years: tuple[int, ...] = (2020, 2021, 2022, 2023, 2024)
    totals: dict[CompanySplitName, int] = Field(
        default_factory=lambda: {"train": 900, "dev": 300, "test": 300}
    )


class StratumReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    split: CompanySplitName
    qtype: QuestionType
    candidates: int
    quota: int
    selected: int

    @property
    def shortfall(self) -> int:
        return self.quota - self.selected


class GNumResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    questions: tuple[NumQuestion, ...]
    report: tuple[StratumReport, ...]
    companies_without_facts: tuple[str, ...]


def quotas(total: int) -> dict[QuestionType, int]:
    """`total` shared equally; the remainder goes one each to the first types."""
    base, extra = divmod(total, len(QUESTION_TYPES))
    return {t: base + (1 if i < extra else 0) for i, t in enumerate(QUESTION_TYPES)}


def candidates(
    companies: Sequence[GNumCompany], *, years: Sequence[int], index_version: str, seed: int
) -> dict[QuestionType, list[NumQuestion]]:
    """Every question the companies of one split can ask, by type."""
    out: dict[QuestionType, list[NumQuestion]] = {t: [] for t in QUESTION_TYPES}
    for c in companies:
        for q in value_questions(c, years=years, index_version=index_version):
            out[q.qtype].append(q)
        out["yoy_growth"] += growth_questions(c, years=years, index_version=index_version)
        out["ratio"] += ratio_questions(c, years=years, index_version=index_version)
    by_sector: defaultdict[str, list[GNumCompany]] = defaultdict(list)
    for c in sorted(companies, key=lambda c: c.company.cik):
        by_sector[c.company.sector].append(c)
    for members in by_sector.values():
        for a, b in combinations(members, 2):
            out["peer_comparison"] += peer_questions(
                a, b, years=years, index_version=index_version, seed=seed
            )
    return out


def select(questions: Sequence[NumQuestion], quota: int, seed: int) -> list[NumQuestion]:
    groups: defaultdict[tuple[int, ...], list[NumQuestion]] = defaultdict(list)
    for q in questions:
        groups[tuple(sorted(q.ciks))].append(q)
    ordered = [
        sorted(groups[key], key=lambda q: seeded_key(seed, "question", q.id))
        for key in sorted(groups, key=lambda k: seeded_key(seed, "group", *k))
    ]
    return round_robin(ordered)[:quota]


def generate(
    companies: Sequence[GNumCompany], config: GNumConfig, index_version: str
) -> GNumResult:
    questions: list[NumQuestion] = []
    report: list[StratumReport] = []
    for split in SPLITS:
        members = [c for c in companies if c.company.split == split and c.facts]
        pool = candidates(
            members, years=config.years, index_version=index_version, seed=config.seed
        )
        for qtype, quota in quotas(config.totals.get(split, 0)).items():
            chosen = select(pool[qtype], quota, config.seed)
            questions += chosen
            report.append(
                StratumReport(
                    split=split,
                    qtype=qtype,
                    candidates=len(pool[qtype]),
                    quota=quota,
                    selected=len(chosen),
                )
            )
    missing = tuple(sorted(c.company.ticker for c in companies if not c.facts))
    return GNumResult(
        questions=tuple(questions), report=tuple(report), companies_without_facts=missing
    )
