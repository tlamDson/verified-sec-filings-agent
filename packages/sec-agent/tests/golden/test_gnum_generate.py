"""G-num selection: per-split quotas stratified by question type, seeded, no leakage."""

from collections import Counter

from golden_data import split_company

from sec_agent.golden.gnum.candidates import GNumCompany
from sec_agent.golden.gnum.generate import QUESTION_TYPES, GNumConfig, generate

YEARS = (2022, 2023, 2024, 2025)


def _config(test: int, *, seed: int = 11, train: int = 0, dev: int = 0) -> GNumConfig:
    return GNumConfig(seed=seed, years=YEARS, totals={"train": train, "dev": dev, "test": test})


def test_default_config_asks_1500_questions_300_of_them_on_test() -> None:
    config = GNumConfig()
    assert config.totals == {"train": 900, "dev": 300, "test": 300}
    assert config.years == (2020, 2021, 2022, 2023, 2024)


def test_each_split_quota_is_shared_equally_by_the_five_question_types(
    apple: GNumCompany, nvidia: GNumCompany
) -> None:
    result = generate([apple, nvidia], _config(50), index_version="v1")
    assert set(QUESTION_TYPES) == {
        "value",
        "yoy_growth",
        "ratio",
        "peer_comparison",
        "fiscal_period",
    }
    assert Counter(q.qtype for q in result.questions) == dict.fromkeys(QUESTION_TYPES, 10)
    assert {q.split for q in result.questions} == {"test"}
    assert {q.index_version for q in result.questions} == {"v1"}


def test_a_quota_that_does_not_divide_by_five_gives_the_remainder_to_the_first_types(
    apple: GNumCompany, nvidia: GNumCompany
) -> None:
    counts = Counter(q.qtype for q in generate([apple, nvidia], _config(12), "v1").questions)
    assert [counts[t] for t in QUESTION_TYPES] == [3, 3, 2, 2, 2]


def test_selection_alternates_between_companies(apple: GNumCompany, nvidia: GNumCompany) -> None:
    result = generate([apple, nvidia], _config(50), index_version="v1")
    for qtype in ("value", "yoy_growth", "ratio", "fiscal_period"):
        per_company = Counter(q.tickers[0] for q in result.questions if q.qtype == qtype)
        assert abs(per_company["AAPL"] - per_company["NVDA"]) <= 1, qtype


def test_selection_is_fixed_by_the_seed(apple: GNumCompany, nvidia: GNumCompany) -> None:
    one = generate([apple, nvidia], _config(50, seed=11), "v1").questions
    assert one == generate([apple, nvidia], _config(50, seed=11), "v1").questions
    other = generate([apple, nvidia], _config(50, seed=12), "v1").questions
    assert {q.id for q in one} != {q.id for q in other}


def test_no_question_crosses_splits(apple: GNumCompany, nvidia: GNumCompany) -> None:
    train_nvidia = GNumCompany(
        company=nvidia.company.model_copy(update={"split": "train"}), facts=nvidia.facts
    )
    result = generate([apple, train_nvidia], _config(50, train=50), "v1")
    for q in result.questions:
        expected = "test" if q.ciks == (320193,) else "train"
        assert q.split == expected
        assert len(q.ciks) == 1  # peers would need two companies of one split and sector
    assert not [q for q in result.questions if q.qtype == "peer_comparison"]


def test_peers_come_from_one_sector_only(apple: GNumCompany, nvidia: GNumCompany) -> None:
    other_sector = GNumCompany(
        company=nvidia.company.model_copy(update={"sector": "Financials"}), facts=nvidia.facts
    )
    result = generate([apple, other_sector], _config(50), "v1")
    assert not [q for q in result.questions if q.qtype == "peer_comparison"]


def test_a_short_stratum_takes_every_candidate_and_reports_the_shortfall(
    apple: GNumCompany, nvidia: GNumCompany
) -> None:
    result = generate([apple, nvidia], _config(100_000), "v1")
    rows = {(r.split, r.qtype): r for r in result.report}
    for qtype in QUESTION_TYPES:
        row = rows[("test", qtype)]
        assert row.quota == 20_000
        assert 0 < row.candidates < row.quota
        assert row.selected == row.candidates
        assert row.shortfall == row.quota - row.candidates
    assert len({q.id for q in result.questions}) == len(result.questions)


def test_report_covers_every_split_and_type_even_when_empty(apple: GNumCompany) -> None:
    result = generate([apple], _config(5), "v1")
    assert {(r.split, r.qtype) for r in result.report} == {
        (s, t) for s in ("train", "dev", "test") for t in QUESTION_TYPES
    }
    assert result.companies_without_facts == ()


def test_companies_without_facts_are_listed_not_hidden(apple: GNumCompany) -> None:
    empty = GNumCompany(company=split_company("EMPT", 42, "test"), facts=())
    result = generate([apple, empty], _config(5), "v1")
    assert result.companies_without_facts == ("EMPT",)
