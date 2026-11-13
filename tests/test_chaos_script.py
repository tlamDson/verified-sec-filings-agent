"""`infra/load/chaos.sh` run against stub `docker`, `git`, `curl` and `sleep` on PATH: the
script must fail when k6 fails (a crossed threshold exits 99) or when the acceptance check
in `sec-agent chaos load-rows` fails, and must still record the rows of a failed run."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

BASH = shutil.which("bash")
STUB = """#!/usr/bin/env bash
echo "$(basename "$0") $*" >> "$STUB_LOG"
if [ "$(basename "$0")" = docker ]; then
  case " $* " in
    *" run --rm k6 "*) exit "${K6_EXIT:-0}" ;;
    *" load-rows "*) exit "${LOAD_ROWS_EXIT:-0}" ;;
  esac
fi
if [ "$(basename "$0")" = git ]; then echo 0123456789abcdef; fi
exit 0
"""

pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")


def _run(repo_root: Path, tmp_path: Path, *, k6: int, load_rows: int) -> tuple[int, str]:
    root = tmp_path / "repo"
    (root / "infra" / "load").mkdir(parents=True)
    shutil.copy(repo_root / "infra" / "load" / "chaos.sh", root / "infra" / "load" / "chaos.sh")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name in ("docker", "git", "curl", "sleep"):
        (stubs / name).write_bytes(STUB.encode("utf-8"))
        (stubs / name).chmod(0o755)
    log = tmp_path / "calls.log"
    env = {
        **os.environ,
        "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
        "STUB_LOG": str(log),
        "CIKS": "320193",
        "K6_EXIT": str(k6),
        "LOAD_ROWS_EXIT": str(load_rows),
    }
    assert BASH is not None
    done = subprocess.run(
        [BASH, str(root / "infra" / "load" / "chaos.sh")],
        env=env,
        capture_output=True,
        timeout=60,
        check=False,
    )
    return done.returncode, log.read_text("utf-8") if log.exists() else ""


def test_a_clean_run_exits_zero(repo_root: Path, tmp_path: Path) -> None:
    code, calls = _run(repo_root, tmp_path, k6=0, load_rows=0)
    assert code == 0
    assert "run --rm k6" in calls
    assert "load-rows" in calls


def test_crossed_k6_thresholds_fail_the_run_after_recording_rows(
    repo_root: Path, tmp_path: Path
) -> None:
    code, calls = _run(repo_root, tmp_path, k6=99, load_rows=0)
    assert code == 99
    assert "load-rows" in calls  # a failed run is still a measured run


def test_a_failed_acceptance_check_fails_the_run(repo_root: Path, tmp_path: Path) -> None:
    code, _calls = _run(repo_root, tmp_path, k6=0, load_rows=1)
    assert code == 1


def test_a_failed_k6_run_is_reported_even_when_the_check_also_fails(
    repo_root: Path, tmp_path: Path
) -> None:
    code, _calls = _run(repo_root, tmp_path, k6=99, load_rows=1)
    assert code == 99
