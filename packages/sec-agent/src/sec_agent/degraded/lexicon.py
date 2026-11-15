"""The words a question may use for a figure, each mapped to one concept or ratio.

Every concept and ratio answers to its own name and label; `_SYNONYMS` adds the everyday
words. Phrases are matched whole, longest first, so "gross margin" is the ratio and never
"margin" plus something else. A measure with no XBRL concept (adjusted EBITDA, E4) has no
phrase here and so matches nothing.
"""

import re
from typing import Literal, NamedTuple

from sec_agent.tools.ratio_defs import RATIOS
from sec_agent.xbrl.concepts import CONCEPTS

MAX_METRICS = 3
_NON_WORD = re.compile(r"[^a-z0-9]+")


class Metric(NamedTuple):
    kind: Literal["concept", "ratio"]
    name: str


def words(text: str) -> str:
    """Lower-case words separated by single spaces; "&" reads as "and"."""
    return _NON_WORD.sub(" ", text.casefold().replace("&", " and ")).strip()


_SYNONYMS: dict[str, tuple[str, ...]] = {
    "revenue": ("revenues", "sales", "net sales", "total revenue", "top line"),
    "cost_of_revenue": ("cost of sales", "cost of goods sold", "cogs"),
    "research_and_development": ("r and d", "research and development expense"),
    "selling_general_admin": ("sg and a", "sga", "selling general and administrative expense"),
    "operating_expenses": ("opex",),
    "operating_income": ("operating profit", "income from operations"),
    "pretax_income": ("pretax income", "pre tax income", "income before taxes"),
    "income_tax": ("income taxes", "tax expense", "provision for income taxes"),
    "net_income": ("net profit", "net earnings", "profit", "earnings", "bottom line"),
    "eps_basic": ("basic eps", "basic earnings per share"),
    "eps_diluted": ("eps", "earnings per share", "diluted eps", "diluted earnings per share"),
    "depreciation_amortization": ("d and a", "depreciation"),
    "cash_and_equivalents": ("cash", "cash equivalents"),
    "accounts_receivable": ("receivables",),
    "inventory": ("inventories",),
    "total_assets": ("assets",),
    "total_liabilities": ("liabilities",),
    "long_term_debt_noncurrent": ("long term debt", "debt"),
    "stockholders_equity": ("shareholders equity", "equity", "book value"),
    "shares_outstanding": ("shares outstanding",),
    "operating_cash_flow": (
        "operating cash flow",
        "cash from operations",
        "cash flow from operations",
        "cash flow from operating activities",
    ),
    "investing_cash_flow": ("investing cash flow", "cash flow from investing activities"),
    "financing_cash_flow": ("financing cash flow", "cash flow from financing activities"),
    "capital_expenditures": ("capital expenditures", "capital expenditure", "capex"),
    "dividends_paid": ("dividends", "dividend"),
    "share_repurchases": ("share repurchases", "buybacks", "buyback", "stock repurchases"),
    "gross_margin": ("gross margins", "gross profit margin"),
    "operating_margin": ("operating margins", "operating profit margin"),
    "net_margin": ("net margins", "net profit margin", "profit margin"),
    "effective_tax_rate": ("tax rate",),
    "rd_to_revenue": ("r and d intensity", "r and d to revenue", "r and d as a share of revenue"),
    "current_ratio": (),
    "liabilities_to_equity": ("debt to equity", "liabilities to equity", "leverage"),
}


_NO_FIGURE = ("free cash flow", "cash flow", "adjusted ebitda", "ebitda", "adjusted earnings")
"""Read whole and matched to nothing: a non-GAAP measure (E4), or a name too vague to
pick one concept for. Without these, "free cash flow" would read as "cash"."""


def _phrases() -> dict[str, Metric | None]:
    found: dict[str, Metric | None] = dict.fromkeys(_NO_FIGURE)
    for concept in CONCEPTS:
        metric = Metric("concept", concept.name)
        for phrase in (concept.name, concept.label, *_SYNONYMS.get(concept.name, ())):
            found.setdefault(words(phrase), metric)
    for ratio in RATIOS.values():
        metric = Metric("ratio", ratio.name)
        # A ratio's own name wins over a concept phrase it contains.
        for phrase in (ratio.name, ratio.label, *_SYNONYMS.get(ratio.name, ())):
            found[words(phrase)] = metric
    return found


PHRASES: dict[str, Metric | None] = _phrases()
_ANY_PHRASE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in sorted(PHRASES, key=len, reverse=True)) + r")\b"
)


def find_metrics(question: str) -> tuple[Metric, ...]:
    """The figures a question names, in the order named, each once, at most `MAX_METRICS`."""
    found: list[Metric] = []
    for match in _ANY_PHRASE.finditer(words(question)):
        metric = PHRASES[match.group()]
        if metric is not None and metric not in found:
            found.append(metric)
    return tuple(found[:MAX_METRICS])
