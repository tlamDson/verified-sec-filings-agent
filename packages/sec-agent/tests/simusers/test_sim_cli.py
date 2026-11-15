"""`sec-agent sim roster|plan|run`. The web app is a stand-in; no network is used."""

from pathlib import Path

import httpx
import pytest
from sim_web_fake import PASSWORD, FakeWebApp

from sec_agent.cli import main
from sec_agent.runs import read_runs
from sec_agent.simusers import cli as sim_cli

PLAN = ["--seed", "3", "--day", "2026-11-13", "--llm-calls-per-day", "40"]


def test_roster_lists_the_fifty_simulated_accounts(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["sim", "roster", "--seed", "3"]) == 0
    lines = capsys.readouterr().out.splitlines()
    accounts = [line for line in lines if "@example.com" in line]
    assert len(accounts) == 50
    assert "simulated" in lines[0].lower()


def test_plan_prints_the_sessions_inside_the_budget(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["sim", "plan", *PLAN]) == 0
    out = capsys.readouterr().out
    assert "5 of 5 questions" in out
    assert "simulated" in out.lower()


def test_a_share_above_half_the_quota_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["sim", "plan", *PLAN, "--share", "0.6"]) == 2
    assert "share" in capsys.readouterr().err


def test_run_needs_the_simulated_password(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SIM_LOGIN_SECRET", raising=False)
    assert main(["sim", "run", *PLAN, "--base-url", "https://web.test"]) == 2
    assert "SIM_LOGIN_SECRET" in capsys.readouterr().err


def test_run_drives_the_plan_and_records_simulated_rows(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    web = FakeWebApp()
    web.chat_status = 429
    monkeypatch.setenv("SIM_LOGIN_SECRET", PASSWORD)

    def client(base_url: str) -> httpx.Client:
        assert base_url == "https://web.test"
        return web.client()

    monkeypatch.setattr(sim_cli, "http_client", client)
    runs = tmp_path / "runs.csv"
    args = ["--base-url", "https://web.test", "--no-wait", "--record", str(runs)]
    assert main(["sim", "run", *PLAN, *args, "--git-sha", "abc1234"]) == 0
    out = capsys.readouterr().out
    assert "simulated users" in out
    assert web.sign_ins
    rows = read_runs(runs)
    assert rows
    assert {r.cohort for r in rows} == {"simulated"}
