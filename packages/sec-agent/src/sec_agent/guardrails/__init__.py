"""Guardrails of a turn, all deterministic code (no model is asked):

- `screen`: a direct attack in the question is refused before any model call; a request
  for investment advice is marked (E9);
- `quarantine`: sentences of filing text that give orders to an AI are replaced by a fixed
  mark before the model reads them (indirect injection);
- `canary`: a random secret in the system prompt; the model writing it, in its answer or
  in a tool call, ends the turn (the prompt leaked, or an injected order was followed);
- `answer`: advice sentences are dropped and the not-investment-advice disclaimer added.

Patterns are in `patterns`; fixed texts in `notices`. `GuardrailConfig` turns each on.
"""
