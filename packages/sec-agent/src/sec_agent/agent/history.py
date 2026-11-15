"""What the model is shown of a conversation: this turn whole, earlier turns in brief.

A turn starts at a user message. Earlier turns keep the question and the final answer
only: their tool calls and results are dropped, which bounds the prompt, and a number in
a follow-up answer has to come from a tool result of its own turn.
"""

from collections.abc import Sequence

from sec_agent.llm.messages import Message


def model_messages(messages: Sequence[Message], *, max_history_turns: int) -> list[Message]:
    turns = _turns(messages)
    if not turns:
        return []
    *earlier, current = turns
    kept = earlier[-max_history_turns:] if max_history_turns > 0 else []
    shown: list[Message] = []
    for turn in kept:
        shown.extend(_brief(turn))
    shown.extend(current)
    return shown


def _turns(messages: Sequence[Message]) -> list[list[Message]]:
    turns: list[list[Message]] = []
    for message in messages:
        if message["role"] == "user" or not turns:
            turns.append([])
        turns[-1].append(message)
    return turns


def _brief(turn: list[Message]) -> list[Message]:
    """The question, and the answer if the turn got one (a turn cut short has none)."""
    question, last = turn[0], turn[-1]
    answered = (
        len(turn) > 1
        and last["role"] == "assistant"
        and bool(last["content"])
        and not last.get("tool_calls")
    )
    return [question, last] if answered else [question]
