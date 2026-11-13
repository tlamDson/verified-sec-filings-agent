"""Concept normalisation table: canonical concepts and the XBRL tags that mean each one.

Companies tag the same line differently (Apple's revenue was `SalesRevenueNet` until 2018,
`RevenueFromContractWithCustomerExcludingAssessedTax` since ASC 606). Each canonical
concept lists its tags in priority order; within one filing and period the first tag that
reports a value wins. A tag is listed only when it has the same accounting meaning as the
concept, so lines that include more (noncontrolling interest, current portion of debt,
restricted cash) are left out rather than mixed in. Each concept declares its unit (E5) and
whether it is a duration (income, cash flow) or an instant (balance sheet).
"""

from functools import cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PeriodType = Literal["duration", "instant"]
Unit = Literal["USD", "USD/shares", "shares"]


class TagRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    taxonomy: str = "us-gaap"
    tag: str


class Concept(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str
    period_type: PeriodType
    unit: Unit
    tags: tuple[TagRef, ...] = Field(min_length=1)


def _c(name: str, label: str, period_type: PeriodType, unit: Unit, *tags: str) -> Concept:
    return Concept(
        name=name,
        label=label,
        period_type=period_type,
        unit=unit,
        tags=tuple(TagRef(tag=t) for t in tags),
    )


DUR: PeriodType = "duration"
INST: PeriodType = "instant"

CONCEPTS: tuple[Concept, ...] = (
    # Income statement
    _c(
        "revenue",
        "Revenue",
        DUR,
        "USD",
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ),
    _c(
        "cost_of_revenue",
        "Cost of revenue",
        DUR,
        "USD",
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
    ),
    _c("gross_profit", "Gross profit", DUR, "USD", "GrossProfit"),
    _c(
        "research_and_development",
        "Research and development",
        DUR,
        "USD",
        "ResearchAndDevelopmentExpense",
    ),
    _c(
        "selling_general_admin",
        "Selling, general and administrative",
        DUR,
        "USD",
        "SellingGeneralAndAdministrativeExpense",
    ),
    _c("operating_expenses", "Operating expenses", DUR, "USD", "OperatingExpenses"),
    _c("operating_income", "Operating income", DUR, "USD", "OperatingIncomeLoss"),
    _c(
        "interest_expense",
        "Interest expense",
        DUR,
        "USD",
        "InterestExpense",
        "InterestExpenseNonoperating",
    ),
    _c(
        "pretax_income",
        "Income before income taxes",
        DUR,
        "USD",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ),
    _c("income_tax", "Income tax expense", DUR, "USD", "IncomeTaxExpenseBenefit"),
    _c("net_income", "Net income", DUR, "USD", "NetIncomeLoss"),
    _c("eps_basic", "Earnings per share, basic", DUR, "USD/shares", "EarningsPerShareBasic"),
    _c("eps_diluted", "Earnings per share, diluted", DUR, "USD/shares", "EarningsPerShareDiluted"),
    _c(
        "weighted_shares_basic",
        "Weighted average shares, basic",
        DUR,
        "shares",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ),
    _c(
        "weighted_shares_diluted",
        "Weighted average shares, diluted",
        DUR,
        "shares",
        "WeightedAverageNumberOfDilutedSharesOutstanding",
    ),
    _c(
        "depreciation_amortization",
        "Depreciation and amortization",
        DUR,
        "USD",
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
    ),
    # Balance sheet
    _c(
        "cash_and_equivalents",
        "Cash and cash equivalents",
        INST,
        "USD",
        "CashAndCashEquivalentsAtCarryingValue",
    ),
    _c(
        "short_term_investments",
        "Short-term investments",
        INST,
        "USD",
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
    ),
    _c("accounts_receivable", "Accounts receivable", INST, "USD", "AccountsReceivableNetCurrent"),
    _c("inventory", "Inventory", INST, "USD", "InventoryNet"),
    _c("current_assets", "Current assets", INST, "USD", "AssetsCurrent"),
    _c("total_assets", "Total assets", INST, "USD", "Assets"),
    _c("current_liabilities", "Current liabilities", INST, "USD", "LiabilitiesCurrent"),
    _c("total_liabilities", "Total liabilities", INST, "USD", "Liabilities"),
    _c(
        "long_term_debt_noncurrent",
        "Long-term debt, noncurrent",
        INST,
        "USD",
        "LongTermDebtNoncurrent",
    ),
    _c("stockholders_equity", "Stockholders' equity", INST, "USD", "StockholdersEquity"),
    _c(
        "shares_outstanding",
        "Common shares outstanding",
        INST,
        "shares",
        "CommonStockSharesOutstanding",
    ),
    # Cash flow statement
    _c(
        "operating_cash_flow",
        "Net cash from operating activities",
        DUR,
        "USD",
        "NetCashProvidedByUsedInOperatingActivities",
    ),
    _c(
        "investing_cash_flow",
        "Net cash from investing activities",
        DUR,
        "USD",
        "NetCashProvidedByUsedInInvestingActivities",
    ),
    _c(
        "financing_cash_flow",
        "Net cash from financing activities",
        DUR,
        "USD",
        "NetCashProvidedByUsedInFinancingActivities",
    ),
    _c(
        "capital_expenditures",
        "Purchases of property and equipment",
        DUR,
        "USD",
        "PaymentsToAcquirePropertyPlantAndEquipment",
    ),
    _c(
        "dividends_paid",
        "Dividends paid",
        DUR,
        "USD",
        "PaymentsOfDividends",
        "PaymentsOfDividendsCommonStock",
    ),
    _c(
        "share_repurchases",
        "Repurchases of common stock",
        DUR,
        "USD",
        "PaymentsForRepurchaseOfCommonStock",
    ),
)


@cache
def _by_name() -> dict[str, Concept]:
    return {c.name: c for c in CONCEPTS}


@cache
def concepts_by_tag() -> dict[tuple[str, str], Concept]:
    """(taxonomy, tag) -> the one concept that tag stands for."""
    return {(t.taxonomy, t.tag): c for c in CONCEPTS for t in c.tags}


def concept(name: str) -> Concept:
    """The canonical concept called `name`; KeyError when there is none."""
    return _by_name()[name]


def tag_priority(concept_: Concept, taxonomy: str, tag: str) -> int:
    """Position of the tag in the concept's list: 0 is preferred."""
    return concept_.tags.index(TagRef(taxonomy=taxonomy, tag=tag))
