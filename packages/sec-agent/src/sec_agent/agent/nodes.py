"""The three steps of a turn: begin it, call the model, run the tools it asked for.

Each step returns the state it changes; LangGraph checkpoints after each one. The answer
the model writes is shown only as the faithfulness checker and the guardrails pass it
(`_checked`); a question the screen takes for an attack ends the turn at `begin`, and the
canary in anything the model writes ends it where it appears (`guarding`). A model call
and each tool call are spans of the turn's trace (`observability.spans`).
"""

import datetime as dt
from typing import Any, Literal

from opentelemetry.trace import Tracer

from sec_agent.agent.answer import Evidence, LLMCall, Reason, Status
from sec_agent.agent.config import AgentConfig
from sec_agent.agent.guarding import WITHHELD_QUESTION, TurnGuard, leaked
from sec_agent.agent.history import model_messages
from sec_agent.agent.notices import DEGRADED_TEXT, STEP_LIMIT_TEXT
from sec_agent.agent.prompt import system_prompt
from sec_agent.agent.state import AgentState
from sec_agent.agent.tool_runner import ToolRunner, refusal
from sec_agent.faithfulness.check import check_answer
from sec_agent.guardrails.notices import ATTACK_REFUSED_TEXT, CANARY_BLOCKED_TEXT
from sec_agent.llm.errors import AllProvidersFailedError
from sec_agent.llm.messages import ChatRequest, Message, assistant, system, tool_result, user
from sec_agent.llm.router import LLMRouter
from sec_agent.observability.spans import failed, llm_call_span, tool_span

Update = dict[str, Any]


