"""b2 on G-num: the agent with its tools and checker, asked through the same runner as b0/b1.

The model is simulated (scripted replies); the tools read the recorded Apple facts, so the
value the agent states is what SEC reported.
"""

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from agent_kit import agent_of
from llm_fakes import ScriptedProvider, call, calls, says

from sec_agent.eval.numeric.agent_model import AgentChatModel, AgentUnavailableError
from sec_agent.eval.numeric.baselines import B0, B2, REPLY_FORMAT
from sec_agent.eval.numeric.grade import grade
from sec_agent.eval.numeric.reply import parse_reply
from sec_agent.eval.numeric.runner import AnswerRecord, cache_path, run_numeric
from sec_agent.golden.gnum.models import NumberAnswer, NumQuestion
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.llm.errors import ProviderUnavailableError
from sec_agent.tools.context import FactsContext

ASKED_ON = dt.date(2026, 11, 13)
NOW = dt.datetime(2026, 11, 13, 1, 0, tzinfo=dt.UTC)
REVENUE = call("get_fact", "c1", company="AAPL", concept="revenue", fiscal_year=2024)
TRACED = (
    "SIMULATED: Apple's revenue for fiscal 2024 (ended 2024-09-28) was $391.0 billion.\n"
    '{"answer": "number", "value": 391035000000, "unit": "USD", "fiscal_year": 2024,'
    ' "fiscal_period": "FY", "period_end": "2024-09-28"}'
)
INVENTED = (
    "SIMULATED: Apple's revenue for fiscal 2024 was about $400 billion.\n"
    '{"answer": "number", "value": 400000000000, "unit": "USD", "fiscal_year": 2024,'
    ' "fiscal_period": "FY", "period_end": "2024-09-28"}'
)


def apple_question(qid: str = "gnum-aapl-revenue-2024") -> NumQuestion:
    return NumQuestion.model_validate(
        {
            "id": qid,
            "split": "test",
            "qtype": "value",
            "question": "What did Apple Inc. (AAPL) report as revenue for FY2024?",
            "tickers": ("AAPL",),
            "ciks": (320193,),
            "concept": "revenue",
            "fiscal_year": 2024,
            "fiscal_period": "FY",
            "period_kind": "annual",
            "answer": NumberAnswer.model_validate(
                {
                    "value": Decimal("391035000000"),
                    "unit": "USD",
                    "period_start": dt.date(2023, 10, 1),
                    "period_end": dt.date(2024, 9, 28),
                }
            ),
            "sources": (),
            "index_version": "v-test",
        }
    )


def test_b2_asks_the_agent_one_user_turn_of_question_and_reply_format() -> None:
    question = apple_question()
    [message] = B2().prompt(question)
    assert message.role == "user"
    assert message.content.startswith(question.question)
    assert message.content.endswith(REPLY_FORMAT)
    assert B2().prompt(question) != B0().prompt(question)


def test_b0_prompt_is_unchanged_by_the_shared_reply_format() -> None:
    [system, _] = B0().prompt(apple_question())
    assert system.content.startswith("You answer questions about the SEC filings")
    assert system.content.endswith(REPLY_FORMAT)


def test_a_traced_agent_answer_is_recorded_as_shown_and_graded_right(
    facts_ctx: FactsContext,
) -> None:
    agent = agent_of(facts_ctx, ScriptedProvider("a", [calls(REVENUE), says(TRACED)]))
    model = AgentChatModel(agent, name="agent:sim", asked_on=ASKED_ON)
    question = apple_question()
    output = model.complete(B2().prompt(question))
    assert output == TRACED
    graded = grade(question, parse_reply(output))
    assert (graded.correct, graded.error) == (True, None)


def test_an_invented_value_never_reaches_the_grader(facts_ctx: FactsContext) -> None:
    """The checker withholds the untraced reply line, so b2 cannot score a model's number."""
    agent = agent_of(facts_ctx, ScriptedProvider("a", [calls(REVENUE), says(INVENTED)]))
    model = AgentChatModel(agent, name="agent:sim", asked_on=ASKED_ON)
    question = apple_question()
    output = model.complete(B2().prompt(question))
    assert "400000000000" not in output
    assert grade(question, parse_reply(output)).error == "unparsed"


def test_each_question_is_its_own_conversation(facts_ctx: FactsContext) -> None:
    provider = ScriptedProvider("a", [says("SIMULATED one."), says("SIMULATED two.")])
    model = AgentChatModel(agent_of(facts_ctx, provider), name="agent:sim", asked_on=ASKED_ON)
    model.complete(B2().prompt(apple_question("q-1")))
    model.complete(B2().prompt(apple_question("q-2")))
    second = provider.requests[1]
    assert [m["role"] for m in second.messages] == ["system", "user"], "no earlier turn"


def test_the_agent_model_refuses_a_prompt_that_is_not_one_user_turn(
    facts_ctx: FactsContext,
) -> None:
    model = AgentChatModel(agent_of(facts_ctx), name="agent:sim", asked_on=ASKED_ON)
    with pytest.raises(ValueError, match="one user message"):
        model.complete(B0().prompt(apple_question()))


def test_no_provider_stops_the_night_and_keeps_what_was_answered(
    facts_ctx: FactsContext, tmp_path: Path
) -> None:
    down = ProviderUnavailableError("503")
    provider = ScriptedProvider("a", [calls(REVENUE), says(TRACED), down, down, down])
    model = AgentChatModel(agent_of(facts_ctx, provider), name="agent:sim", asked_on=ASKED_ON)
    results = tmp_path / "b2.jsonl"
    questions = [apple_question("q-1"), apple_question("q-2")]
    with pytest.raises(AgentUnavailableError):
        run_numeric(questions, B2(), model, results=results, now=lambda: NOW)
    cached = read_jsonl(cache_path(results), AnswerRecord)
    assert [(r.qid, r.system, r.model) for r in cached] == [("q-1", "b2", "agent:sim")]
    assert "degraded" not in cached[0].output
