"""quarantine: filing text is data, so a sentence of it that gives orders to an AI is
replaced by a fixed mark before the model reads it (indirect prompt injection).

Only the text tools carry filing text: the passages of `search_filings` and the risk-factor
paragraphs of `diff_risk_factors`. A result with nothing flagged is returned byte for
byte; otherwise it is the same result with those sentences replaced, so the model and the
faithfulness checker read one text. Character offsets still point into the filing.
"""

from dataclasses import dataclass

from pydantic import ValidationError

from sec_agent.faithfulness.sentences import split_sentences
from sec_agent.guardrails.patterns import INJECTION, first_match
from sec_agent.tools.risk_factors import RiskChange, RiskDiffResult
from sec_agent.tools.search_filings import Passage, SearchResult

REMOVED_MARK = "[removed: this sentence of the filing addressed instructions to an AI]"


@dataclass(frozen=True)
class Quarantined:
    content: str
    flagged: int
    """Sentences replaced by `REMOVED_MARK`."""


def quarantine(tool_name: str, content: str) -> Quarantined:
    try:
        if tool_name == "search_filings":
            return _search(SearchResult.model_validate_json(content), content)
        if tool_name == "diff_risk_factors":
            return _risks(RiskDiffResult.model_validate_json(content), content)
    except ValidationError:  # a refusal, not a result: it holds no filing text
        pass
    return Quarantined(content, 0)


def clean_text(text: str) -> tuple[str, int]:
    """`text` with each sentence that matches an injection rule replaced by the mark."""
    parts: list[str] = []
    flagged = 0
    for sentence in split_sentences(text):
        piece = text[sentence.start : sentence.end]
        if first_match(piece.strip(), INJECTION) is None:
            parts.append(piece)
        else:
            flagged += 1
            parts.append(REMOVED_MARK + piece[len(piece.rstrip()) :])
    return ("".join(parts), flagged) if flagged else (text, 0)


def _search(result: SearchResult, content: str) -> Quarantined:
    flagged = 0
    passages: list[Passage] = []
    for passage in result.passages:
        text, count = clean_text(passage.text)
        flagged += count
        passages.append(passage.model_copy(update={"text": text}) if count else passage)
    if not flagged:
        return Quarantined(content, 0)
    cleaned = result.model_copy(update={"passages": tuple(passages)})
    return Quarantined(cleaned.model_dump_json(), flagged)


def _risks(result: RiskDiffResult, content: str) -> Quarantined:
    flagged = 0
    changes: list[RiskChange] = []
    for change in result.changes:
        update: dict[str, str] = {}
        for field in ("text", "previous_text"):
            value: str | None = getattr(change, field)
            if value is not None:
                text, count = clean_text(value)
                if count:
                    flagged += count
                    update[field] = text
        changes.append(change.model_copy(update=update) if update else change)
    if not flagged:
        return Quarantined(content, 0)
    cleaned = result.model_copy(update={"changes": tuple(changes)})
    return Quarantined(cleaned.model_dump_json(), flagged)
