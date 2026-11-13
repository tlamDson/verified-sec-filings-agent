"""The company-level split: which companies are train, dev and test, fixed by a seed.

1. Sample: eligible companies are grouped by GICS sector; sectors take turns, in a seeded
   order, each giving its next company in a seeded order, until `n` are taken. The S&P 100
   has only seven sectors with five or more members, so "5 per sector x 10 sectors" cannot
   hold; taking turns keeps sectors within one company of each other unless a sector runs
   out (Materials and Real Estate have one member each).
2. Assign: test, then dev, draw same-sector pairs, walking the sectors in the seeded order
   and taking a pair only from a sector that keeps at least one company for train. Pairs
   let every split ask peer questions inside itself; everything left is train.
3. Until a split holds two companies whose fiscal year does not end in December (E1), the
   walk skips sectors with no such company left, and a pair starts with that company. A
   split of December filers only would have almost no fiscal-period trap to ask about.

Questions about a split's companies stay in that split (no company leaks across splits).
"""

from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sec_agent.golden.ranking import round_robin, seeded_key
from sec_agent.golden.universe import Company, universe_digest

CompanySplitName = Literal["train", "dev", "test"]
SPLIT_SEED = 20261113
"""The seed of the committed split (`data/golden/company_split.json`)."""
DEFAULT_SPLIT_FILE = Path("data/golden/company_split.json")
_MIN_TRAIN_LEFT = 1
_MIN_OFF_CALENDAR = 2


class SplitCompany(Company):
    split: CompanySplitName


class CompanySplit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int
    universe_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    companies: tuple[SplitCompany, ...]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        for field in ("ticker", "cik"):
            values = [getattr(c, field) for c in self.companies]
            if len(set(values)) != len(values):
                raise ValueError(f"split has a duplicate {field}")
        return self

    def of(self, split: CompanySplitName) -> tuple[SplitCompany, ...]:
        return tuple(c for c in self.companies if c.split == split)

    def by_ticker(self, ticker: str) -> SplitCompany | None:
        return next((c for c in self.companies if c.ticker == ticker), None)

    def by_cik(self, cik: int) -> SplitCompany | None:
        return next((c for c in self.companies if c.cik == cik), None)


def _sector_order(sectors: set[str], seed: int) -> list[str]:
    return sorted(sectors, key=lambda s: seeded_key(seed, "sector", s))


def _by_sector(companies: Sequence[Company], seed: int) -> dict[str, list[Company]]:
    groups: defaultdict[str, list[Company]] = defaultdict(list)
    for c in sorted(companies, key=lambda c: seeded_key(seed, "company", c.cik)):
        groups[c.sector].append(c)
    return dict(groups)


def sample_companies(universe: Sequence[Company], *, seed: int, n: int = 50) -> list[Company]:
    """`n` eligible companies, sectors taking turns (see the module docstring)."""
    eligible = [c for c in universe if not c.excluded]
    if len(eligible) < n:
        raise ValueError(f"universe has {len(eligible)} eligible companies, fewer than {n}")
    groups = _by_sector(eligible, seed)
    return round_robin(groups[s] for s in _sector_order(set(groups), seed))[:n]


def build_split(
    universe: Sequence[Company],
    *,
    seed: int = SPLIT_SEED,
    n: int = 50,
    test: int = 10,
    dev: int = 10,
) -> CompanySplit:
    """Sample `n` companies, then draw `test` and `dev` as same-sector pairs; rest is train."""
    if test % 2 or dev % 2:
        raise ValueError("test and dev sizes must be even: they are drawn as same-sector pairs")
    sample = sample_companies(universe, seed=seed, n=n)
    remaining = _by_sector(sample, seed)
    order = _sector_order(set(remaining), seed)
    assigned: dict[int, CompanySplitName] = {}
    cursor = 0
    plan: tuple[tuple[CompanySplitName, int], ...] = (("test", test), ("dev", dev))
    for name, size in plan:
        pairs, misses, off_calendar = size // 2, 0, 0
        while pairs:
            sector = order[cursor % len(order)]
            cursor += 1
            pair = _pair(remaining[sector], need_off_calendar=off_calendar < _MIN_OFF_CALENDAR)
            if pair is None and off_calendar < _MIN_OFF_CALENDAR and misses >= len(order):
                # A full walk found no off-calendar company to give: take any pair.
                pair = _pair(remaining[sector], need_off_calendar=False)
            if pair is None:
                misses += 1
                if misses > 2 * len(order):
                    raise ValueError(f"not enough same-sector pairs to fill the {name} split")
                continue
            for company in pair:
                assigned[company.cik] = name
            remaining[sector] = [c for c in remaining[sector] if c not in pair]
            off_calendar += sum(c.off_calendar for c in pair)
            pairs, misses = pairs - 1, 0
    companies = tuple(
        SplitCompany(**c.model_dump(), split=assigned.get(c.cik, "train"))
        for c in sorted(sample, key=lambda c: c.ticker)
    )
    return CompanySplit(seed=seed, universe_sha256=universe_digest(universe), companies=companies)


def _pair(companies: list[Company], *, need_off_calendar: bool) -> tuple[Company, Company] | None:
    """Two companies of one sector that leave one for train; off-calendar first if needed."""
    if len(companies) < 2 + _MIN_TRAIN_LEFT:
        return None
    if not need_off_calendar:
        return (companies[0], companies[1])
    first = next((c for c in companies if c.off_calendar), None)
    if first is None:
        return None
    second = next(c for c in companies if c is not first)
    return (first, second)


def write_split(path: Path, split: CompanySplit) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(split.model_dump_json(indent=2) + "\n", "utf-8", newline="\n")


def read_split(path: Path) -> CompanySplit:
    return CompanySplit.model_validate_json(path.read_text("utf-8"))
