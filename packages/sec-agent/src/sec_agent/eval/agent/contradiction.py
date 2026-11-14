"""Whether a cited sentence says the opposite of the passage it restates.

Sharing words with a passage (`grounding`) does not make a sentence agree with it:
"does not depend on a single supplier" shares every content word with "we depend on a
single supplier". A clause of the sentence is compared with the clause of the source it
overlaps most (at least `MIN_SHARED` content words); the two contradict when exactly one is
negated ("not", "no", "never", "without", "n't"...). A differing figure is not judged here:
the faithfulness checker already fails a figure that no cited text holds. Code decides it,
never a model.
"""

import re
from collections.abc import Iterable

from sec_agent.eval.agent.grounding import MIN_SHARED, stems

_SOURCE_CLAUSE = re.compile(r"(?<=[.;:!?])\s+")
_SAID_CLAUSE = re.compile(
    r"[,;:]|\s(?:which|but|although|while|whereas|and)\s|(?<=[.!?])\s+", re.IGNORECASE
)
_NEGATION = re.compile(
    r"\b(?:not|no|never|neither|nor|none|nothing|without|cannot|unable)\b|n't\b", re.IGNORECASE
)
_CITATION = re.compile(r"\[[^\]]*\]")


def negated(text: str) -> bool:
    return _NEGATION.search(_CITATION.sub(" ", text)) is not None


def contradicts(sentence: str, source: str) -> bool:
    """Whether a clause of `sentence` and the clause of `source` it overlaps most differ in
    negation (a clause of fewer than `MIN_SHARED` shared words is not judged)."""
    source_clauses = [(c, stems(c)) for c in _SOURCE_CLAUSE.split(source)]
    for said in _SAID_CLAUSE.split(_CITATION.sub(" ", sentence)):
        words = stems(said)
        overlap, best = max(((len(words & w), c) for c, w in source_clauses), default=(0, ""))
        if overlap >= MIN_SHARED and negated(said) != negated(best):
            return True
    return False


def contradicts_any(sentence: str, sources: Iterable[str]) -> bool:
    return any(contradicts(sentence, source) for source in sources)
