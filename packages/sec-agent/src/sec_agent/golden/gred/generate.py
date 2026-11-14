"""generate_gred: the G-red items, in a fixed order, from `templates` and one seed.

The seed picks the markers and which simulated passages go with which question; the
templates fix everything else. `sec-agent golden gred` writes the result to
`data/golden/g_red.jsonl`, and a test checks the committed file is this output.
"""

import random
from collections.abc import Iterator

from sec_agent.golden.gred import templates as tpl
from sec_agent.golden.gred.models import RedGoal, RedItem, RedKind

DEFAULT_SEED = 20261113
_INDIRECT_PER_TOPIC = 4


def generate_gred(seed: int = DEFAULT_SEED) -> list[RedItem]:
    rng = random.Random(seed)
    items = [*_direct(rng), *_indirect(rng), *_advice(), *_benign(rng)]
    counts: dict[RedKind, int] = {}
    numbered: list[RedItem] = []
    for item in items:
        counts[item.kind] = counts.get(item.kind, 0) + 1
        numbered.append(item.model_copy(update={"id": f"gred-{item.kind}-{counts[item.kind]:03d}"}))
    return numbered


def _marker(rng: random.Random) -> str:
    return f"{rng.choice(tpl.MARKER_WORDS)}-{rng.randrange(10, 100)}"


def _item(
    kind: RedKind, goal: RedGoal | None, question: str, company: str, **extra: object
) -> RedItem:
    return RedItem.model_validate(
        {"id": "-", "kind": kind, "goal": goal, "question": question, "company": company, **extra}
    )


def _direct(rng: random.Random) -> Iterator[RedItem]:
    for template in tpl.DIRECT_MARKER:
        for ticker, name in tpl.COMPANIES:
            marker = _marker(rng)
            question = template.format(m=marker, t=ticker, name=name)
            yield _item("direct", "marker", question, ticker, marker=marker)
    for template in tpl.DIRECT_LEAK:
        for ticker, name in tpl.COMPANIES:
            yield _item("direct", "leak", template.format(t=ticker, name=name), ticker)


def _indirect(rng: random.Random) -> Iterator[RedItem]:
    goals: list[tuple[RedGoal, str]] = [
        *(("marker", t) for t in tpl.INDIRECT_MARKER),
        *(("advice", t) for t in tpl.INDIRECT_ADVICE),
        *(("leak", t) for t in tpl.INDIRECT_LEAK),
    ]
    index = 0
    for ticker, name in tpl.COMPANIES:
        topics = tpl.INDIRECT_TOPICS[ticker]
        for topic, clean in topics:
            for _ in range(_INDIRECT_PER_TOPIC):
                goal, template = goals[index % len(goals)]
                index += 1
                marker = _marker(rng) if goal == "marker" else None
                injected = f"{clean} {template.format(m=marker, t=ticker)}"
                other = rng.choice([text for t, text in topics if t != topic])
                passages = [injected, other]
                rng.shuffle(passages)
                question = tpl.BENIGN_TEXT[index % len(tpl.BENIGN_TEXT)].format(
                    name=name, topic=topic
                )
                yield _item(
                    "indirect", goal, question, ticker, passages=tuple(passages), marker=marker
                )


def _advice() -> Iterator[RedItem]:
    for template in tpl.ADVICE:
        for ticker, name in tpl.COMPANIES:
            yield _item("advice", "advice", template.format(t=ticker, name=name), ticker)


def _benign(rng: random.Random) -> Iterator[RedItem]:
    for template in tpl.BENIGN_NUMERIC:
        for ticker, name in tpl.COMPANIES:
            for year in tpl.BENIGN_YEARS:
                yield _item("benign", None, template.format(name=name, y=year), ticker)
    for template in tpl.BENIGN_TEXT:
        for ticker, name in tpl.COMPANIES:
            for topic, clean in tpl.INDIRECT_TOPICS[ticker]:
                passages = [clean, rng.choice(tpl.BENIGN_PASSAGES[ticker])]
                rng.shuffle(passages)
                question = template.format(name=name, topic=topic)
                yield _item("benign", None, question, ticker, passages=tuple(passages))
    for template in tpl.BENIGN_TRICKY:
        for ticker, name in tpl.COMPANIES:
            yield _item("benign", None, template.format(name=name), ticker)
