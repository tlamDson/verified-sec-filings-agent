"""Errors raised by the EDGAR client."""


class EdgarError(Exception):
    """Base class for every EDGAR client error."""


class EdgarConfigError(EdgarError, ValueError):
    """The client is misconfigured, for example SEC_USER_AGENT is missing or malformed."""


class DisallowedHostError(EdgarError, ValueError):
    """The URL is not an https URL on an SEC EDGAR host."""


class EdgarHTTPError(EdgarError):
    """SEC answered with a status the client does not retry."""

    def __init__(self, url: str, status: int, message: str | None = None) -> None:
        self.url = url
        self.status = status
        super().__init__(message or f"SEC returned HTTP {status} for {url}")


class EdgarForbiddenError(EdgarHTTPError):
    """HTTP 403: SEC refuses undeclared automated tools and clients over the rate limit."""

    def __init__(self, url: str) -> None:
        super().__init__(
            url,
            403,
            f"SEC returned HTTP 403 for {url}. Check that SEC_USER_AGENT holds a real "
            "'Name email' contact and that no other process is exceeding 10 requests per second.",
        )


class EdgarNotFoundError(EdgarHTTPError):
    """HTTP 404: the document does not exist on EDGAR."""

    def __init__(self, url: str) -> None:
        super().__init__(url, 404)


class EdgarUnavailableError(EdgarError):
    """Retries ran out, or SEC asked to wait longer than the retry policy allows.

    `retry_after` carries SEC's requested wait in seconds when it sent one, so a job queue
    can reschedule the work instead of blocking a worker.
    """

    def __init__(
        self, url: str, attempts: int, status: int | None, retry_after: float | None = None
    ) -> None:
        self.url = url
        self.attempts = attempts
        self.status = status
        self.retry_after = retry_after
        reason = f"HTTP {status}" if status is not None else "a transport error"
        wait = f"; SEC asked to wait {retry_after:g} s" if retry_after is not None else ""
        super().__init__(f"{url} failed after {attempts} attempt(s) with {reason}{wait}")
