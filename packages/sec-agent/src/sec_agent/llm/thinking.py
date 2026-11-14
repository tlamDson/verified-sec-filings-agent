"""Whether the model thinks before it answers, set per role.

llama.cpp passes `chat_template_kwargs` to the model's chat template; for Qwen,
`enable_thinking` switches the hidden reasoning on or off. Left unset, the server's own
default applies (thinking on, up to its token budget), which is what every call did
before this setting existed.
"""

from typing import get_args

from pydantic import BaseModel, ConfigDict, StrictBool

from sec_agent.llm.messages import LLMRole


class ThinkingSettings(BaseModel):
    """None: send nothing. True or False: send `enable_thinking` with that value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: StrictBool | None = None
    """The call that writes the answer shown to the user (b0, b1, and the agent's last call)."""
    tool_choice: StrictBool | None = None
    """An agent call that may ask for tools."""
    judge: StrictBool | None = None
    """A model grading another model's output."""
    guardrail: StrictBool | None = None
    """A model screening a question or a passage."""

    def for_role(self, role: LLMRole) -> bool | None:
        return getattr(self, role)

    def label(self) -> str:
        """The roles that are set, e.g. "answer=off tool_choice=on"; empty when none is."""
        parts: list[str] = []
        for role in get_args(LLMRole):
            value = self.for_role(role)
            if value is not None:
                parts.append(f"{role}={'on' if value else 'off'}")
        return " ".join(parts)
