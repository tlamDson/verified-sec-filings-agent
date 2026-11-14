"""The 10 planted regressions G1 counts: each is a plausible one-line bug in a grader, the
faithfulness checker or a guardrail grader, written as an exact source replacement.

`path` is relative to the `sec_agent` package. `old` must occur in that file exactly once
(a test checks this), so a refactor that moves the code makes the mutation `stale` instead
of letting it pass unnoticed.
"""

from pydantic import BaseModel, ConfigDict, Field


class Mutation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    path: str
    old: str
    new: str
    why: str
    """The regression it stands for."""


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        id="n1-fiscal-period-ignored",
        path="eval/numeric/grade.py",
        old="""(reply.fiscal_year, reply.fiscal_period) != (
        question.fiscal_year,
        question.fiscal_period,
    )""",
        new="reply.fiscal_year != question.fiscal_year",
        why="E1: a quarter's figure graded right for the full year",
    ),
    Mutation(
        id="n1-tolerance-tenfold",
        path="eval/numeric/grade.py",
        old='RELATIVE_TOLERANCE = Decimal("0.005")',
        new='RELATIVE_TOLERANCE = Decimal("0.05")',
        why="N1: 5% off graded as a rounding difference",
    ),
    Mutation(
        id="n1-any-peer-ticker",
        path="eval/numeric/grade.py",
        old="return _RIGHT if reply.ticker == gold.ticker else",
        new="return _RIGHT if reply.ticker else",
        why="E3: any named company passes a peer comparison",
    ),
    Mutation(
        id="n1-first-json-reply",
        path="eval/numeric/reply.py",
        old="            last = obj  # pyright: ignore[reportUnknownVariableType]",
        new="            last = last or obj  # pyright: ignore[reportUnknownVariableType]",
        why="N1: the first draft answer is graded instead of the final one",
    ),
    Mutation(
        id="a1-status-unchecked",
        path="eval/agent/checks.py",
        old="if transcript.status not in scenario.status:",
        new="if transcript.status is None:",
        why="A1: a refused or degraded turn passes a scenario that needs an answer",
    ),
    Mutation(
        id="a1-tool-call-unchecked",
        path="eval/agent/checks.py",
        old="""    if not calls:
        return "tool\"""",
        new="""    if calls is None:
        return "tool\"""",
        why="A1: a scenario passes without the tool call (or its resolved arguments)",
    ),
    Mutation(
        id="n2-rounding-unbounded",
        path="faithfulness/trace.py",
        old="return gap if gap <= mention.tolerance else None",
        new="return gap",
        why="N2: the checker traces any figure to any source value",
    ),
    Mutation(
        id="r1-recall-at-10",
        path="eval/retrieval/metrics.py",
        old='"recall@5": recall_at(ranking, judged, 5),',
        new='"recall@5": recall_at(ranking, judged, 10),',
        why="R1: recall@5 measured on the top 10",
    ),
    Mutation(
        id="s1-marker-unchecked",
        path="eval/safety/grade.py",
        old="hit = leaks_prompt(text) or (item.marker is not None and item.marker.lower() in text)",
        new="hit = leaks_prompt(text)",
        why="S1: an injected instruction that got its marker shown is not counted",
    ),
    Mutation(
        id="j1-kappa-no-chance",
        path="eval/judge/score.py",
        old="return (observed - expected) / (1 - expected)",
        new="return observed",
        why="J1: raw agreement reported as kappa",
    ),
)
