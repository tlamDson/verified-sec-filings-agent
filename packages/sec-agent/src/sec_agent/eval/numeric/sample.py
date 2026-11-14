"""A short night's questions: N of a split, shared across question types in turn.

G-num files list questions type by type, so the first N in file order can hold only one or
two types (the first night's 100 were 60 `value` and 40 `yoy_growth`). `stratified` takes
the types in turn, each in file order: N = 100 over five types is 20 of each, and a later,
longer night keeps every question of a shorter one, so cached answers are reused.
"""

from collections.abc import Sequence

from sec_agent.golden.gnum.models import NumQuestion, QuestionType


def stratified(questions: Sequence[NumQuestion], n: int) -> list[NumQuestion]:
    if n < 0:
        raise ValueError("the limit must not be negative")
    by_type: dict[QuestionType, list[NumQuestion]] = {}
    for q in questions:
        by_type.setdefault(q.qtype, []).append(q)
    chosen: set[str] = set()
    depth = 0
    while len(chosen) < min(n, len(questions)):
        for group in by_type.values():
            if depth < len(group) and len(chosen) < n:
                chosen.add(group[depth].id)
        depth += 1
    return [q for q in questions if q.id in chosen]
