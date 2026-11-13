"""Fixed texts the agent answers with when the model did not write the answer.

They hold no figure: whatever numbers a degraded answer shows are its tool results.
"""

DEGRADED_TEXT = (
    "The language model is unavailable right now, so this answer has no written "
    "explanation. Any figures and passages retrieved for your question are shown as "
    "returned by the tools. This is not investment advice."
)
STEP_LIMIT_TEXT = (
    "This question needed more lookups than one answer allows, so no answer was written. "
    "Any figures and passages retrieved so far are shown as returned by the tools. "
    "Try a narrower question. This is not investment advice."
)
