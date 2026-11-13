"""Load and chaos stack (s-20): 3 API replicas behind nginx, two simulated models, three
ingest workers on one raw cache, k6 in a profile. Nothing in it can bill or reach a model."""

import json
import re
from pathlib import Path
from typing import Any

import yaml

LOAD = Path("infra") / "load"
API_REPLICAS = ("api-1", "api-2", "api-3")
WORKERS = ("worker-1", "worker-2", "worker-3")


def _compose(repo_root: Path) -> dict[str, Any]:
    return yaml.safe_load((repo_root / LOAD / "compose.yaml").read_text("utf-8"))


def _services(repo_root: Path) -> dict[str, Any]:
    return _compose(repo_root)["services"]


def _env(service: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in service.get("environment", {}).items()}


def _text(repo_root: Path, name: str) -> str:
    return (repo_root / LOAD / name).read_text("utf-8")


def test_stack_has_its_own_project_and_database(repo_root: Path) -> None:
    compose = _compose(repo_root)
    assert compose["name"] == "sec-agent-load"  # never touches the dev stack's volumes
    postgres = compose["services"]["postgres"]
    assert postgres["image"].startswith("paradedb/paradedb:")
    assert postgres["image"].endswith("-pg17")


def test_two_to_three_api_replicas_share_one_image_and_serve_one_facts_version(
    repo_root: Path,
) -> None:
    services = _services(repo_root)
    replicas = [name for name in services if name.startswith("api-")]
    assert tuple(sorted(replicas)) == API_REPLICAS
    images = {services[name]["image"] for name in replicas}
    assert len(images) == 1
    for name in replicas:
        command = " ".join(services[name]["command"])
        assert "sec-agent api serve" in command
        assert "--facts-version" in command
        assert "--host 0.0.0.0" in command


def test_secrets_have_no_committed_default(repo_root: Path) -> None:
    services = _services(repo_root)
    for name in (*API_REPLICAS, "k6"):
        assert _env(services[name])["API_AUTH_SECRET"].startswith("${API_AUTH_SECRET:?")
    assert _env(services["postgres"])["POSTGRES_PASSWORD"].startswith("${POSTGRES_PASSWORD:?")
    for name in WORKERS:
        assert _env(services[name])["SEC_USER_AGENT"].startswith("${SEC_USER_AGENT:?")


def test_replicas_reach_only_the_simulated_models(repo_root: Path) -> None:
    services = _services(repo_root)
    for name in API_REPLICAS:
        providers = json.loads(_env(services[name])["LLM_PROVIDERS"])
        assert [p["name"] for p in providers] == ["llm-a", "llm-b"]
        for provider in providers:
            assert provider["base_url"].startswith(f"http://{provider['name']}:")
            assert "api_key_env" not in provider  # no key, so nothing can bill
    for name in ("llm-a", "llm-b"):
        assert "sec-agent chaos fake-llm" in " ".join(services[name]["command"])


def test_load_balancer_spreads_over_every_replica_and_retries_a_dead_one(
    repo_root: Path,
) -> None:
    lb = _services(repo_root)["lb"]
    assert lb["image"].startswith("nginx:1.")
    assert any("nginx.conf" in str(volume) for volume in lb["volumes"])
    conf = _text(repo_root, "nginx.conf")
    upstream = re.search(r"upstream api \{(.*?)\}", conf, re.S)
    assert upstream is not None
    assert re.findall(r"server (api-\d):8000", upstream.group(1)) == list(API_REPLICAS)
    assert "max_fails" in upstream.group(1)
    assert re.search(r"proxy_next_upstream error timeout", conf)
    assert "proxy_buffering off" in conf  # server-sent events reach k6 as they are sent


def test_workers_share_one_raw_cache_and_name_themselves(repo_root: Path) -> None:
    services = _services(repo_root)
    for name in WORKERS:
        worker = services[name]
        assert worker["hostname"] == name  # the job's lease owner names the container
        assert worker["profiles"] == ["ingest"]
        assert any(str(v).startswith("rawcache:") for v in worker["volumes"])
        assert _env(worker)["SEC_RAW_CACHE_DIR"] == "/rawcache"
        assert "sec-agent worker" in " ".join(worker["command"])


