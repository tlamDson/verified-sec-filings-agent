"""SEC_USER_AGENT must hold "Name email"; SEC blocks automated requests without one."""

from pathlib import Path

import pytest

from sec_agent.edgar.errors import EdgarConfigError
from sec_agent.edgar.user_agent import PLACEHOLDER_USER_AGENT, parse_user_agent, user_agent_from_env

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_accepts_name_and_email() -> None:
    assert parse_user_agent("  Jane Analyst jane@example.com ") == "Jane Analyst jane@example.com"


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_missing_value_names_the_variable(raw: str | None) -> None:
    with pytest.raises(EdgarConfigError, match="SEC_USER_AGENT"):
        parse_user_agent(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "Jane Analyst",
        "jane@example.com",
        "Jane Analyst jane@",
        "Jane Analyst jane@example",
        "Jane\nAnalyst jane@example.com",
        "Jane Analyst jane@example.com\r\nX-Injected: 1",
    ],
)
def test_rejects_malformed_values(raw: str) -> None:
    with pytest.raises(EdgarConfigError):
        parse_user_agent(raw)


def test_rejects_the_env_example_placeholder() -> None:
    with pytest.raises(EdgarConfigError, match="placeholder"):
        parse_user_agent(PLACEHOLDER_USER_AGENT)


def test_placeholder_matches_env_example() -> None:
    text = (REPO_ROOT / ".env.example").read_text("utf-8")
    assert f'SEC_USER_AGENT="{PLACEHOLDER_USER_AGENT}"' in text


def test_reads_from_environment_mapping() -> None:
    env = {"SEC_USER_AGENT": "Jane Analyst jane@example.com"}
    assert user_agent_from_env(env) == "Jane Analyst jane@example.com"


def test_missing_from_environment_mapping() -> None:
    with pytest.raises(EdgarConfigError, match="SEC_USER_AGENT"):
        user_agent_from_env({})
