"""What the model is shown of a conversation: this turn whole, earlier turns in brief."""

from llm_fakes import call, calls, says

from sec_agent.agent.history import model_messages
from sec_agent.llm.messages import Message, tool_result, user


def _turn(n: int) -> list[Message]:
    return [
        user(f"question {n}"),
        calls(call("get_fact", f"c{n}")),
        tool_result(f"c{n}", f"result {n}"),
        says(f"answer {n}"),
    ]


def test_the_current_turn_is_shown_whole() -> None:
    turn = _turn(1)[:3]
    assert model_messages(turn, max_history_turns=4) == turn


def test_earlier_turns_keep_only_the_question_and_the_final_answer() -> None:
    messages = [*_turn(1), *_turn(2), *_turn(3)[:3]]
    assert model_messages(messages, max_history_turns=4) == [
        user("question 1"),
        says("answer 1"),
        user("question 2"),
        says("answer 2"),
        *_turn(3)[:3],
    ]


def test_only_the_latest_earlier_turns_are_kept() -> None:
    messages = [*_turn(1), *_turn(2), *_turn(3), user("question 4")]
    assert model_messages(messages, max_history_turns=2) == [
        user("question 2"),
        says("answer 2"),
        user("question 3"),
        says("answer 3"),
        user("question 4"),
    ]
    assert model_messages(messages, max_history_turns=0) == [user("question 4")]


def test_an_earlier_turn_without_an_answer_keeps_its_question() -> None:
    messages = [user("question 1"), user("question 2")]
    assert model_messages(messages, max_history_turns=4) == messages


def test_no_messages_give_no_messages() -> None:
    assert model_messages([], max_history_turns=4) == []
