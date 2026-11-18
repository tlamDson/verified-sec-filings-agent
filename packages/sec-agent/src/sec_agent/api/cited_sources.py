"""cited_sources: the citations an answer's Sources panel lists.

A search returns its top passages whether or not they bear on the question, so next to a
figure card most of them are noise (a net income answer listing a passage on gross
margin). When the turn shows a figure (fact, ratio or peer card), the panel lists the
filings behind it and only the passages the answer text cites. A turn with no figure is a
text question, and every passage it found stays listed.
"""

from sec_agent.api.cards import EvidenceView, FactCard, PeersCard, RatioCard
from sec_agent.faithfulness.patterns import CITATION_KEY

_FIGURES = (FactCard, RatioCard, PeersCard)


def cited_sources(view: EvidenceView, text: str) -> EvidenceView:
    if not any(isinstance(card, _FIGURES) for card in view.cards):
        return view
    cited = {match.group(0) for match in CITATION_KEY.finditer(text)}
    kept = tuple(c for c in view.citations if c.kind != "passage" or c.key in cited)
    return view.model_copy(update={"citations": kept})
