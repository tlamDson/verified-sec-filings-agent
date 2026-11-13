"""Reading a question without a model: which companies, which figures, which fiscal years.

Rules, not a model: what is not recognised is left out, never guessed.
"""

import pytest

from sec_agent.degraded.lexicon import Metric
from sec_agent.degraded.question import read_question
from sec_agent.tools.companies import CompanyDirectory

REVENUE = Metric(kind="concept", name="revenue")
NET_INCOME = Metric(kind="concept", name="net_income")
GROSS_MARGIN = Metric(kind="ratio", name="gross_margin")


def _tickers(question: str, directory: CompanyDirectory) -> list[str]:
    return [c.ticker for c in read_question(question, directory).companies]


def test_a_plain_numeric_question(directory: CompanyDirectory) -> None:
    parts = read_question("What was Apple's revenue in fiscal 2024?", directory)
    assert [c.ticker for c in parts.companies] == ["AAPL"]
    assert parts.metrics == (REVENUE,)
    assert parts.years == (2024,)
    assert (parts.span, parts.fiscal_period) == (None, "FY")
    assert (parts.growth, parts.peers, parts.risk_changes) == (False, False, False)


@pytest.mark.parametrize(
    ("question", "tickers"),
    [
        ("NVDA gross margin", ["NVDA"]),
        ("How did nvidia do?", ["NVDA"]),
        ("Compare Nvidia with AMD", ["NVDA", "AMD"]),
        ("revenue of Advanced Micro Devices", ["AMD"]),
        ("What does $T report as debt?", ["T"]),
        ("Facebook revenue", ["META"]),
        ("Is Google growing?", ["GOOGL"]),
        ("Meta net income", ["META"]),
        ("Amazon and Microsoft", ["AMZN", "MSFT"]),
        ("JPMorgan Chase total assets", ["JPM"]),
        ("apple, Apple and AAPL", ["AAPL"]),
        ("BRK.B cash", ["BRK.B"]),
    ],
)
def test_companies_are_found_by_ticker_alias_or_name(
    question: str, tickers: list[str], directory: CompanyDirectory
) -> None:
    assert _tickers(question, directory) == tickers


@pytest.mark.parametrize(
    "question",
    [
        "Is the cost of revenue low for all of them, so what now?",
        "what is a 10-k?",
        "Which company has the highest margin?",
        "Tell me about Zzyzx Corp revenue",
        "What did the CEO say about AI and the US economy in Q3?",
        "a c t v",
    ],
)
def test_ordinary_words_are_not_read_as_tickers(question: str, directory: CompanyDirectory) -> None:
    assert _tickers(question, directory) == []


def test_at_most_four_companies_are_kept_in_the_order_named(directory: CompanyDirectory) -> None:
    question = "AAPL, MSFT, NVDA, AMD, INTC and IBM revenue"
    assert _tickers(question, directory) == ["AAPL", "MSFT", "NVDA", "AMD"]


@pytest.mark.parametrize(
    ("question", "metrics"),
    [
        ("Apple sales", (REVENUE,)),
        ("Apple net income and revenue", (NET_INCOME, REVENUE)),
        ("Apple gross margin", (GROSS_MARGIN,)),
        ("Apple gross profit", (Metric(kind="concept", name="gross_profit"),)),
        ("Apple diluted EPS", (Metric(kind="concept", name="eps_diluted"),)),
        ("Apple earnings per share", (Metric(kind="concept", name="eps_diluted"),)),
        ("Apple R&D spending", (Metric(kind="concept", name="research_and_development"),)),
        ("Apple operating cash flow", (Metric(kind="concept", name="operating_cash_flow"),)),
        ("Apple operating margin", (Metric(kind="ratio", name="operating_margin"),)),
        ("Apple current ratio", (Metric(kind="ratio", name="current_ratio"),)),
        ("Apple total assets", (Metric(kind="concept", name="total_assets"),)),
        ("Apple's profit", (NET_INCOME,)),
        ("Apple", ()),
        ("Apple adjusted EBITDA", ()),
    ],
)
def test_figures_are_matched_by_their_longest_name(
    question: str, metrics: tuple[Metric, ...], directory: CompanyDirectory
) -> None:
    """E4: a non-GAAP measure has no XBRL concept, so it matches nothing."""
    assert read_question(question, directory).metrics == metrics


@pytest.mark.parametrize(
    ("question", "years", "span"),
    [
        ("Apple revenue 2023", (2023,), None),
        ("Apple revenue FY2022 and FY2024", (2022, 2024), None),
        ("Apple revenue in fiscal year 2021", (2021,), None),
        ("Apple revenue from 2021 to 2023", (2021, 2022, 2023), None),
        ("Apple revenue 2021-2023", (2021, 2022, 2023), None),
        ("Apple revenue over the last 3 years", (), 3),
        ("Apple revenue over the past five years", (), 5),
        ("Apple revenue last year", (), None),
        ("Apple revenue", (), None),
        ("Apple revenue over the last 40 years", (), 5),
        ("Apple revenue in 1066 and 3024", (), None),
    ],
)
def test_fiscal_years_named_or_spanned(
    question: str, years: tuple[int, ...], span: int | None, directory: CompanyDirectory
) -> None:
    parts = read_question(question, directory)
    assert (parts.years, parts.span) == (years, span)


def test_a_quarter_is_read_as_the_fiscal_period(directory: CompanyDirectory) -> None:
    assert read_question("Apple revenue Q2 2024", directory).fiscal_period == "Q2"
    assert read_question("Apple revenue in the third quarter of 2024", directory).fiscal_period == (
        "Q3"
    )


@pytest.mark.parametrize(
    "question",
    [
        "How fast did Apple's revenue grow in 2024?",
        "Apple revenue growth 2024",
        "Apple revenue year over year",
        "Apple revenue YoY",
    ],
)
def test_growth_words_ask_for_the_change_from_the_year_before(
    question: str, directory: CompanyDirectory
) -> None:
    assert read_question(question, directory).growth


@pytest.mark.parametrize(
    "question",
    [
        "How does Apple's gross margin compare to its peers?",
        "Apple gross margin against its sector",
        "Apple versus competitors on revenue",
    ],
)
def test_peer_words_ask_for_the_sector(question: str, directory: CompanyDirectory) -> None:
    assert read_question(question, directory).peers


@pytest.mark.parametrize(
    "question",
    [
        "What new risks did Apple add in its latest 10-K?",
        "How did Apple's risk factors change from last year?",
    ],
)
def test_questions_about_changed_risk_factors(question: str, directory: CompanyDirectory) -> None:
    assert read_question(question, directory).risk_changes


def test_a_plain_risk_question_is_not_a_diff(directory: CompanyDirectory) -> None:
    assert not read_question("What are Apple's main risks?", directory).risk_changes
