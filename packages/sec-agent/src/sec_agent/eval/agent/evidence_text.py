"""The citations a sentence gives, and the filing text the turn's evidence holds."""

from typing import Any, cast

from sec_agent.agent.answer import Evidence
from sec_agent.eval.agent.contradiction import contradicts_any
from sec_agent.eval.agent.grounding import restates
from sec_agent.eval.agent.scenarios import result_values
from sec_agent.faithfulness.models import SentenceCheck

ANYWHERE = frozenset({""})


def cited(sentence: SentenceCheck) -> set[str]:
    """The valid citation keys of the sentence."""
    return {c.key for c in sentence.citations if c.status == "valid"}


def cites_any(keys: set[str], accessions: set[str]) -> bool:
    """Whether a key cites one of the filings (`accession` or `accession/section/n`)."""
    return any(k.split("/", 1)[0] in accessions for k in keys)


def restates_cited(sentence: SentenceCheck, texts: dict[str, str]) -> bool:
    """Whether the sentence restates a passage of `texts` (key -> text) that it cites, and
    contradicts none of the cited passages."""
    sources = [texts[k] for k in cited(sentence) if k in texts]
    return restates(sentence.text, sources) and not contradicts_any(sentence.text, sources)


def passage_texts(
    evidence: Evidence, scope: frozenset[str] | set[str] = ANYWHERE
) -> dict[str, str]:
    """Citation key -> text of a search result's passages in `scope`: {""} all of them, or
    the elements a check matched ("passages[1]")."""
    found: dict[str, str] = {}
    for passages in result_values(evidence.result, "passages"):
        if not isinstance(passages, list):
            continue
        for i, passage in enumerate(cast(list[Any], passages)):
            if ("" in scope or f"passages[{i}]" in scope) and isinstance(passage, dict):
                key = cast(dict[str, Any], passage).get("citation")
                text = cast(dict[str, Any], passage).get("text")
                if isinstance(key, str) and isinstance(text, str):
                    found[key] = text
    return found
