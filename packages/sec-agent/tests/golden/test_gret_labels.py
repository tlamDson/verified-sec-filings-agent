"""G-ret labels: append-only, last label wins, stale labels ignored, qrels; blind session."""

import datetime as dt
from collections.abc import Iterator

import pytest

from sec_agent.golden.gret.labels import current_labels, pending_items, qrels_lines
from sec_agent.golden.gret.models import ChunkRef, Label, PoolItem, RetQuestion
from sec_agent.golden.gret.session import label_session

ACC = "9999999999-25-000008"
NOW = dt.datetime(2026, 11, 13, 9, 0, tzinfo=dt.UTC)


def _item(qid: str, ordinal: int, sha: str = "a") -> PoolItem:
    return PoolItem(
        qid=qid,
        ticker="SIMW",
        index_version="v1",
        chunk=ChunkRef(accession=ACC, section="mdna", ordinal=ordinal),
        systems=("bm25", "hybrid"),
        best_rank=ordinal + 1,
        text=f"Simulated passage {ordinal}.",
        text_sha256=sha * 64,
    )


def _label(item: PoolItem, grade: int, *, sha: str | None = None, minute: int = 0) -> Label:
    return Label.model_validate(
        {
            "qid": item.qid,
            "docid": item.docid,
            "grade": grade,
            "text_sha256": sha or item.text_sha256,
            "labeled_at": NOW + dt.timedelta(minutes=minute),
        }
    )


QUESTIONS = {
    "q-001": RetQuestion(
        id="q-001", ticker="SIMW", question="What drives costs?", written_on=dt.date(2026, 11, 1)
    )
}


def test_grades_are_zero_one_or_two() -> None:
    with pytest.raises(ValueError, match="grade"):
        _label(_item("q-001", 0), 3)


def test_the_latest_label_of_a_chunk_wins() -> None:
    item = _item("q-001", 0)
    labels = [_label(item, 2), _label(item, 0, minute=5)]
    assert current_labels(labels)[("q-001", item.docid)].grade == 0


def test_pending_items_are_those_without_a_label_for_the_same_text() -> None:
    a, b, c = _item("q-001", 0), _item("q-001", 1), _item("q-001", 2)
    labels = [_label(a, 1), _label(b, 2, sha="b" * 64)]  # b's text changed since: stale
    assert pending_items([a, b, c], labels) == [b, c]


def test_qrels_hold_current_labels_of_pool_items_only() -> None:
    a, b = _item("q-001", 0), _item("q-001", 1)
    outside = _item("q-001", 9)
    labels = [_label(a, 2), _label(b, 0), _label(outside, 1)]
    assert qrels_lines([a, b], labels) == [f"q-001 0 {a.docid} 2", f"q-001 0 {b.docid} 0"]


class Console:
    """Scripted answers in, everything shown kept."""

    def __init__(self, answers: list[str]) -> None:
        self._answers: Iterator[str] = iter(answers)
        self.shown: list[str] = []

    def ask(self, prompt: str) -> str:
        self.shown.append(prompt)
        try:
            return next(self._answers)
        except StopIteration:
            raise EOFError from None

    def show(self, text: str) -> None:
        self.shown.append(text)


def test_session_saves_each_grade_at_once_and_stops_on_quit() -> None:
    items = [_item("q-001", n) for n in range(3)]
    console, saved = Console(["2", "q"]), list[Label]()
    result = label_session(
        items, QUESTIONS, ask=console.ask, show=console.show, save=saved.append, now=lambda: NOW
    )
    assert [(lbl.docid, lbl.grade) for lbl in saved] == [(items[0].docid, 2)]
    assert saved[0].labeled_at == NOW
    assert saved[0].text_sha256 == items[0].text_sha256
    assert (result.labelled, result.skipped, result.stopped) == (1, 0, True)


def test_session_skips_reprompts_bad_input_and_stops_at_end_of_input() -> None:
    items = [_item("q-001", n) for n in range(3)]
    console, saved = Console(["s", "7", "x", "1"]), list[Label]()
    result = label_session(
        items, QUESTIONS, ask=console.ask, show=console.show, save=saved.append, now=lambda: NOW
    )
    assert [(lbl.docid, lbl.grade) for lbl in saved] == [(items[1].docid, 1)]
    assert (result.labelled, result.skipped, result.stopped) == (1, 1, True)


def test_session_shows_question_and_text_but_never_systems_or_ranks() -> None:
    items = [_item("q-001", 4)]
    console = Console(["0"])
    label_session(
        items, QUESTIONS, ask=console.ask, show=console.show, save=lambda _: None, now=lambda: NOW
    )
    screen = "\n".join(console.shown)
    assert "What drives costs?" in screen
    assert "Simulated passage 4." in screen
    assert "SIMW" in screen
    assert "[1/1]" in screen
    assert "bm25" not in screen
    assert "hybrid" not in screen
    assert "rank" not in screen.lower()
