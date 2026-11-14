"""Replace the text between the results markers and nothing else."""

import pytest
from sec_agent.report.splice import MarkersMissingError, splice_block

START = "<!-- results:start -->"
END = "<!-- results:end -->"


def test_replaces_only_the_block() -> None:
    text = f"before\n{START}\nold\n{END}\nafter\n"
    assert splice_block(text, "new") == f"before\n{START}\nnew\n{END}\nafter\n"


def test_is_idempotent() -> None:
    once = splice_block(f"a\n{START}\n{END}\nb\n", "x\ny")
    assert splice_block(once, "x\ny") == once


def test_missing_markers_raise() -> None:
    with pytest.raises(MarkersMissingError):
        splice_block("no markers here", "x")
