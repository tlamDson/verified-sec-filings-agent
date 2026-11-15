"""CLAUDE.md and AGENTS.md carry the rules every build session follows."""

from pathlib import Path


def test_claude_md_imports_agents_md(repo_root: Path) -> None:
    assert "@AGENTS.md" in (repo_root / "CLAUDE.md").read_text("utf-8")


def test_agents_md_states_core_rules(repo_root: Path) -> None:
    text = (repo_root / "AGENTS.md").read_text("utf-8")
    for phrase in ("runs.csv", "SEC_USER_AGENT", "simulated", "$0", "provider router", "fixtures"):
        assert phrase in text, phrase


def test_env_example_has_no_real_contact(repo_root: Path) -> None:
    text = (repo_root / ".env.example").read_text("utf-8")
    line = next(x for x in text.splitlines() if x.startswith("SEC_USER_AGENT="))
    assert "@example.com" in line
