"""The SEC User-Agent: "Name email", read from the SEC_USER_AGENT environment variable.

SEC answers 403 to automated requests that do not declare a contact
(https://www.sec.gov/os/accessing-edgar-data). The contact lives only in the environment;
the repository holds a placeholder in `.env.example`, which is refused here.
"""

import os
import re
from collections.abc import Mapping

from sec_agent.edgar.errors import EdgarConfigError

ENV_VAR = "SEC_USER_AGENT"
PLACEHOLDER_USER_AGENT = "Your Name your-name@example.com"

# A name (at least one word), a space, then an email address as the last word.
_USER_AGENT = re.compile(r"[^\s@][^@]*\s[^\s@]+@[^\s@]+\.[^\s@.]+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def parse_user_agent(raw: str | None) -> str:
    """Return the trimmed User-Agent, or raise EdgarConfigError when it is unusable."""
    value = (raw or "").strip()
    if not value:
        raise EdgarConfigError(f"{ENV_VAR} is not set; put 'Your Name you@your-domain' in .env")
    if _CONTROL.search(value):
        raise EdgarConfigError(f"{ENV_VAR} must be one line without control characters")
    if value == PLACEHOLDER_USER_AGENT:
        raise EdgarConfigError(f"{ENV_VAR} still holds the .env.example placeholder")
    if not _USER_AGENT.fullmatch(value):
        raise EdgarConfigError(f"{ENV_VAR} must look like 'Name email@domain', got {value!r}")
    return value


def user_agent_from_env(environ: Mapping[str, str] | None = None) -> str:
    """Read and validate SEC_USER_AGENT from `environ` (default: the process environment)."""
    env = os.environ if environ is None else environ
    return parse_user_agent(env.get(ENV_VAR))
