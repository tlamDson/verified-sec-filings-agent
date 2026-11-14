"""Whether a cited sentence says the opposite of the passage it restates.

Sharing words with a passage (`grounding`) does not make a sentence agree with it:
"does not depend on a single supplier" shares every content word with "we depend on a
single supplier". A source sentence the whole sentence restates (`MIN_SHARED` content words)
is the anchor. Both sides are split into clauses (commas, ";", ":", "which", "but", "and"...);
a clause of the sentence is compared with each anchor clause it shares `MIN_CLAUSE` content
words with. They contradict when exactly one is negated ("not", "no", "never", "without",
"fail to", "lack"...), or when each holds one side of an opposite pair ("increase" and
"decrease", "rise" and "fall"). A differing figure is not judged here: the faithfulness
checker already fails a figure that no cited text holds. Code decides it, never a model.
"""

import re
from collections.abc import Iterable

from sec_agent.eval.agent.grounding import MIN_SHARED, stems

MIN_CLAUSE = 3
_SENTENCE = re.compile(r"(?<=[.;:!?])\s+")
_CLAUSE = re.compile(r"[,;:]|\s(?:which|but|although|while|whereas|and)\s|(?<=[.!?])\s+", re.I)
_CITATION = re.compile(r"\[[^\]]*\]")
_WORD = re.compile(r"[a-z']+")
_NEGATION = re.compile(
    r"\b(?:not|no|never|neither|nor|none|nothing|without|cannot|unable|unlikely|lack\w*"
    r"|fail(?:s|ed|ing)?\s+to|failure\s+to|den(?:y|ies|ied)|cease[sd]?)\b|n't\b",
    re.IGNORECASE,
)
_OPPOSITES: tuple[tuple[frozenset[str], frozenset[str]], ...] = tuple(
    (frozenset(a.split()), frozenset(b.split()))
    for a, b in (
        ("increase increased increases increasing rise rose rising grew grow grows"
         " higher greater expand expanded expands improve improved improves",
         "decrease decreased decreases decreasing fall fell falling declined decline declines"
         " lower lesser shrink shrank worsen worsened"),
        ("added adds adding introduced introduces", "removed removes removing eliminated"),
        ("allow allows allowed permit permits permitted", "prohibit prohibits prohibited forbid"),
        ("sufficient adequate", "insufficient inadequate"),
    )
)  # fmt: skip


def negated(text: str) -> bool:
    return _NEGATION.search(_CITATION.sub(" ", text)) is not None


def _opposed(a: str, b: str) -> bool:
    left, right = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    return any(
        (left & x and right & y and not left & y and not right & x)
        or (left & y and right & x and not left & x and not right & y)
        for x, y in _OPPOSITES
    )


def _clauses(text: str) -> list[tuple[str, frozenset[str]]]:
    return [(c, stems(c)) for c in _CLAUSE.split(_CITATION.sub(" ", text))]


def contradicts(sentence: str, source: str) -> bool:
    """Whether a clause of `sentence` and a clause of a source sentence it restates differ in
    negation or hold opposite words (clauses sharing fewer than `MIN_CLAUSE` words are not
    judged)."""
    whole = stems(sentence)
    said = _clauses(sentence)
    for anchor in _SENTENCE.split(source):
        if len(whole & stems(anchor)) < MIN_SHARED:
            continue
        for part, part_stems in said:
            for clause, clause_stems in _clauses(anchor):
                if len(part_stems & clause_stems) >= MIN_CLAUSE and (
                    negated(part) != negated(clause) or _opposed(part, clause)
                ):
                    return True
    return False


def contradicts_any(sentence: str, sources: Iterable[str]) -> bool:
    return any(contradicts(sentence, source) for source in sources)
