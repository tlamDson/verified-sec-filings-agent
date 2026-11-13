# LLM response fixtures (simulated)

Every file here is **simulated data**, written by hand for tests. No model produced them and
no provider was called. They copy only the field names and value types of an
OpenAI-compatible `POST /chat/completions` response (the shape llama.cpp's server and the
free hosted providers return); the wording, ids and token counts are made up.

| File                           | Simulates                                                             |
| ------------------------------ | --------------------------------------------------------------------- |
| `chat_answer.sim.json`         | A reply with text and no tool call                                    |
| `chat_tool_call.sim.json`      | A reply that calls `get_fact`, with `content` null                    |
| `chat_reasoning.sim.json`      | A reply from a reasoning model: an extra `reasoning_content` field, a tool call with no id, no `usage` |
