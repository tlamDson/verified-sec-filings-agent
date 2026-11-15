"""Filing HTML to text blocks: one block per paragraph, line, or table row."""

from collections.abc import Callable

from sec_agent.filings.html_text import decode_html, html_blocks


def test_block_elements_split_and_inline_elements_join() -> None:
    html = "<div>Item <b>1A.</b> Risk</div><p>First<br>second</p><p>third</p>"
    assert html_blocks(html) == ["Item 1A. Risk", "First", "second", "third"]


def test_table_cells_join_into_one_row() -> None:
    html = "<table><tr><td>Net sales</td><td>$</td><td>1,234</td></tr><tr><td>x</td></tr></table>"
    assert html_blocks(html) == ["Net sales $ 1,234", "x"]


def test_whitespace_entities_and_nbsp_are_normalised() -> None:
    html = "<div>Item&#160;1.&nbsp;&nbsp; Business\n  of the\tCompany&#8217;s\u200b unit</div>"
    assert html_blocks(html) == ["Item 1. Business of the Company\u2019s unit"]


def test_script_style_head_and_hidden_blocks_are_skipped() -> None:
    html = (
        "<head><title>t</title><style>p {}</style></head>"
        "<script>var x = '<p>no</p>';</script>"
        "<div style='DISPLAY : None'><ix:header>hidden fact</ix:header></div>"
        "<p>shown</p>"
    )
    assert html_blocks(html) == ["shown"]


def test_unclosed_tags_inside_a_hidden_block_do_not_swallow_the_rest() -> None:
    html = "<div style='display:none'><p>open <span>never closed</div><p>after</p>"
    assert html_blocks(html) == ["after"]


def test_self_closing_hidden_element_hides_nothing_else() -> None:
    html = "<div style='display:none'/><p>after</p>"
    assert html_blocks(html) == ["after"]


def test_page_numbers_and_table_of_contents_links_are_dropped() -> None:
    html = "<p>body</p><div>12</div><div>Page 13</div><div>Table of Contents</div><p>more</p>"
    assert html_blocks(html) == ["body", "more"]


def test_decode_html_reads_utf8_and_falls_back_to_cp1252() -> None:
    assert decode_html("Company\u2019s".encode()) == "Company\u2019s"
    assert decode_html(b"Company\x92s") == "Company\u2019s"


def test_simulated_10k_hides_xbrl_header_and_keeps_body(
    read_fixture: Callable[[str], bytes],
) -> None:
    blocks = html_blocks(read_fixture("sim-10k.htm"))
    text = "\n".join(blocks)
    assert "hidden fact" not in text
    assert "unclosed paragraph" not in text
    assert "font-weight" not in text
    assert "var note" not in text
    assert "UNITED STATES SECURITIES AND EXCHANGE COMMISSION" in blocks
    assert "Net sales $ 1,234 $ 1,100" in blocks
    assert "Table of Contents" not in blocks
