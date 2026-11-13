"""Load G-ret questions: unique ids, each about a company of the test split."""

from pathlib import Path

from sec_agent.golden.gret.models import RetQuestion
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.golden.split import CompanySplit

TARGET_QUESTIONS = 100
"""The plan asks for at least this many (gate G-F2); fewer is allowed while writing."""


def load_questions(path: Path, split: CompanySplit) -> list[RetQuestion]:
    questions = read_jsonl(path, RetQuestion)
    seen: set[str] = set()
    for q in questions:
        if q.id in seen:
            raise ValueError(f"duplicate question id {q.id!r}")
        seen.add(q.id)
        company = split.by_ticker(q.ticker)
        if company is None or company.split != "test":
            raise ValueError(f"question {q.id!r} is about {q.ticker}, not a test split company")
    return questions
