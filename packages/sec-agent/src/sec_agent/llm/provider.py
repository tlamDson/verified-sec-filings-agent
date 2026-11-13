"""A provider as the router sees it, and the configuration of an OpenAI-compatible one."""

from typing import Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sec_agent.llm.messages import ChatRequest, Completion
from sec_agent.llm.quota import QuotaLimits

DEFAULT_TIMEOUT_SECONDS = 60.0


class Provider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def limits(self) -> QuotaLimits: ...

    def complete(self, request: ChatRequest) -> Completion:
        """One call. Raises a `ProviderError` subclass for a failure of the provider."""
        ...


class ProviderConfig(BaseModel):
    """One OpenAI-compatible endpoint. The key itself is never here: `api_key_env` names
    the environment variable that holds it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    timeout_seconds: float = Field(default=DEFAULT_TIMEOUT_SECONDS, gt=0, le=3600)
    limits: QuotaLimits = QuotaLimits()

    @field_validator("base_url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("must be an http or https URL")
        if parts.username or parts.password:
            raise ValueError("must not carry credentials; use api_key_env")
        return value
