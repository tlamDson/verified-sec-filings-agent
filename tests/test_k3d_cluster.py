"""k3d cluster config and the scripts that bring the optional Kubernetes deployment (s-x1) up,
load it to watch the HPA, and tear it down. All local: no registry push, no cloud, no model."""

from pathlib import Path
from typing import Any

import yaml

K3D = Path("infra") / "k3d"


def _text(repo_root: Path, name: str) -> str:
    return (repo_root / K3D / name).read_text("utf-8")


def _cluster(repo_root: Path) -> dict[str, Any]:
    return yaml.safe_load(_text(repo_root, "cluster.yaml"))


def test_cluster_has_one_server_and_two_agents(repo_root: Path) -> None:
    cluster = _cluster(repo_root)
    assert cluster["apiVersion"].startswith("k3d.io/")
    assert cluster["kind"] == "Simple"
    assert cluster["metadata"]["name"] == "sec-agent"
    assert cluster["servers"] == 1
    assert cluster["agents"] == 2  # pods of one deployment spread over nodes
    assert cluster["image"].startswith("rancher/k3s:v")


def test_ingress_is_published_on_localhost_only(repo_root: Path) -> None:
    ports = _cluster(repo_root)["ports"]
    assert any(p["port"].startswith("127.0.0.1:") and p["port"].endswith(":80") for p in ports)


def test_metrics_server_is_kept_for_the_hpa(repo_root: Path) -> None:
    text = _text(repo_root, "cluster.yaml")
    assert "--disable=metrics-server" not in text


def test_up_script_imports_the_image_and_makes_the_secret_from_env(repo_root: Path) -> None:
    text = _text(repo_root, "up.sh")
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert "k3d cluster create --config" in text
    assert "docker build" in text and "infra/load/Dockerfile" in text
    assert "k3d image import" in text
    assert "kubectl create secret generic" in text
    for key in ("PGPASSWORD", "API_AUTH_SECRET", "SEC_USER_AGENT"):
        assert key in text, key
    assert "infra/postgres/init" in text  # the init SQL becomes a ConfigMap
    assert "helm upgrade --install" in text
    assert "--set secretName=" in text
    assert "--wait" in text


def test_hpa_script_loads_the_api_and_watches_replicas(repo_root: Path) -> None:
    text = _text(repo_root, "hpa-watch.sh")
    assert "set -euo pipefail" in text
    assert "/healthz" in text  # load that needs no token and calls no model
    assert "kubectl get hpa" in text
    assert "simulated" in text


def test_down_script_deletes_the_cluster(repo_root: Path) -> None:
    assert "k3d cluster delete" in _text(repo_root, "down.sh")


def test_helm_workflow_lints_and_renders_the_chart(repo_root: Path) -> None:
    workflow = yaml.safe_load(
        (repo_root / ".github" / "workflows" / "helm.yml").read_text("utf-8")
    )
    jobs = workflow["jobs"]
    assert "Python checks" not in [job.get("name") for job in jobs.values()]
    steps = " ".join(str(step.get("run", "")) for job in jobs.values() for step in job["steps"])
    assert "helm lint" in steps
    assert "helm template" in steps
    assert "kubeconform" in steps
