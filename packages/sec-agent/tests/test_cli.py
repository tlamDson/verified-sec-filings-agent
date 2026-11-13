"""The `sec-agent` entry point exists and reports its version."""

import pytest

from sec_agent import __version__
from sec_agent.cli import main


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"sec-agent {__version__}"


def test_no_command_prints_help_and_fails(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "usage: sec-agent" in capsys.readouterr().out
