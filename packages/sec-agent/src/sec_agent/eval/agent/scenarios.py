"""A1 scenarios and the transcript a system leaves for one.

A scenario is one or more user turns and the checks its last answer must pass. Checks name
what code can verify: which tool was called and how the tool resolved its arguments (read
from the result, so "Home Depot" and "HD" are the same company), which result field a
shown figure must trace to, whether a valid citation is given, and text the answer must or
must not contain. Expected figures are never written in a scenario: they are whatever the
named tool returns, so a scenario cannot hold a number the tools did not produce.
"""

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal, Self, cast, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from sec_agent.agent.answer import Evidence, Status
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.golden.split import CompanySplitName

_FROZEN = ConfigDict(frozen=True, extra="forbid")

Category = Literal[
    "value",
    "fiscal_period",
    "growth",
    "ratio",
    "peers",
    "text",
    "risk_diff",
    "follow_up",
    "out_of_scope",
    "advice",
    "not_reported",
    "non_gaap",
]
CATEGORIES: tuple[Category, ...] = get_args(Category)
Scalar = str | int | bool | None


class ToolCheck(BaseModel):
    """A call the turn must hold: of `tool` (None: any tool), succeeded or refused as `ok`
    says, whose result has every `match` value. A `match` key is a dotted path into the
    result JSON; `*` stands for any element of a list ("rows.*.company.ticker"). With
    `figure`, the shown answer must state a figure that traced to a field of such a call
    whose path fully matches the regex (e.g. r"fact\\.value")."""

    model_config = _FROZEN

    tool: str | None = None
    match: dict[str, Scalar] = Field(default_factory=dict[str, Scalar])
    figure: str | None = None
    ok: bool = True
    call: dict[str, Scalar | list[str]] | None = None
    """The arguments of the call that answers the check. The scorer runs it itself (the
    oracle) to judge a system that does not offer `tool`, such as the RAG baseline: that
    system passes when it states the oracle's figure from a passage it cites."""

    @field_validator("match")
    @classmethod
    def _one_list(cls, match: dict[str, Scalar]) -> dict[str, Scalar]:
        heads = {path.split(".*.", 1)[0] for path in match if "*" in path}
        for path in match:
            if "*" in path and (path.count("*") != 1 or ".*." not in path):
                raise ValueError(f"{path!r}: use one '*' between dots, e.g. rows.*.company.ticker")
        if len(heads) > 1:
            raise ValueError(f"wildcard paths must share one list, not {sorted(heads)}")
        return match

    @field_validator("figure")
    @classmethod
    def _regex(cls, figure: str | None) -> str | None:
        if figure is not None:
            _compile(figure)
        return figure


class Scenario(BaseModel):
    model_config = _FROZEN

    id: str = Field(pattern=r"^a1-\d{3}$")
    category: Category
    split: CompanySplitName
    companies: tuple[str, ...] = ()
    """Tickers the question is about; the RAG baseline searches these companies' text."""
    turns: tuple[str, ...] = Field(min_length=1)
    tools: tuple[ToolCheck, ...] = ()
    cite: bool = False
    """The answer must give at least one valid citation."""
    says: tuple[str, ...] = ()
    """Regexes the shown answer must each match (case-insensitive)."""
    not_says: tuple[str, ...] = ()
    """Regexes the shown answer must not match (case-insensitive)."""
    status: tuple[Status, ...] = ("answered",)
    notes: str = ""

    @field_validator("says", "not_says")
    @classmethod
    def _regexes(cls, patterns: tuple[str, ...]) -> tuple[str, ...]:
        for pattern in patterns:
            _compile(pattern)
        return patterns

    @model_validator(mode="after")
    def _checks_something(self) -> Self:
        if not (self.tools or self.cite or self.says or self.not_says):
            raise ValueError(f"scenario {self.id} checks nothing")
        return self


class Transcript(BaseModel):
    """What one system did for one scenario: the last turn's shown text and its evidence."""

    model_config = _FROZEN

    scenario_id: str
    system: str
    model: str
    scenario_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    text: str
    status: Status
    evidence: tuple[Evidence, ...]
    asked_on: dt.date
    answered_at: dt.datetime
    offered_tools: tuple[str, ...] | None = None
    """The tools the system could call; None: every tool of the catalog."""
    oracle: tuple[Evidence, ...] = ()
    """The checks' own calls (`ToolCheck.call`) as the scorer ran them, never shown to the
    system: the expected figures for a system without the tool."""


def scenario_sha256(scenario: Scenario, fingerprint: str) -> str:
    """The cache key of a scenario for a system: its turns and checks, and the system's
    fingerprint, so changing either asks again. The oracle's arguments (`ToolCheck.call`)
    are left out: they change how an answer is scored, never what a system is asked."""
    asked = scenario.model_dump_json(exclude={"tools": {"__all__": {"call"}}})
    payload = asked + "\n" + fingerprint
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_scenarios(path: Path) -> list[Scenario]:
    scenarios = read_jsonl(path, Scenario)
    seen: set[str] = set()
    for s in scenarios:
        if s.id in seen:
            raise ValueError(f"{path} lists scenario {s.id} twice")
        seen.add(s.id)
    return scenarios


def result_values(result: str, path: str) -> list[Any]:
    """Every value at the dotted `path` of a tool result's JSON; `*` is any list element."""
    try:
        values: list[Any] = [json.loads(result)]
    except ValueError:
        return []
    for part in path.split("."):
        found: list[Any] = []
        for value in values:
            if part == "*" and isinstance(value, list):
                found.extend(cast(list[Any], value))
            elif isinstance(value, dict) and part in value:
                found.append(cast(dict[str, Any], value)[part])
        values = found
    return values


def matching_elements(result: str, path: str, expected: Scalar) -> set[str]:
    """The elements of the list before `*` ("rows.*.company.ticker") whose value at the rest
    of the path is `expected`, as the checker names fields: {"rows[1]"}."""
    head, tail = path.split(".*.", 1)
    found: set[str] = set()
    for rows in result_values(result, head):
        if not isinstance(rows, list):
            continue
        for i, row in enumerate(cast(list[Any], rows)):
            if expected in result_values(json.dumps(row), tail):
                found.add(f"{head}[{i}]")
    return found


def _compile(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as error:
        raise ValueError(f"not a valid regex {pattern!r}: {error}") from None
