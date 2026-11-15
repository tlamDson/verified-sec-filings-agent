"""What the user is shown: the answer, the answer without its untraced sentences, or nothing.

Evidence comes from the real tools on the recorded Apple facts; answers are simulated.
"""

import pytest
from faithfulness_kit import ASKED_ON, run_tool

from sec_agent.agent.answer import Evidence
from sec_agent.faithfulness.check import check_answer
from sec_agent.faithfulness.config import FaithfulnessConfig
from sec_agent.faithfulness.notices import BLOCKED_TEXT, TRIMMED_NOTE
from sec_agent.tools.context import FactsContext

GOOD = "Apple's revenue for fiscal 2024 was $391.0 billion."
GOOD_TOO = "That period ended September 28, 2024."
BAD = "Its revenue will reach $450 billion."
PROSE = "This is not investment advice."


@pytest.fixture
def evidence(facts_ctx: FactsContext) -> list[Evidence]:
    return [run_tool(facts_ctx, "get_fact", company="AAPL", concept="revenue", fiscal_year=2024)]


def test_an_answer_whose_figures_all_trace_is_shown_unchanged(evidence: list[Evidence]) -> None:
    text = f"{GOOD} {GOOD_TOO} {PROSE}"
    report = check_answer(text, evidence, asked_on=ASKED_ON)
    assert (report.verdict, report.text, report.faithful) == ("pass", text, True)
    assert (report.mentions, report.traced) == (2, 2)
    assert all(s.kept for s in report.sentences)


def test_an_untraced_sentence_is_dropped_and_the_user_told(evidence: list[Evidence]) -> None:
    report = check_answer(f"{GOOD} {BAD} {GOOD_TOO} {PROSE}", evidence, asked_on=ASKED_ON)
    assert report.verdict == "trimmed"
    assert report.text == f"{GOOD} {GOOD_TOO} {PROSE}\n\n{TRIMMED_NOTE}"
    assert not report.faithful
    assert (report.mentions, report.traced) == (3, 2)
    assert [s.kept for s in report.sentences] == [True, False, True, True]


def test_a_dropped_line_leaves_the_other_lines_as_they_were(evidence: list[Evidence]) -> None:
    text = f"Figures:\n- {GOOD}\n- {BAD}\n- {GOOD_TOO}\n\n{PROSE}"
    report = check_answer(text, evidence, asked_on=ASKED_ON)
    assert report.verdict == "trimmed"
    assert report.text == f"Figures:\n- {GOOD}\n- {GOOD_TOO}\n\n{PROSE}\n\n{TRIMMED_NOTE}"


def test_an_answer_is_blocked_when_most_of_its_checked_sentences_fail(
    evidence: list[Evidence],
) -> None:
    """Sentences without a figure, date or citation are not counted either way."""
    report = check_answer(f"{BAD} {PROSE}", evidence, asked_on=ASKED_ON)
    assert (report.verdict, report.text) == ("blocked", BLOCKED_TEXT)
    assert [s.kept for s in report.sentences] == [False, False]


def test_half_the_checked_sentences_failing_is_still_trimmed_by_default(
    evidence: list[Evidence],
) -> None:
    report = check_answer(f"{GOOD} {BAD}", evidence, asked_on=ASKED_ON)
    assert report.verdict == "trimmed"


def test_block_mode_blocks_on_any_untraced_figure(evidence: list[Evidence]) -> None:
    config = FaithfulnessConfig(on_failure="block")
    report = check_answer(f"{GOOD} {BAD} {GOOD_TOO}", evidence, asked_on=ASKED_ON, config=config)
    assert (report.verdict, report.text) == ("blocked", BLOCKED_TEXT)
    passing = check_answer(GOOD, evidence, asked_on=ASKED_ON, config=config)
    assert passing.verdict == "pass"


def test_an_answer_left_with_nothing_to_say_is_blocked(evidence: list[Evidence]) -> None:
    config = FaithfulnessConfig(max_dropped_share=1.0)
    assert check_answer(BAD, evidence, asked_on=ASKED_ON, config=config).verdict == "blocked"
    kept = check_answer(f"{BAD} {PROSE}", evidence, asked_on=ASKED_ON, config=config)
    assert (kept.verdict, kept.text) == ("trimmed", f"{PROSE}\n\n{TRIMMED_NOTE}")


def test_the_notices_hold_no_figure(evidence: list[Evidence]) -> None:
    for notice in (BLOCKED_TEXT, TRIMMED_NOTE):
        assert check_answer(notice, evidence, asked_on=ASKED_ON).mentions == 0


@pytest.mark.parametrize("share", [-0.1, 1.1])
def test_the_dropped_share_is_a_fraction(share: float) -> None:
    with pytest.raises(ValueError, match="max_dropped_share"):
        FaithfulnessConfig(max_dropped_share=share)
