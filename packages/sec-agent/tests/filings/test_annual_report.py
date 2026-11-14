"""Exhibit 13 (annual report to shareholders) text blocks to the same section keys as a 10-K.

An annual report has no "Item" headings: MD&A is "Management's Discussion and Analysis" or
"Financial Review", risk factors are "Risk Factors", and the report repeats a section's
title at page tops.
"""

from collections.abc import Callable

from sec_agent.filings.annual_report import find_annual_report_sections
from sec_agent.filings.html_text import html_blocks

URL = "https://www.sec.gov/Archives/edgar/data/9999999999/999999999925000011/simb-ex13.htm"
FILLER = "The simulated company describes this topic at enough length to count as a section."


def test_financial_review_is_mdna_and_risk_factors_end_where_the_next_part_starts(
    read_fixture: Callable[[str], bytes],
) -> None:
    sections = find_annual_report_sections(html_blocks(read_fixture("sim-ex13.htm")), URL)
    assert [s.key for s in sections] == ["risk_factors", "mdna"]
    risk, mdna = sections

    assert mdna.item == "Exhibit 13"
    assert mdna.heading == "Financial Review"
    assert mdna.source_url == URL
    assert mdna.text.startswith("Overview\nSimulated Bancorp earned simulated net income in 2024.")
    assert "Noninterest income rose on simulated advisory fees." in mdna.text  # past page top
    assert "simulated asset cap" in mdna.text  # Regulatory Matters is part of the review
    assert mdna.text.endswith("This report contains simulated forward-looking statements.")
    assert "Financial Review" not in mdna.text  # the running header is not body text
    assert "Contents" not in mdna.text

    assert risk.heading == "Risk Factors"
    assert risk.text.startswith("An investment in the company involves simulated risks")
    assert risk.text.endswith("including the asset cap, could limit growth.")
    assert "continued" not in risk.text
    assert "disclosure controls" not in risk.text


def test_mdna_heading_and_market_risk_end_at_the_auditor_report() -> None:
    blocks = [
        "Management's Discussion and Analysis of Financial Condition and Results of Operations",
        FILLER,
        "Quantitative and Qualitative Disclosures About Market Risk",
        "The company is exposed to simulated interest rate risk on simulated borrowings.",
        "Report of Independent Registered Public Accounting Firm",
        "We have audited the simulated statements.",
    ]
    sections = find_annual_report_sections(blocks, URL)
    assert [(s.key, s.text) for s in sections] == [
        ("mdna", FILLER),
        ("market_risk", blocks[3]),
    ]


def test_a_title_inside_a_sentence_is_not_a_heading() -> None:
    blocks = ["Financial Review", FILLER, "See Risk Factors for more.", FILLER]
    (mdna,) = find_annual_report_sections(blocks, URL)
    assert mdna.text == "\n".join(blocks[1:])


def test_a_report_without_those_parts_gives_no_sections() -> None:
    assert find_annual_report_sections(["Letter to Shareholders", FILLER], URL) == []
