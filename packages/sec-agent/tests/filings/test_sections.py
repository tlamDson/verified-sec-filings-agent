"""Text blocks to the sections the index keeps: 10-K Items 1, 1A, 7, 7A; 10-Q MD&A and 1A."""

from collections.abc import Callable

import pytest

from sec_agent.filings.html_text import html_blocks
from sec_agent.filings.models import Section
from sec_agent.filings.sections import find_sections

FILLER = "The simulated company describes this topic at enough length to count as a section."


def _by_key(sections: list[Section]) -> dict[str, Section]:
    return {s.key: s for s in sections}


def test_10k_finds_the_four_items_and_skips_the_table_of_contents(
    read_fixture: Callable[[str], bytes],
) -> None:
    sections = find_sections(html_blocks(read_fixture("sim-10k.htm")), "10-K")
    assert [s.key for s in sections] == ["business", "risk_factors", "mdna", "market_risk"]
    found = _by_key(sections)

    business = found["business"]
    assert business.item == "Item 1"
    assert business.heading == "Item 1. Business"
    assert business.text.startswith("Company Overview\nSimulated Widgets Inc. designs")
    assert business.text.endswith("the Company employs simulated staff only.")
    assert "see Part I, Item 1A of this Form 10-K" in business.text  # a reference, not a heading

    risk = found["risk_factors"]
    assert risk.heading == "Item 1A. Risk Factors"  # heading split over two blocks
    assert risk.text.startswith("Investing in a simulated company involves risks.")
    assert risk.text.endswith("Item 7 of this report discusses how input costs affected margins.")

    mdna = found["mdna"]
    assert mdna.item == "Item 7"
    assert mdna.heading.startswith("Item 7. Management\u2019s Discussion and Analysis")
    assert "Net sales $ 1,234 $ 1,100" in mdna.text
    assert mdna.text.endswith("rose in every region.")

    market = found["market_risk"]
    assert market.item == "Item 7A"
    assert market.text == (
        "The Company is exposed to simulated interest rate risk on its variable-rate borrowings."
    )
    for section in sections:
        assert section.token_count > 0
        assert "Table of Contents" not in section.text


def test_10q_finds_mdna_in_part_i_and_risk_factors_in_part_ii(
    read_fixture: Callable[[str], bytes],
) -> None:
    sections = find_sections(html_blocks(read_fixture("sim-10q.htm")), "10-Q")
    assert [s.key for s in sections] == ["mdna", "risk_factors"]
    found = _by_key(sections)
    assert found["mdna"].item == "Part I, Item 2"
    assert found["mdna"].text.startswith("Second-quarter net sales rose")
    assert found["mdna"].text.endswith("simulated credit facility.")
    assert found["risk_factors"].item == "Part II, Item 1A"
    assert found["risk_factors"].text.startswith("There have been no material changes")
    assert "repurchased" not in found["risk_factors"].text


def test_amendment_with_only_part_iii_has_no_sections(
    read_fixture: Callable[[str], bytes],
) -> None:
    assert find_sections(html_blocks(read_fixture("sim-10ka-part3.htm")), "10-K/A") == []


def test_amendments_use_the_items_of_their_base_form() -> None:
    blocks = ["Item 1A. Risk Factors", FILLER, "Item 2. Properties", FILLER]
    assert [s.key for s in find_sections(blocks, "10-K/A")] == ["risk_factors"]
    assert [s.key for s in find_sections(blocks, "10-Q/A")] == ["risk_factors"]


def test_combined_items_heading_counts_for_the_first_item() -> None:
    blocks = ["Items 1 and 2. Business and Properties", FILLER, "Item 1A. Risk Factors", FILLER]
    found = _by_key(find_sections(blocks, "10-K"))
    assert found["business"].text == FILLER
    assert found["risk_factors"].text == FILLER


@pytest.mark.parametrize(
    "heading",
    [
        "ITEM 1A. RISK FACTORS",
        "Item 1A \u2014 Risk Factors",
        "Item 1A: Risk Factors",
        "Item 1A Risk Factors",
        "PART I, ITEM 1A. RISK FACTORS",
    ],
)
def test_heading_variants(heading: str) -> None:
    sections = find_sections([heading, FILLER, "Item 1B. Unresolved Staff Comments"], "10-K")
    assert [(s.key, s.text) for s in sections] == [("risk_factors", FILLER)]


@pytest.mark.parametrize(
    "block",
    [
        "Item 7 of this report discusses margins.",
        "See Item 7. Management's Discussion and Analysis.",
        "Item 7. " + "Long sentence that only looks like a heading. " * 6,
    ],
)
def test_references_and_long_blocks_are_not_headings(block: str) -> None:
    blocks = ["Item 1A. Risk Factors", FILLER, block, FILLER, "Item 1B. None"]
    (risk,) = find_sections(blocks, "10-K")
    assert block in risk.text


def test_section_ends_at_the_next_part_or_signatures() -> None:
    blocks = ["Item 7A. Quantitative and Qualitative Disclosures About Market Risk", FILLER]
    for end in ("PART III", "SIGNATURES"):
        (market,) = find_sections([*blocks, end, "tail text after the section"], "10-K")
        assert market.text == FILLER


def test_longest_candidate_wins_over_table_of_contents_rows() -> None:
    blocks = [
        "Item 1A. Risk Factors 5",
        "Item 1B. Unresolved Staff Comments 9",
        "Item 1A. Risk Factors",
        FILLER,
        FILLER,
        "Item 1B. Unresolved Staff Comments",
    ]
    (risk,) = find_sections(blocks, "10-K")
    assert risk.text == f"{FILLER}\n{FILLER}"


def test_too_short_a_section_is_dropped() -> None:
    blocks = ["Item 1A. Risk Factors", "See page 12.", "Item 1B. Unresolved Staff Comments"]
    assert find_sections(blocks, "10-K") == []


def test_unknown_form_is_rejected() -> None:
    with pytest.raises(ValueError, match="8-K"):
        find_sections([], "8-K")
