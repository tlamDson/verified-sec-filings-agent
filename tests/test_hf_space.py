"""The API deploys as a Docker Space on Hugging Face (free CPU) from a GitHub Actions workflow
that holds only the secret HF_TOKEN; the required CI checks are untouched."""

import re
from pathlib import Path
from typing import Any

import yaml

SPACE = Path("infra") / "hf-space"
WORKFLOW = Path(".github") / "workflows" / "deploy-api.yml"


def _front_matter(repo_root: Path) -> dict[str, Any]:
    text = (repo_root / SPACE / "README.md").read_text("utf-8")
    head, found, _ = text.removeprefix("---\n").partition("\n---\n")
    assert text.startswith("---\n"), "Space card needs YAML front matter"
    assert found, "Space card front matter is not closed"
    return yaml.safe_load(head)


def _dockerfile(repo_root: Path) -> str:
    return (repo_root / SPACE / "Dockerfile").read_text("utf-8")


def _workflow(repo_root: Path) -> dict[Any, Any]:
    return yaml.safe_load((repo_root / WORKFLOW).read_text("utf-8"))


def _runs(repo_root: Path) -> str:
    steps = [step for job in _workflow(repo_root)["jobs"].values() for step in job["steps"]]
    return "\n".join(step.get("run", "") for step in steps)


def test_space_card_is_a_docker_space_on_the_dockerfile_port(repo_root: Path) -> None:
    card = _front_matter(repo_root)
    assert card["sdk"] == "docker"
    port = card["app_port"]
    assert f"EXPOSE {port}" in _dockerfile(repo_root)
    assert f"--port {port}" in _dockerfile(repo_root) or f"PORT={port}" in _dockerfile(repo_root)


def test_dockerfile_pins_python_312_and_uv(repo_root: Path) -> None:
    dockerfile = _dockerfile(repo_root)
    assert re.search(r"^FROM python:3\.12[\w.-]*-slim", dockerfile, re.MULTILINE)
    assert re.search(r"ghcr\.io/astral-sh/uv:\d+\.\d+\.\d+", dockerfile)


def test_dockerfile_installs_the_locked_runtime_without_dev_or_gpu_extras(
    repo_root: Path,
) -> None:
    dockerfile = _dockerfile(repo_root)
    assert "uv sync --locked --no-dev" in dockerfile
    assert "--extra embed" not in dockerfile
    assert "--all-extras" not in dockerfile


def test_dockerfile_runs_as_uid_1000(repo_root: Path) -> None:
    # Spaces run the container as user 1000; files it writes must belong to that user.
    assert re.search(r"^USER 1000\b|^USER \w+$", _dockerfile(repo_root), re.MULTILINE)
    assert "1000" in _dockerfile(repo_root)


def test_entrypoint_creates_tables_then_serves_lexical_on_all_interfaces(
    repo_root: Path,
) -> None:
    entry = (repo_root / SPACE / "start.sh").read_text("utf-8")
    serve = entry.index("api serve")
    assert entry.index("agent init") < serve
    assert entry.index("api init") < serve
    command = entry[serve:]
    assert "--lexical" in command  # no embedding model on the free CPU Space
    assert "--host 0.0.0.0" in command
    assert "FACTS_VERSION" in command


def test_workflow_is_manual_or_main_only_and_reads_only_contents(repo_root: Path) -> None:
    workflow = _workflow(repo_root)
    triggers = workflow[True]
    assert "workflow_dispatch" in triggers
    assert "pull_request" not in triggers  # a fork's PR never sees the token
    assert triggers.get("push", {}).get("branches", ["main"]) == ["main"]
    assert workflow["permissions"] == {"contents": "read"}


def test_workflow_does_not_add_a_required_check_name(repo_root: Path) -> None:
    names = {job["name"] for job in _workflow(repo_root)["jobs"].values()}
    assert not names & {"Python checks", "Web checks"}


def test_workflow_uses_hf_token_only_from_secrets(repo_root: Path) -> None:
    text = (repo_root / WORKFLOW).read_text("utf-8")
    assert "secrets.HF_TOKEN" in text
    assert not re.search(r"hf_[A-Za-z0-9]{20,}", text)  # no literal token
    assert "set -x" not in text  # would print the token


def test_workflow_pushes_the_staged_space_and_sets_its_secrets(repo_root: Path) -> None:
    run = _runs(repo_root)
    assert "huggingface.co/api/repos/create" in run
    assert "/secrets" in run
    assert "huggingface.co/spaces/" in run
    assert "git push" in run
    for name in ("DATABASE_URL", "API_AUTH_SECRET", "SEC_USER_AGENT", "LLM_PROVIDERS"):
        assert name in run, name


def test_workflow_stages_only_what_the_image_needs(repo_root: Path) -> None:
    run = _runs(repo_root)
    for path in ("infra/hf-space/", "pyproject.toml", "uv.lock", "packages/sec-agent"):
        assert path in run, path
    assert "packages/sec-agent/tests" in run  # removed from the staged copy


def test_nothing_deploys_to_azure(repo_root: Path) -> None:
    for path in [*(repo_root / ".github" / "workflows").glob("*.yml"), repo_root / SPACE]:
        files = [path] if path.is_file() else [p for p in path.iterdir() if p.is_file()]
        for file in files:
            assert "azure" not in file.read_text("utf-8").lower(), file


def test_terraform_is_checked_on_pull_requests(repo_root: Path) -> None:
    workflow = yaml.safe_load(
        (repo_root / ".github" / "workflows" / "terraform.yml").read_text("utf-8")
    )
    assert "pull_request" in workflow[True]
    run = "\n".join(
        step.get("run", "") for job in workflow["jobs"].values() for step in job["steps"]
    )
    for command in ("terraform fmt -check", "terraform init -backend=false", "terraform validate"):
        assert command in run, command
    assert "terraform apply" not in run
