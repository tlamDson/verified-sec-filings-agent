"""The k3d scripts (s-x1) only ever talk to the cluster's own kube context, and only when that
context's API server is on this machine: the Secret made from .env and the release can never
reach whatever context happens to be current."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

K3D = Path("infra") / "k3d"
SCRIPTS = ("up.sh", "hpa-watch.sh")


def _text(repo_root: Path, name: str) -> str:
    return (repo_root / K3D / name).read_text("utf-8")


def _code_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


def test_cluster_create_leaves_the_current_context_alone(repo_root: Path) -> None:
    cluster = yaml.safe_load(_text(repo_root, "cluster.yaml"))
    assert cluster["options"]["kubeconfig"]["switchCurrentContext"] is False


def test_context_file_pins_the_k3d_context(repo_root: Path) -> None:
    text = _text(repo_root, "context.sh")
    assert 'CTX="k3d-sec-agent"' in text
    assert 'kube() { kubectl --context "$CTX" "$@"; }' in text


@pytest.mark.parametrize("script", SCRIPTS)
def test_scripts_never_call_kubectl_without_the_pinned_context(
    repo_root: Path, script: str
) -> None:
    for line in _code_lines(_text(repo_root, script)):
        assert not re.search(r"\bkubectl\b", line), line
        if re.search(r"(^|[(|;]\s*)helm\s", line):
            assert '--kube-context "$CTX"' in line, line


@pytest.mark.parametrize("script", SCRIPTS)
def test_scripts_check_the_context_before_the_first_kube_call(repo_root: Path, script: str) -> None:
    lines = _code_lines(_text(repo_root, script))
    source = next(i for i, line in enumerate(lines) if "infra/k3d/context.sh" in line)
    check = next(i for i, line in enumerate(lines) if line.strip() == "require_context")
    first_kube = next(
        i for i, line in enumerate(lines) if re.search(r"(^|[|;({]\s*|\$\()kube\s", line)
    )
    assert source < check < first_kube


def test_up_script_keeps_secret_values_off_the_command_line(repo_root: Path) -> None:
    text = _text(repo_root, "up.sh")
    assert "--from-literal" not in text
    assert "umask 077" in text
    assert "trap 'rm -rf \"$SECRET_DIR\"' EXIT" in text
    assert "--kubeconfig-switch-context=false" in text


def _bash() -> str | None:
    bash = shutil.which("bash")
    # On Windows, System32's bash.exe is WSL, which cannot see this kubectl or these paths.
    if bash is None or (sys.platform == "win32" and "system32" in bash.lower()):
        return None
    return bash


LOCAL = "https://0.0.0.0:6550"
REMOTE = "https://prod.example.com:6443"


def _require_context(
    repo_root: Path,
    tmp_path: Path,
    clusters: dict[str, str],
    context_cluster: str | None,
) -> int:
    """Run require_context against a throwaway kubeconfig.

    `clusters` maps cluster names to servers; `context_cluster` is the cluster the
    k3d-sec-agent context selects, or None for no such context. The current context is
    always a remote "work" cluster, as on a developer laptop.
    """
    bash, kubectl = _bash(), shutil.which("kubectl")
    if bash is None or kubectl is None:
        pytest.skip("needs bash and kubectl")
    contexts: list[dict[str, object]] = [
        {"name": "work", "context": {"cluster": "work", "user": "u"}}
    ]
    if context_cluster is not None:
        contexts.append(
            {"name": "k3d-sec-agent", "context": {"cluster": context_cluster, "user": "u"}}
        )
    config: dict[str, object] = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            *({"name": name, "cluster": {"server": server}} for name, server in clusters.items()),
            {"name": "work", "cluster": {"server": "https://k8s.example:6443"}},
        ],
        "contexts": contexts,
        "users": [{"name": "u", "user": {}}],
        "current-context": "work",
    }
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text(yaml.safe_dump(config), "utf-8")
    context_sh = (repo_root / K3D / "context.sh").as_posix()
    # `kubectl config view` reads only the given file: nothing is sent anywhere.
    result = subprocess.run(
        [bash, "-c", '. "$1"; require_context', "_", context_sh],
        env={**os.environ, "KUBECONFIG": str(kubeconfig)},
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode


def test_require_context_accepts_the_local_k3d_server(repo_root: Path, tmp_path: Path) -> None:
    clusters = {"k3d-sec-agent": LOCAL}
    assert _require_context(repo_root, tmp_path, clusters, "k3d-sec-agent") == 0


def test_require_context_reads_the_cluster_the_context_selects(
    repo_root: Path, tmp_path: Path
) -> None:
    clusters = {"k3d-sec-agent-local": LOCAL}
    assert _require_context(repo_root, tmp_path, clusters, "k3d-sec-agent-local") == 0


def test_require_context_refuses_a_remote_server(repo_root: Path, tmp_path: Path) -> None:
    clusters = {"k3d-sec-agent": REMOTE}
    assert _require_context(repo_root, tmp_path, clusters, "k3d-sec-agent") != 0


def test_require_context_ignores_a_local_namesake_cluster(repo_root: Path, tmp_path: Path) -> None:
    # The context is named k3d-sec-agent but selects a remote cluster; a local cluster
    # that only shares the context's name must not make the check pass.
    clusters = {"k3d-sec-agent": LOCAL, "prod": REMOTE}
    assert _require_context(repo_root, tmp_path, clusters, "prod") != 0


def test_require_context_refuses_a_context_whose_cluster_is_missing(
    repo_root: Path, tmp_path: Path
) -> None:
    clusters = {"k3d-sec-agent": LOCAL}
    assert _require_context(repo_root, tmp_path, clusters, "gone") != 0


def test_require_context_refuses_a_missing_context(repo_root: Path, tmp_path: Path) -> None:
    clusters = {"k3d-sec-agent": LOCAL}
    assert _require_context(repo_root, tmp_path, clusters, None) != 0


@pytest.mark.parametrize(
    "server",
    [
        "https://localhost:6443@prod.example.com",
        "https://127.0.0.1:6443.prod.example.com",
        "http://127.0.0.1:6550",
    ],
)
def test_require_context_refuses_a_server_that_only_starts_like_a_local_one(
    repo_root: Path, tmp_path: Path, server: str
) -> None:
    clusters = {"k3d-sec-agent": server}
    assert _require_context(repo_root, tmp_path, clusters, "k3d-sec-agent") != 0
