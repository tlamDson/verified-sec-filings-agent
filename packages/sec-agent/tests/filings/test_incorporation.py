"""10-K items incorporated by reference to Exhibit 13, and replacing them with its text."""

from collections.abc import Callable

from sec_agent.filings.annual_report import find_annual_report_sections
from sec_agent.filings.html_text import html_blocks
from sec_agent.filings.incorporation import incorporated_keys, merge_sections
from sec_agent.filings.models import Section
from sec_agent.filings.sections import find_sections

URL = "https://www.sec.gov/Archives/edgar/data/9999999999/999999999925000011/simb-ex13.htm"


def _primary(read: Callable[[str], bytes], name: str, form: str = "10-K") -> list[Section]:
    return find_sections(html_blocks(read(name)), form)


def test_stub_items_pointing_to_the_annual_report_are_incorporated(
    read_fixture: Callable[[str], bytes],
) -> None:
    primary = _primary(read_fixture, "sim-10k-ibr.htm")
    assert incorporated_keys(primary, "10-K") == {"risk_factors", "mdna", "market_risk"}


def test_a_10k_with_its_own_text_incorporates_nothing(
    read_fixture: Callable[[str], bytes],
) -> None:
    assert incorporated_keys(_primary(read_fixture, "sim-10k.htm"), "10-K") == set()
    assert incorporated_keys(_primary(read_fixture, "sim-10k.htm"), "10-K/A") == set()


def test_quarterly_reports_never_look_for_exhibit_13(
    read_fixture: Callable[[str], bytes],
) -> None:
    assert incorporated_keys(_primary(read_fixture, "sim-10q.htm", "10-Q"), "10-Q") == set()
    assert incorporated_keys([], "10-Q") == set()


def test_a_missing_annual_item_is_looked_for_in_exhibit_13() -> None:
    assert incorporated_keys([], "10-K") == {"risk_factors", "mdna", "market_risk"}


def test_exhibit_text_replaces_only_the_incorporated_stubs(
    read_fixture: Callable[[str], bytes],
) -> None:
    primary = _primary(read_fixture, "sim-10k-ibr.htm")
    exhibit = find_annual_report_sections(html_blocks(read_fixture("sim-ex13.htm")), URL)
    merged = merge_sections(primary, exhibit, "10-K")
    assert [s.key for s in merged] == ["business", "risk_factors", "mdna", "market_risk"]
    by_key = {s.key: s for s in merged}
    assert by_key["business"] == primary[0]
    assert by_key["business"].source_url is None  # from the primary document
    assert by_key["mdna"].item == "Exhibit 13"
    assert by_key["mdna"].source_url == URL
    assert "simulated asset cap" in by_key["mdna"].text
    assert by_key["risk_factors"].source_url == URL
    # The exhibit has no market risk part of its own, so the 10-K's pointer stays.
    assert "incorporated into this item by reference" in by_key["market_risk"].text


def test_exhibit_text_never_replaces_an_item_the_10k_answers_itself(
    read_fixture: Callable[[str], bytes],
) -> None:
    primary = _primary(read_fixture, "sim-10k.htm")
    exhibit = find_annual_report_sections(html_blocks(read_fixture("sim-ex13.htm")), URL)
    assert merge_sections(primary, exhibit, "10-K") == primary