class TurnNodes:
    def __init__(
        self, router: LLMRouter, tools: ToolRunner, config: AgentConfig, tracer: Tracer
    ) -> None:
        self._router = router
        self._tools = tools
        self._config = config
        self._tracer = tracer
        self._guard = TurnGuard(config.guardrails)

    def begin(self, state: AgentState) -> Update:
        """Start a turn: the question joins the conversation, the turn's record is reset.
        A question screened as an attack ends the turn here, before any model call."""
        question = state.get("question", "")
        screened = self._guard.screen(question)
        update: Update = {
            "messages": [user(question)],
            "turn": state.get("turn", 0) + 1,
            "evidence": [],
            "llm_calls": [],
            "status": None,
            "reason": None,
            "text": None,
            "draft": None,
            "faithfulness": None,
            "guard": screened.report,
        }
        if screened.refused:
            end = _end([], "blocked", "prompt_attack", ATTACK_REFUSED_TEXT)
            update.update(end, messages=[user(WITHHELD_QUESTION), *end["messages"]])
        return update

    def call_model(self, state: AgentState) -> Update:
        """One model call. It ends the turn unless the reply asks for tools."""
        calls = list(state.get("llm_calls", []))
        last_call = len(calls) + 1 >= self._config.max_llm_calls
        with llm_call_span(self._tracer, tools_offered=not last_call) as span:
            update = self._model_step(state, calls, last_call)
            if update.get("status") == "degraded":
                failed(span, update["reason"])
        return update

    def _model_step(
        self, state: AgentState, calls: list[dict[str, Any]], last_call: bool
    ) -> Update:
        request = ChatRequest(
            messages=self._prompt(state),
            tools=self._tools.schemas(),
            tool_choice="none" if last_call else "auto",
            max_tokens=self._config.max_answer_tokens,
        )
        try:
            result = self._router.complete(request)
        except AllProvidersFailedError as error:
            calls.append(_record(None, None, 0, 0, error.attempts))
            return _end(calls, "degraded", "llm_unavailable", DEGRADED_TEXT)
        completion = result.completion
        usage = completion.usage
        calls.append(
            _record(
                result.provider,
                completion.model,
                usage.prompt_tokens,
                usage.completion_tokens,
                result.attempts,
            )
        )
        message = completion.message
        if self._guard.reply_leaks(message):  # its text and its tool calls alike
            return self._leak(state, calls)
        if completion.finish_reason == "length":  # cut off: it may end in half a number
            return _end(calls, "degraded", "truncated_reply", DEGRADED_TEXT)
        tool_calls = message.get("tool_calls")
        if tool_calls:
            if last_call:
                return _end(calls, "step_limit", "max_llm_calls", STEP_LIMIT_TEXT)
            asked: Message = {
                "role": "assistant",
                "content": message["content"],
                "tool_calls": tool_calls,
            }
            return {"llm_calls": calls, "messages": [asked]}
        text = (message["content"] or "").strip()
        if not text:
            return _end(calls, "degraded", "empty_reply", DEGRADED_TEXT)
        return self._checked(state, calls, text)

    def run_tools(self, state: AgentState) -> Update:
        """Run every call of the last reply, in order; each gets a result message."""
        limit = self._config.max_tool_calls_per_reply
        evidence = list(state.get("evidence", []))
        guard = state.get("guard")
        results: list[Message] = []
        for index, call in enumerate(state.get("messages", [])[-1].get("tool_calls", [])):
            function = call["function"]
            with tool_span(self._tracer, function["name"], call["id"]) as span:
                if index < limit:
                    output = self._tools.run(function["name"], function["arguments"])
                else:
                    output = refusal("too_many_calls", f"at most {limit} tool calls in one reply")
                if not output.ok:
                    failed(span, output.code or "refused")
            content, guard = self._guard.tool_result(guard, function["name"], output.content)
            results.append(tool_result(call["id"], content))
            record = Evidence(
                call_id=call["id"],
                name=function["name"],
                arguments=function["arguments"],
                result=content,
                ok=output.ok,
                trimmed=output.trimmed,
            )
            evidence.append(record.model_dump(mode="json"))
        return {"messages": results, "evidence": evidence, "guard": guard}

    def _checked(self, state: AgentState, calls: list[dict[str, Any]], draft: str) -> Update:
        """The answer as the user may see it: no canary, only figures traced to this turn's
        evidence, no advice (E9)."""
        if self._guard.draft_leaks(draft):
            return {**self._leak(state, calls), "draft": draft}
        config = self._config.faithfulness
        if config is None:
            text, guard = self._guard.answer(state.get("guard"), draft)
            return {**_end(calls, "answered", None, text), "draft": draft, "guard": guard}
        evidence = [Evidence.model_validate(e) for e in state.get("evidence", [])]
        asked_on = dt.date.fromisoformat(state.get("asked_on", ""))
        report = check_answer(draft, evidence, asked_on=asked_on, config=config)
        checked: Update = {"draft": draft, "faithfulness": report.model_dump(mode="json")}
        if report.verdict == "blocked":
            return {**_end(calls, "blocked", "untraced_figures", report.text), **checked}
        text, guard = self._guard.answer(state.get("guard"), report.text)
        return {**_end(calls, "answered", None, text), **checked, "guard": guard}

    def _leak(self, state: AgentState, calls: list[dict[str, Any]]) -> Update:
        end = _end(calls, "blocked", "canary_leak", CANARY_BLOCKED_TEXT)
        return {**end, "guard": leaked(state.get("guard"))}

    def _prompt(self, state: AgentState) -> list[Message]:
        asked_on = dt.date.fromisoformat(state.get("asked_on", ""))
        shown = model_messages(
            state.get("messages", []), max_history_turns=self._config.max_history_turns
        )
        return [system(system_prompt(asked_on, canary=self._guard.canary)), *shown]


def after_begin(state: AgentState) -> Literal["model", "done"]:
    """A turn the screen refused is over before the model is called."""
    return "model" if state.get("status") is None else "done"


def after_model(state: AgentState) -> Literal["tools", "done"]:
    """The turn goes on to the tools while it has no status."""
    return "tools" if state.get("status") is None else "done"


def _end(calls: list[dict[str, Any]], status: Status, reason: Reason | None, text: str) -> Update:
    """The turn's last update: its closing assistant message is the answer or the notice."""
    return {
        "llm_calls": calls,
        "messages": [assistant(text)],
        "status": status,
        "reason": reason,
        "text": text,
    }


def _record(
    provider: str | None,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    attempts: tuple[Any, ...],
) -> dict[str, Any]:
    call = LLMCall(
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        attempts=attempts,
    )
    return call.model_dump(mode="json")
