"""Helm chart for the optional k3d deployment (s-x1): stateless API replicas scaled by an HPA,
ingest workers, two simulated models and one Postgres. Secrets come from a Secret made outside
the chart, so no password, token or contact is committed. Checked without helm: the templates
are read as text, values.yaml and Chart.yaml as YAML."""

import re
from pathlib import Path
from typing import Any

import yaml

CHART = Path("infra") / "helm" / "sec-agent"


def _yaml(repo_root: Path, name: str) -> dict[str, Any]:
    return yaml.safe_load((repo_root / CHART / name).read_text("utf-8"))


def _template(repo_root: Path, name: str) -> str:
    return (repo_root / CHART / "templates" / name).read_text("utf-8")


def _all_templates(repo_root: Path) -> str:
    return "\n".join(
        path.read_text("utf-8") for path in sorted((repo_root / CHART / "templates").iterdir())
    )


def test_chart_is_a_helm_v2_application(repo_root: Path) -> None:
    chart = _yaml(repo_root, "Chart.yaml")
    assert chart["apiVersion"] == "v2"
    assert chart["name"] == "sec-agent"
    assert chart["type"] == "application"
    assert re.fullmatch(r"\d+\.\d+\.\d+", chart["version"])


def test_api_hpa_scales_between_two_and_five_replicas_on_cpu(repo_root: Path) -> None:
    hpa = _yaml(repo_root, "values.yaml")["api"]["autoscaling"]
    assert hpa["enabled"] is True
    assert hpa["minReplicas"] >= 2  # one replica dying never takes the API down
    assert hpa["maxReplicas"] > hpa["minReplicas"]
    assert 0 < hpa["targetCPUUtilizationPercentage"] <= 90
    text = _template(repo_root, "api-hpa.yaml")
    assert "apiVersion: autoscaling/v2" in text
    assert "kind: HorizontalPodAutoscaler" in text
    assert "kind: Deployment" in text  # scaleTargetRef
    assert "averageUtilization" in text
    assert "behavior:" in text  # scale-down is slowed so a short dip does not drop replicas


def test_hpa_has_cpu_requests_to_measure_against(repo_root: Path) -> None:
    values = _yaml(repo_root, "values.yaml")
    for part in ("api", "worker", "fakeLlm"):
        resources = values[part]["resources"]
        assert resources["requests"]["cpu"], part
        assert resources["limits"]["memory"], part
    assert "toYaml .Values.api.resources" in _template(repo_root, "api-deployment.yaml")


def test_api_deployment_leaves_replicas_to_the_hpa(repo_root: Path) -> None:
    text = _template(repo_root, "api-deployment.yaml")
    assert "if not .Values.api.autoscaling.enabled" in text
    assert "sec-agent api serve" in text
    assert "--facts-version" in text
    assert "--host 0.0.0.0" in text
    assert "/healthz" in text
    assert "readinessProbe" in text
    assert "livenessProbe" in text
    # Tables are created once by a Job, not by every replica racing on start.
    assert "sec-agent api init" not in text


def test_init_job_creates_tables_before_install_and_upgrade(repo_root: Path) -> None:
    text = _template(repo_root, "init-job.yaml")
    assert "kind: Job" in text
    assert "post-install,pre-upgrade" in text
    assert "sec-agent agent init" in text
    assert "sec-agent api init" in text


def test_pod_disruption_budget_keeps_one_api_replica(repo_root: Path) -> None:
    text = _template(repo_root, "api-pdb.yaml")
    assert "kind: PodDisruptionBudget" in text
    assert "minAvailable: 1" in text


def test_secrets_come_from_a_secret_made_outside_the_chart(repo_root: Path) -> None:
    values = _yaml(repo_root, "values.yaml")
    assert values["secretName"] == ""  # required at install: helm fails without it
    templates = _all_templates(repo_root)
    assert "kind: Secret" not in templates
    assert 'required "set secretName' in templates
    for key in ("PGPASSWORD", "API_AUTH_SECRET", "SEC_USER_AGENT"):
        assert f"key: {key}" in templates, key
    raw = (repo_root / CHART / "values.yaml").read_text("utf-8")
    assert "@" not in raw  # no contact for SEC_USER_AGENT
    assert "change-me" not in raw


def test_default_models_are_simulated_and_cost_nothing(repo_root: Path) -> None:
    values = _yaml(repo_root, "values.yaml")
    assert values["fakeLlm"]["enabled"] is True
    providers = values["llm"]["providers"]
    assert [p["model"] for p in providers] == ["fake-llm-sim", "fake-llm-sim"]
    assert all("fake-llm" in p["base_url"] for p in providers)
    text = _template(repo_root, "fake-llm.yaml")
    assert "sec-agent" in text
    assert "fake-llm" in text
    assert "kind: Service" in text


def test_one_worker_keeps_the_sec_rate_limit_and_a_lease(repo_root: Path) -> None:
    values = _yaml(repo_root, "values.yaml")
    # The EDGAR token bucket is per process: a second worker would double the SEC rate.
    assert values["worker"]["replicas"] == 1
    text = _template(repo_root, "worker-deployment.yaml")
    assert "sec-agent" in text
    assert "worker" in text
    assert "--lease" in text
    assert "--heartbeat" in text
    assert "SEC_USER_AGENT" in text
    assert "terminationGracePeriodSeconds" in text
    assert "if gt (int .Values.worker.replicas) 1" in text
    assert "fail " in text
    assert "type: Recreate" in text


def test_postgres_is_paradedb_pg17_with_the_repo_init_sql(repo_root: Path) -> None:
    values = _yaml(repo_root, "values.yaml")
    image = values["postgres"]["image"]
    assert image.startswith("paradedb/paradedb:")
    assert image.endswith("-pg17")
    assert values["postgres"]["initConfigMap"]
    text = _template(repo_root, "postgres.yaml")
    assert "kind: StatefulSet" in text
    assert "volumeClaimTemplates" in text
    assert "/docker-entrypoint-initdb.d" in text
    assert "pg_isready" in text


def test_api_is_reached_through_one_service_and_ingress(repo_root: Path) -> None:
    service = _template(repo_root, "api-service.yaml")
    assert "kind: Service" in service
    ingress = _template(repo_root, "api-ingress.yaml")
    assert "kind: Ingress" in ingress
    assert "traefik" in _yaml(repo_root, "values.yaml")["api"]["ingress"]["className"]


def test_images_are_pinned(repo_root: Path) -> None:
    values = _yaml(repo_root, "values.yaml")
    assert values["image"]["tag"] not in ("", "latest")
    assert values["image"]["pullPolicy"] == "IfNotPresent"  # imported into k3d, never pulled
    assert ":latest" not in _all_templates(repo_root)
