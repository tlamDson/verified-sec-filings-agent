"""Whether a cited sentence says the opposite of the passage it restates.

Sharing words with a passage (`grounding`) does not make a sentence agree with it:
"does not depend on a single supplier" shares every content word with "we depend on a
single supplier". Both sides are split into clauses (sentence ends, commas, ";", ":",
"which", "but", "and"...). A clause of the sentence that shares `MIN_CLAUSE` content words
with the passage as a whole is judged, even when the passage spreads those words over
several of its sentences. A negation's whole scope (up to the end of its clause, across the
commas and "or" of a list it governs, and through a list it introduces with ":") is judged
as one more clause on both sides, so "not on a vendor, or a single supplier" and "none of
the following: a vendor, or a single supplier" stay negated. A clause is compared with the
passage clauses it shares the most words with; it agrees when one of them has the same
negation ("not", "no", "never", "without", "fail to", "lack"...) and no opposite word
("increase" and "decrease", "rise" and "fall"), and contradicts otherwise. "Not only",
"not just", "not limited to" and "without limitation" are not negations. A differing
figure is not judged here: the faithfulness checker already fails a figure that no cited
text holds. Code decides it, never a model.
"""

import re
from collections.abc import Iterable

from sec_agent.eval.agent.grounding import stems

MIN_CLAUSE = 3
_CLAUSE = re.compile(r"[,;:]|\s(?:which|but|although|while|whereas|and)\s|(?<=[.!?])\s+", re.I)
_SCOPE_END = re.compile(
    r"[.;:!?]|\s(?:which|but|although|while|whereas|because|since)\s|,\s*(?:and|but)\s", re.I
)
_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")
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


def _negation_scopes(text: str) -> list[str]:
    """Each negation with the words it governs: up to the end of its clause, across the
    commas and "or" of a list ("not on a vendor, a carrier, or a single supplier"). A list
    the clause introduces with ":" is governed, with the whole clause, to the end of its
    sentence ("we depend on none of the following: a vendor; or a supplier")."""
    clean = _NOT_NEGATION.sub(" ", text)
    scopes: list[str] = []
    for cue in _NEGATION.finditer(clean):
        start = cue.start()
        rest = clean[start:]
        end = _SCOPE_END.search(rest)
        if end and end.group() == ":":
            start = max((m.end() for m in _CLAUSE.finditer(clean, 0, start)), default=0)
            rest = clean[start:]
            end = _SENTENCE_END.search(rest, cue.start() - start)
        scopes.append(rest[: end.start()] if end else rest)
    return scopes


def _clauses(text: str) -> list[tuple[str, frozenset[str]]]:
    clean = _CITATION.sub(" ", text)
    parts = _CLAUSE.split(clean) + _negation_scopes(clean)
    return [(c, stems(c)) for c in parts]


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
