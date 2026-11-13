"""Degraded mode: the figures a question asks for, looked up without any model.

When every LLM provider is out of quota or down, the agent cannot pick tools or write an
answer. `question.read_question` then reads the question with fixed rules (which
companies, which figures, which fiscal years; `lexicon` holds the names of the figures)
and `lookup.deterministic_evidence` runs the same deterministic tools the agent would
call. The result is evidence like the agent's, shown as cards without written
explanation. What the rules do not recognise is left out, never guessed.
"""