def test_k6_is_pinned_and_only_in_the_load_profile(repo_root: Path) -> None:
    k6 = _services(repo_root)["k6"]
    name, _, tag = k6["image"].partition(":")
    assert name == "grafana/k6"
    assert re.fullmatch(r"\d+\.\d+\.\d+", tag)
    assert k6["profiles"] == ["load"]
    assert "--summary-export" in " ".join(k6["command"])


def test_k6_script_speaks_as_simulated_users_and_emits_the_parsed_metrics(
    repo_root: Path,
) -> None:
    from sec_agent.chaos.k6_summary import METRIC_NAMES

    script = _text(repo_root, "chat.js")
    for metric in METRIC_NAMES:
        assert f'"{metric}"' in script, metric
    assert "sim:" in script
    assert 'cohort: "simulated"' in script
    assert 'aud: "sec-agent-api"' in script
    assert "PEAK_VUS || 200" in script  # 200 virtual users unless told otherwise
    assert "thresholds" in script


def test_chaos_script_kills_a_replica_a_worker_and_rate_limits_the_models(
    repo_root: Path,
) -> None:
    script = _text(repo_root, "chaos.sh")
    assert script.startswith("#!/usr/bin/env bash")
    assert "kill api-2" in script
    assert "sec-agent chaos integrity" in script
    assert "/admin/mode" in script
    assert "rate_limited" in script
    assert "sec-agent chaos load-rows" in script


def test_image_copies_only_the_python_package(repo_root: Path) -> None:
    dockerfile = _text(repo_root, "Dockerfile")
    assert "FROM python:3.12" in dockerfile
    assert "COPY . ." not in dockerfile  # node_modules and data stay out of the image
    assert "uv sync --locked --no-dev" in dockerfile


def test_raw_cache_mount_point_belongs_to_the_runtime_user(repo_root: Path) -> None:
    """A new named volume takes the ownership of the image directory it is mounted on; a
    directory missing from the image is created owned by root, and uid 1000 cannot write."""
    dockerfile = _text(repo_root, "Dockerfile")
    user_at = dockerfile.index("USER 1000")
    setup = dockerfile[:user_at]
    assert re.search(r"mkdir -p [^&]*/rawcache", setup)
    assert re.search(r"chown 1000:1000 [^&]*/rawcache", setup)
    cache_dirs = {_env(_services(repo_root)[name])["SEC_RAW_CACHE_DIR"] for name in WORKERS}
    assert cache_dirs == {"/rawcache"}


def test_results_dir_is_writable_from_the_containers(repo_root: Path) -> None:
    assert 'chmod 0777 "$RESULTS"' in _text(repo_root, "chaos.sh")


def test_no_database_url_holds_a_password(repo_root: Path) -> None:
    for name, service in _services(repo_root).items():
        url = _env(service).get("DATABASE_URL", "")
        assert "POSTGRES_PASSWORD" not in url, name
        assert "@" not in url, name
        if url:
            assert _env(service)["PGPASSWORD"].startswith("${POSTGRES_PASSWORD:?"), name


def test_k6_thresholds_use_the_acceptance_limit(repo_root: Path) -> None:
    """The k6 thresholds and `sec_agent.chaos.acceptance` enforce the same limit."""
    from sec_agent.chaos.acceptance import ERROR_RATE_LIMIT
    from sec_agent.chaos.k6_summary import INTERRUPTED_RESUME_FAILED, RESUME_FAILED, TURN_FAILED

    block = re.search(r"thresholds: \{(.*?)\}", _text(repo_root, "chat.js"), re.S)
    assert block is not None
    found = dict(re.findall(r'(\w+): \["([^"]+)"\]', block.group(1)))
    limit = f"rate<{ERROR_RATE_LIMIT}"
    assert found == {TURN_FAILED: limit, RESUME_FAILED: limit, INTERRUPTED_RESUME_FAILED: limit}


def test_chaos_script_does_not_swallow_a_failed_k6_run(repo_root: Path) -> None:
    script = _text(repo_root, "chaos.sh")
    assert not re.search(r'wait "\$K6" \|\| echo', script)
