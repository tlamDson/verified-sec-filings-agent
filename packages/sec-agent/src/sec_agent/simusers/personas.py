"""The personas simulated accounts play: what they open with, how they follow up, how often
they rate a turn. Templates name `{company}`, `{peer}` and `{year}` only.

Some personas probe the edge-case rules on purpose: advice (E9), non-GAAP (E4), relative
periods (E6) and segment figures (E11).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PersonaName = Literal["analyst", "student", "journalist", "retail", "skeptic"]


class Persona(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: PersonaName
    openers: tuple[str, ...] = Field(min_length=1)
    follow_ups: tuple[str, ...] = Field(min_length=3)
    """At least three, so a session can ask up to three different ones."""
    max_sessions: int = Field(ge=1)
    """Sessions an account of this persona may start in one day."""
    rate_share: float = Field(ge=0, le=1)
    """How often a turn that meets the rating criteria is rated."""


PERSONAS: dict[PersonaName, Persona] = {
    p.name: p
    for p in (
        Persona(
            name="analyst",
            openers=(
                "What was {company}'s gross margin in fiscal {year}?",
                "Compare the operating margin of {company} and {peer} in fiscal {year}.",
                "What was {company}'s free cash flow in fiscal {year}?",
            ),
            follow_ups=(
                "How does that compare with {peer}?",
                "And the operating margin?",
                "Show the trend over the last 3 years.",
                "What was the debt to equity ratio?",
            ),
            max_sessions=2,
            rate_share=0.5,
        ),
        Persona(
            name="student",
            openers=(
                "What was {company}'s revenue in fiscal {year}?",
                "How much net income did {company} report for fiscal {year}?",
                "What were {company}'s total assets at the end of fiscal {year}?",
            ),
            follow_ups=(
                "What about net income?",
                "How much cash did they hold at year end?",
                "What does that figure include?",
                "And the year before?",
            ),
            max_sessions=1,
            rate_share=0.3,
        ),
        Persona(
            name="journalist",
            openers=(
                "What new risk factors did {company} add in its latest 10-K?",
                "What does {company}'s 10-K for fiscal {year} say about competition?",
            ),
            follow_ups=(
                "Which risk factors were removed?",
                "What does the filing say about the supply chain?",
                "Quote the passage on regulation.",
                "Does {peer} mention the same risk?",
            ),
            max_sessions=1,
            rate_share=0.4,
        ),
        Persona(
            name="retail",
            openers=(
                "Should I buy {company} stock?",
                "Is {company} a better investment than {peer}?",
            ),
            follow_ups=(
                "OK, then what was its revenue growth over the last 3 years?",
                "What was the net margin in fiscal {year}?",
                "How much debt does it have?",
            ),
            max_sessions=1,
            rate_share=0.6,
        ),
        Persona(
            name="skeptic",
            openers=(
                "What was {company}'s adjusted EBITDA in fiscal {year}?",
                "What was {company}'s revenue last quarter?",
                "What was the revenue of {company}'s largest segment in fiscal {year}?",
            ),
            follow_ups=(
                "And for {peer}?",
                "Where exactly in the filing is that?",
                "Is that figure restated anywhere?",
            ),
            max_sessions=1,
            rate_share=0.8,
        ),
    )
}
