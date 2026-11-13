"""Why the agent refused a turn before, or while, running it."""


class AgentError(Exception):
    """Base class for every agent error."""


class InvalidQuestionError(AgentError, ValueError):
    """The question is empty or longer than the configured limit."""


class InvalidThreadError(AgentError, ValueError):
    """The conversation id is empty, too long, or holds control characters."""


class ConversationConflictError(AgentError):
    """Another replica advanced this conversation first; this turn's state was not saved.

    The caller reloads the conversation and asks again; nothing was overwritten.
    """

    def __init__(self, thread_id: str) -> None:
        self.thread_id = thread_id
        super().__init__(f"conversation {thread_id!r} was advanced by another request")
