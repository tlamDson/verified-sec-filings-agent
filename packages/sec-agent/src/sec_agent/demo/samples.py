"""Pick sample answers from committed agent transcripts, with each citation and its passage.

Pure: takes parsed scenarios and transcripts, returns what the page shows. Only an answered
turn whose citations all resolve to a passage in its own evidence is a sample, so the page
never shows a citation it cannot back.
"""

import json
from collections.abc import Iterator, Sequence
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from sec_agent.agent.answer import Evidence
from sec_agent.eval.agent.evidence_text import passage_texts
from sec_agent.eval.agent.scenarios import Scenario, Transcript
from sec_agent.faithfulness.patterns import CITATION_KEY

_FROZEN = ConfigDict(frozen=True, extra="forbid")
SAMPLED_SYSTEM = "agent"


class CitedPassage(BaseModel):
    model_config = _FROZEN

    citation: str
    text: str


class ToolSource(BaseModel):
    """A tool call of the turn: what was asked and the filings its result links."""

    model_config = _FROZEN

    name: str
    arguments: str
    filing_urls: tuple[str, ...]


class Sample(BaseModel):
    model_config = _FROZEN

    scenario_id: str
    category: str
    earlier_turns: tuple[str, ...]
    """The turns before the question, for a follow-up that leans on them."""
    question: str
    answer: str
    passages: tuple[CitedPassage, ...]
    tools: tuple[ToolSource, ...]


def _urls(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in cast(dict[str, Any], node).items():
            if key == "filing_url" and isinstance(value, str):
                yield value
            else:
                yield from _urls(value)
    elif isinstance(node, list):
        for item in cast(list[Any], node):
            yield from _urls(item)


def _tool(evidence: Evidence) -> ToolSource:
    try:
        arguments = json.dumps(json.loads(evidence.arguments), sort_keys=True)
        result: Any = json.loads(evidence.result)
    except ValueError:
        arguments, result = evidence.arguments, None
    return ToolSource(
        name=evidence.name,
        arguments=arguments,
        filing_urls=tuple(dict.fromkeys(_urls(result))),
    )


def _cited_keys(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(0) for m in CITATION_KEY.finditer(text)))


def to_sample(scenario: Scenario, transcript: Transcript) -> Sample | None:
    """The sample for one turn, or None when it is not answered, has no source, or cites
    a passage its evidence does not hold."""
    if transcript.status != "answered" or not transcript.evidence:
        return None
    texts: dict[str, str] = {}
    for evidence in transcript.evidence:
        texts.update(passage_texts(evidence))
    keys = _cited_keys(transcript.text)
    if any(key not in texts for key in keys):
        return None
    tools = tuple(_tool(e) for e in transcript.evidence if e.ok and e.name != "search_filings")
    if not keys and not any(t.filing_urls for t in tools):
        return None
    return Sample(
        scenario_id=scenario.id,
        category=scenario.category,
        earlier_turns=scenario.turns[:-1],
        question=scenario.turns[-1],
        answer=transcript.text,
        passages=tuple(CitedPassage(citation=k, text=texts[k]) for k in keys),
        tools=tools,
    )


def pick_samples(
    scenarios: Sequence[Scenario],
    transcripts: Sequence[Transcript],
    limit: int = 10,
    cited_first: int = 3,
) -> list[Sample]:
    """Up to `limit` samples of the agent: first up to `cited_first` that cite filing
    passages, then the least-shown category each time, each in scenario order."""
    by_id = {s.id: s for s in scenarios}
    queues: dict[str, list[Sample]] = {}
    for transcript in sorted(transcripts, key=lambda t: t.scenario_id):
        scenario = by_id.get(transcript.scenario_id)
        if transcript.system != SAMPLED_SYSTEM or scenario is None:
            continue
        sample = to_sample(scenario, transcript)
        if sample is not None:
            queues.setdefault(sample.category, []).append(sample)
    everyone = [s for queue in queues.values() for s in queue]
    picked = sorted((s for s in everyone if s.passages), key=lambda s: s.scenario_id)
    picked = picked[: min(cited_first, limit)]
    for queue in queues.values():
        queue[:] = [s for s in queue if s not in picked]
    while len(picked) < limit and any(queues.values()):
        # The least-shown category next; ties keep scenario order.
        shown = [s.category for s in picked]
        category = min((c for c, q in queues.items() if q), key=shown.count)
        picked.append(queues[category].pop(0))
    return picked
