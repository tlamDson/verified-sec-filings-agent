"""Attribute names: OpenTelemetry GenAI semantic conventions, the OpenInference ones Phoenix
shows (span kind, model, token counts), and this project's own (`sec_agent.*`)."""

from typing import Final, Literal

# OpenTelemetry GenAI (gen_ai.*), and error.type from the general conventions.
OPERATION: Final = "gen_ai.operation.name"
PROVIDER: Final = "gen_ai.provider.name"
AGENT_NAME: Final = "gen_ai.agent.name"
CONVERSATION_ID: Final = "gen_ai.conversation.id"
REQUEST_MAX_TOKENS: Final = "gen_ai.request.max_tokens"
REQUEST_TEMPERATURE: Final = "gen_ai.request.temperature"
RESPONSE_MODEL: Final = "gen_ai.response.model"
RESPONSE_FINISH_REASONS: Final = "gen_ai.response.finish_reasons"
INPUT_TOKENS: Final = "gen_ai.usage.input_tokens"
OUTPUT_TOKENS: Final = "gen_ai.usage.output_tokens"
TOOL_NAME: Final = "gen_ai.tool.name"
TOOL_CALL_ID: Final = "gen_ai.tool.call.id"
TOOL_TYPE: Final = "gen_ai.tool.type"
ERROR_TYPE: Final = "error.type"

# OpenInference, which Phoenix uses for its span kinds, token totals and sessions.
OI_SPAN_KIND: Final = "openinference.span.kind"
OI_SESSION_ID: Final = "session.id"
OI_PROVIDER: Final = "llm.provider"
OI_MODEL: Final = "llm.model_name"
OI_PROMPT_TOKENS: Final = "llm.token_count.prompt"
OI_COMPLETION_TOKENS: Final = "llm.token_count.completion"
OI_TOTAL_TOKENS: Final = "llm.token_count.total"
OI_TOOL_NAME: Final = "tool.name"

# This project.
STEP: Final = "sec_agent.step"
TURN: Final = "sec_agent.turn"
TURN_STATUS: Final = "sec_agent.turn.status"
TURN_REASON: Final = "sec_agent.turn.reason"
TOOLS_OFFERED: Final = "sec_agent.llm.tools_offered"
LLM_OUTCOME: Final = "sec_agent.llm.outcome"
SKIPPED_EVENT: Final = "sec_agent.llm.skipped"

AGENT: Final = "sec-agent"
Step = Literal["turn", "llm_call", "chat", "tool"]
"""What a span is to the latency table: the turn, one model call of it (with failover),
one call to one provider, or one tool call."""
