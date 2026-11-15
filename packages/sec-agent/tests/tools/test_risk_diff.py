"""Block diff of two risk factor sections: added, removed, changed and unchanged paragraphs.

Every paragraph here is simulated text written for the test.
"""

from sec_agent.tools.risk_diff import Block, diff_blocks, similarity, split_blocks

OLD = """Investing in a simulated company involves risks.
Supply of simulated parts may be interrupted. A single supplier provides most parts.
Our simulated factory is located in one region exposed to floods.
5
We depend on three distributors for most of our simulated sales."""

NEW = """Investing in a simulated company involves risks.
We depend on two distributors for most of our simulated sales.
Supply of simulated parts may be interrupted. A single supplier provides most parts.
New export controls may restrict sales of simulated widgets abroad."""


def test_blocks_are_lines_with_their_offsets_and_page_numbers_dropped() -> None:
    blocks = split_blocks(OLD)
    assert [b.text for b in blocks] == [line for line in OLD.splitlines() if line != "5"]
    for b in blocks:
        assert OLD[b.start : b.end] == b.text


def test_blocks_ignore_surrounding_whitespace() -> None:
    text = "  First risk paragraph here.  \n\n\tSecond risk paragraph.\n"
    blocks = split_blocks(text)
    assert [b.text for b in blocks] == ["First risk paragraph here.", "Second risk paragraph."]
    assert all(text[b.start : b.end] == b.text for b in blocks)


def test_diff_finds_added_removed_changed_and_moved_unchanged() -> None:
    diff = diff_blocks(split_blocks(OLD), split_blocks(NEW))
    assert diff.unchanged == 2  # the intro, and the supplier risk although it moved
    assert [b.text for b in diff.added] == [
        "New export controls may restrict sales of simulated widgets abroad."
    ]
    assert [b.text for b in diff.removed] == [
        "Our simulated factory is located in one region exposed to floods."
    ]
    assert len(diff.changed) == 1
    pair = diff.changed[0]
    assert "three distributors" in pair.old.text
    assert "two distributors" in pair.new.text
    assert 0.5 <= pair.similarity < 1


def test_case_and_spacing_alone_are_no_change() -> None:
    old = [Block("Supply  may be INTERRUPTED.", 0, 26)]
    new = [Block("supply may be interrupted.", 0, 26)]
    diff = diff_blocks(old, new)
    assert (diff.unchanged, diff.added, diff.removed, diff.changed) == (1, (), (), ())


def test_identical_duplicates_pair_one_to_one() -> None:
    a = Block("Same risk.", 0, 10)
    diff = diff_blocks([a, a], [a])
    assert diff.unchanged == 1
    assert diff.removed == (a,)


def test_similarity_is_jaccard_of_word_sets() -> None:
    assert similarity("a b c", "a b d") == 0.5
    assert similarity("A, b!", "a b") == 1.0
    assert similarity("", "") == 1.0
    assert similarity("x", "") == 0.0


def test_pairing_takes_the_most_similar_first_and_is_deterministic() -> None:
    old = [Block("alpha beta gamma delta", 0, 1), Block("alpha beta gamma epsilon zeta", 2, 3)]
    new = [Block("alpha beta gamma delta eta", 4, 5)]
    first = diff_blocks(old, new)
    assert [(p.old.start, p.new.start) for p in first.changed] == [(0, 4)]
    assert [b.start for b in first.removed] == [2]
    assert diff_blocks(old, new) == first


def test_empty_sections() -> None:
    blocks = split_blocks(NEW)
    assert diff_blocks([], blocks).added == tuple(blocks)
    assert diff_blocks(blocks, []).removed == tuple(blocks)
