"""Names a request may use for a number: canonical XBRL concepts, then ratios."""

from sec_agent.tools.errors import UnknownMetricError
from sec_agent.xbrl.concepts import CONCEPTS, Concept, concept

CONCEPT_NAMES: tuple[str, ...] = tuple(c.name for c in CONCEPTS)


def require_concept(name: str) -> Concept:
    try:
        return concept(name)
    except KeyError:
        raise UnknownMetricError(
            f"{name!r} is not one of the {len(CONCEPT_NAMES)} XBRL concepts the facts hold "
            "(non-GAAP measures such as adjusted EBITDA are not in XBRL; quote the filing "
            "text instead)"
        ) from None
