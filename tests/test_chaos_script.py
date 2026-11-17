"""`infra/load/chaos.sh` run against stub `docker`, `git`, `curl` and `sleep` on PATH.

The script must inject its faults while k6 runs (kill one API replica, then rate-limit each
simulated model, then restore them), fail when k6 fails (a crossed threshold exits 99) or
when the acceptance check in `sec-agent chaos load-rows` fails, and still record the rows of
a failed run. The stub k6 run, like the real one, lasts until the fault timeline is over: it
ends after the fourth `/admin/mode` call, or exits 97 when that never comes."""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
import yaml

BASH = shutil.which("bash")
STUB = """#!/usr/bin/env bash
echo "$(basename "$0") $*" >> "$STUB_LOG"
if [ "$(basename "$0")" = docker ]; then
  case " $* " in
    *" run --rm k6 "*)
      for _ in $(seq 400); do
        if [ "$(grep -c /admin/mode "$STUB_LOG")" -ge 4 ]; then
          echo "k6 end" >> "$STUB_LOG"
          exit "${K6_EXIT:-0}"
        fi
        command -p sleep 0.05
      done
      echo "k6 timeout: the fault timeline never ran" >> "$STUB_LOG"
      exit 97 ;;
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


def _published_port(repo_root: Path, service: str) -> str:
    compose = yaml.safe_load((repo_root / "infra" / "load" / "compose.yaml").read_text("utf-8"))
    (mapping,) = compose["services"][service]["ports"]
    host, port, _container = str(mapping).split(":")
    assert host == "127.0.0.1"
    return port


def _index(calls: list[str], start: int, *parts: str) -> int:
    """The first call at or after `start` that holds every part."""
    for at in range(start, len(calls)):
        if all(part in calls[at] for part in parts):
            return at
    raise AssertionError(f"no call with {parts} after call {start}: {calls[start:]}")


def test_faults_are_injected_in_order_while_k6_runs(repo_root: Path, tmp_path: Path) -> None:
    code, log = _run(repo_root, tmp_path, k6=0, load_rows=0)
    assert code == 0, log
    calls = log.splitlines()
    compose = f"/{tmp_path.name}/repo/infra/load/compose.yaml "  # the load stack, not dev
    a = f"127.0.0.1:{_published_port(repo_root, 'llm-a')}/admin/mode"
    b = f"127.0.0.1:{_published_port(repo_root, 'llm-b')}/admin/mode"
    at = _index(calls, 0, "docker compose", "run --rm k6")
    kill = _index(calls, at, "docker compose", " kill api-2")
    assert " -f " in calls[kill]
    assert compose in calls[kill]
    at = _index(calls, kill, "curl", a, '"mode": "rate_limited"')
    at = _index(calls, at, "curl", b, '"mode": "rate_limited"')
    at = _index(calls, at, "curl", a, '"mode": "ok"')
    at = _index(calls, at, "curl", b, '"mode": "ok"')
    at = _index(calls, at, "k6 end")
    _index(calls, at, "docker compose", "load-rows")


def test_only_one_api_replica_is_killed(repo_root: Path, tmp_path: Path) -> None:
    _code, log = _run(repo_root, tmp_path, k6=0, load_rows=0)
    stops = [
        call
        for call in log.splitlines()
        if call.startswith("docker ")
        and any(f" {verb} " in f"{call} " for verb in ("kill", "stop", "down", "rm"))
        and "run --rm" not in call
    ]
    assert len(stops) == 1, stops
    assert stops[0].endswith(" kill api-2")


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


def test_the_stub_k6_gives_up_on_a_wall_clock_budget(tmp_path: Path) -> None:
    """The 'timeline never ran' path must end on time, not after N forks: on Windows 400
    polls of `grep` plus `sleep` take over 40 s, so it used to outlast the 60 s timeout."""
    stub = tmp_path / "docker"
    stub.write_bytes(STUB.encode("utf-8"))
    stub.chmod(0o755)
    log = tmp_path / "calls.log"
    env = {**os.environ, "STUB_LOG": str(log), "K6_STUB_BUDGET": "1"}
    assert BASH is not None
    started = time.monotonic()
    done = subprocess.run(
        [BASH, str(stub), "compose", "run", "--rm", "k6"],
        env=env,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 97
    assert time.monotonic() - started < 10
