"""The API's settings from the environment. Every secret here is made up for a test."""

import pytest
from api_kit import SECRET

from sec_agent.api.config import (
    DAILY_QUESTIONS_ENV_VAR,
    DEFAULT_DAILY_QUESTIONS,
    SECRET_ENV_VAR,
    ApiConfigError,
    config_from_env,
)


def test_the_secret_is_required_and_the_daily_limit_has_a_default() -> None:
    config = config_from_env({SECRET_ENV_VAR: SECRET})
    assert (config.auth_secret, config.daily_questions) == (SECRET, DEFAULT_DAILY_QUESTIONS)


def test_the_daily_limit_is_read_from_the_environment() -> None:
    config = config_from_env({SECRET_ENV_VAR: SECRET, DAILY_QUESTIONS_ENV_VAR: "5"})
    assert config.daily_questions == 5


@pytest.mark.parametrize(
    "secret", ["", "   ", "too-short", "change-me-to-a-random-secret-of-32-or-more-characters"]
)
def test_a_missing_or_short_secret_is_an_error_that_does_not_repeat_it(secret: str) -> None:
    with pytest.raises(ApiConfigError, match=SECRET_ENV_VAR) as caught:
        config_from_env({SECRET_ENV_VAR: secret})
    assert "too-short" not in str(caught.value)
    assert "change-me-to" not in str(caught.value)


@pytest.mark.parametrize("limit", ["0", "-1", "many", "1.5"])
def test_a_daily_limit_that_is_not_a_positive_whole_number_is_an_error(limit: str) -> None:
    with pytest.raises(ApiConfigError, match=DAILY_QUESTIONS_ENV_VAR):
        config_from_env({SECRET_ENV_VAR: SECRET, DAILY_QUESTIONS_ENV_VAR: limit})
