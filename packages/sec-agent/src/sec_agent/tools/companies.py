"""Which company a request means: ticker, CIK, name or a former ticker, always to one CIK (E8).

A company outside the directory (by default the eligible S&P 100 universe) is out of scope
(E7): the tools say so instead of answering about it.
"""

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Self

from pydantic import BaseModel, ConfigDict

from sec_agent.golden.universe import Company, GicsSector, load_universe
from sec_agent.tools.errors import AmbiguousCompanyError, UnknownCompanyError

ALIASES: Mapping[str, str] = {
    "FB": "META",  # Facebook, renamed Meta Platforms; ticker changed 2022-06-09
    "FACEBOOK": "META",
    "GOOG": "GOOGL",  # Alphabet's class C shares; one company, CIK 1652044
    "GOOGLE": "GOOGL",
}
"""Former tickers and names -> the current ticker. The CIK never changes on a rename."""

_SUFFIXES = frozenset(
    {"inc", "incorporated", "corp", "corporation", "co", "company", "plc", "ltd", "the"}
)
_NON_WORD = re.compile(r"[^a-z0-9]+")
_DIGITS = re.compile(r"\d{1,10}")


class CompanyRef(BaseModel):
    """The company a result is about."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    name: str
    cik: int
    sector: GicsSector


def _name_key(text: str) -> str:
    words = _NON_WORD.sub(" ", text.casefold()).split()
    return " ".join(w for w in words if w not in _SUFFIXES)


class CompanyDirectory:
    def __init__(self, companies: Iterable[Company], aliases: Mapping[str, str] = ALIASES) -> None:
        eligible = [c for c in companies if not c.excluded]
        self._refs = tuple(
            sorted(
                (
                    CompanyRef(ticker=c.ticker, name=c.name, cik=c.cik, sector=c.sector)
                    for c in eligible
                ),
                key=lambda r: r.cik,
            )
        )
        self._by_ticker = {r.ticker: r for r in self._refs}
        self._by_cik = {r.cik: r for r in self._refs}
        self._aliases = {
            a.upper(): self._by_ticker[t] for a, t in aliases.items() if t in self._by_ticker
        }
        names: defaultdict[str, list[CompanyRef]] = defaultdict(list)
        for r in self._refs:
            names[_name_key(r.name)].append(r)
        self._by_name = dict(names)

    @classmethod
    def from_universe(cls) -> Self:
        """The packaged S&P 100 universe, without its excluded companies."""
        return cls(load_universe())

    @property
    def companies(self) -> tuple[CompanyRef, ...]:
        return self._refs

    def by_cik(self, cik: int) -> CompanyRef | None:
        return self._by_cik.get(cik)

    def resolve(self, text: str) -> CompanyRef:
        """Ticker, alias, CIK, then name; raise when none or several companies match."""
        query = text.strip()
        upper = query.upper()
        found = self._by_ticker.get(upper) or self._aliases.get(upper)
        if found is None and _DIGITS.fullmatch(query):
            found = self._by_cik.get(int(query))
        if found is not None:
            return found
        matches = self._by_name.get(_name_key(query), []) if query else []
        if len(matches) > 1:
            tickers = ", ".join(sorted(m.ticker for m in matches))
            raise AmbiguousCompanyError(f"{text!r} matches {tickers}; ask with the ticker")
        if not matches:
            raise UnknownCompanyError(
                f"{text!r} is not in the {len(self._refs)} companies this product covers"
            )
        return matches[0]

    def sector_peers(self, company: CompanyRef) -> tuple[CompanyRef, ...]:
        """Every company of the same GICS sector, the company included, in CIK order."""
        return tuple(r for r in self._refs if r.sector == company.sector)
