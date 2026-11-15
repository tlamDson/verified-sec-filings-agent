"""The web app and the API are configured by the environment; `.env.example` names every
variable with a placeholder, never a real secret, and the design says how they fit."""

from pathlib import Path

VARIABLES = (
    "API_AUTH_SECRET",
    "API_DAILY_QUESTIONS",
    "API_BASE_URL",
    "NEXTAUTH_SECRET",
    "NEXTAUTH_URL",
    "AUTH_GITHUB_ID",
    "AUTH_GITHUB_SECRET",
    "SIM_LOGIN_SECRET",
)
SECRETS = ("API_AUTH_SECRET", "NEXTAUTH_SECRET", "AUTH_GITHUB_SECRET", "SIM_LOGIN_SECRET")


def _values(repo_root: Path) -> dict[str, str]:
    """Every variable of `.env.example`, set or commented out, with its value."""
    values: dict[str, str] = {}
    for line in (repo_root / ".env.example").read_text("utf-8").splitlines():
        name, found, value = line.lstrip("# ").partition("=")
        if found and name.isidentifier() and name.isupper():
            values[name] = value.strip().strip("\"'")
    return values


def test_env_example_names_every_web_and_api_variable(repo_root: Path) -> None:
    values = _values(repo_root)
    for name in VARIABLES:
        assert name in values, name


def test_env_example_holds_placeholders_not_secrets(repo_root: Path) -> None:
    values = _values(repo_root)
    for name in SECRETS:
        assert values[name] == "" or values[name].startswith("change-me"), name


def test_the_simulated_sign_in_is_off_unless_its_secret_is_set(repo_root: Path) -> None:
    text = (repo_root / ".env.example").read_text("utf-8")
    line = next(x for x in text.splitlines() if "SIM_LOGIN_SECRET=" in x)
    assert line.startswith("#"), "simulated accounts are opt-in"


def test_the_design_describes_the_web_app_and_its_api(repo_root: Path) -> None:
    text = (repo_root / "docs" / "design.md").read_text("utf-8")
    assert "### Web app and API" in text
    section = text.split("### Web app and API", 1)[1].split("\n### ", 1)[0]
    for phrase in (
        "/v1/chat",
        "server-sent events",
        "Degraded mode",
        "Daily limit",
        "cohort",
        "simulated",
        "API_AUTH_SECRET",
    ):
        assert phrase in section, phrase
