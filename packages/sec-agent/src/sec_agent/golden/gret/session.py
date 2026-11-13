"""The labelling loop: one pooled chunk at a time, blind to systems and their order.

Each grade is saved the moment it is given, so quitting or a crash loses nothing. Input:
0, 1 or 2 grades the chunk, `s` skips it, `q` quits; anything else asks again.
"""

import datetime as dt
from collections.abc import Callable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from sec_agent.golden.gret.models import Grade, Label, PoolItem, RetQuestion

PROMPT = "grade 0 (not relevant), 1 (partly), 2 (answers it); s skip; q quit: "
_GRADES: dict[str, Grade] = {"0": 0, "1": 1, "2": 2}


class SessionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    labelled: int
    skipped: int
    stopped: bool
    """True when the labeller quit or input ended before the last chunk."""


def _screen(item: PoolItem, question: RetQuestion, n: int, total: int) -> str:
    rule = "-" * 72
    return (
        f"{rule}\n[{n}/{total}] {question.id} | {item.ticker}\n"
        f"Q: {question.question}\n{rule}\n{item.text}\n{rule}"
    )


def label_session(
    items: Sequence[PoolItem],
    questions: Mapping[str, RetQuestion],
    *,
    ask: Callable[[str], str],
    show: Callable[[str], None],
    save: Callable[[Label], None],
    now: Callable[[], dt.datetime],
) -> SessionResult:
    labelled = skipped = 0
    for n, item in enumerate(items, start=1):
        show(_screen(item, questions[item.qid], n, len(items)))
        while True:
            try:
                answer = ask(PROMPT).strip().lower()
            except EOFError:
                return SessionResult(labelled=labelled, skipped=skipped, stopped=True)
            if answer == "q":
                return SessionResult(labelled=labelled, skipped=skipped, stopped=True)
            if answer == "s":
                skipped += 1
                break
            grade = _GRADES.get(answer)
            if grade is None:
                show("please answer 0, 1, 2, s or q")
                continue
            save(
                Label(
                    qid=item.qid,
                    docid=item.docid,
                    grade=grade,
                    text_sha256=item.text_sha256,
                    labeled_at=now(),
                )
            )
            labelled += 1
            break
    return SessionResult(labelled=labelled, skipped=skipped, stopped=False)
