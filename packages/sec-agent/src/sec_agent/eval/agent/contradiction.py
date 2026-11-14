"""Whether a cited sentence says the opposite of the passage it restates.

Sharing words with a passage (`grounding`) does not make a sentence agree with it:
"does not depend on a single supplier" shares every content word with "we depend on a
single supplier". Both sides are split into clauses (sentence ends, commas, ";", ":",
"which", "but", "and"...). A clause of the sentence that shares `MIN_CLAUSE` content words
with the passage as a whole is judged, even when the passage spreads those words over
several of its sentences. It is compared with the passage clauses it shares the most words
with; it agrees when one of them has the same negation ("not", "no", "never", "without",
"fail to", "lack"...) and no opposite word ("increase" and "decrease", "rise" and "fall"),
and contradicts otherwise. "Not only", "not just", "not limited to" and "without
limitation" are not negations. A differing figure is not judged here: the faithfulness
checker already fails a figure that no cited text holds. Code decides it, never a model.
"""

import re
from collections.abc import Iterable

from sec_agent.eval.agent.grounding import stems

MIN_CLAUSE = 3
_CLAUSE = re.compile(r"[,;:]|\s(?:which|but|although|while|whereas|and)\s|(?<=[.!?])\s+", re.I)
_CITATION = re.compile(r"\[[^\]]*\]")
_WORD = re.compile(r"[a-z']+")
_NOT_NEGATION = re.compile(
    r"\b(?:not|no)\s+(?:only|just|merely|simply|least|limited\s+to)\b|\bwithout\s+limitation\b",
    re.IGNORECASE,
)
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
    return _NEGATION.search(_NOT_NEGATION.sub(" ", _CITATION.sub(" ", text))) is not None


def _opposed(a: str, b: str) -> bool:
    left, right = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    return any(
        (left & x and right & y and not left & y and not right & x)
        or (left & y and right & x and not left & x and not right & y)
        for x, y in _OPPOSITES
    )


def _clauses(text: str) -> list[tuple[str, frozenset[str]]]:
    return [(c, stems(c)) for c in _CLAUSE.split(_CITATION.sub(" ", text))]


def _clause_contradicts(part: str, part_stems: frozenset[str], source: str) -> bool:
    clauses = [(c, len(part_stems & cs)) for c, cs in _clauses(source)]
    best = max((n for _, n in clauses), default=0)
    return not any(
        n == best and negated(c) == negated(part) and not _opposed(part, c) for c, n in clauses
    )


def contradicts(sentence: str, source: str) -> bool:
    """Whether a clause of `sentence` sharing `MIN_CLAUSE` words with `source` disagrees, in
    negation or by an opposite word, with every source clause it shares the most words with."""
    whole = stems(source)
    return any(
        len(part_stems & whole) >= MIN_CLAUSE and _clause_contradicts(part, part_stems, source)
        for part, part_stems in _clauses(sentence)
    )


def contradicts_any(sentence: str, sources: Iterable[str]) -> bool:
    """Whether `sentence` contradicts one cited source, or all of them read together."""
    texts = list(sources)
    return any(contradicts(sentence, t) for t in texts) or (
        len(texts) > 1 and contradicts(sentence, " ".join(texts))
    )
