"""Local stack: Postgres 17 with pgvector and pg_search, plus Phoenix for traces."""

from pathlib import Path
from typing import Any

import yaml


def _services(repo_root: Path) -> dict[str, Any]:
    compose = yaml.safe_load((repo_root / "compose.yaml").read_text("utf-8"))
    return compose["services"]


def test_postgres_is_pinned_paradedb_pg17(repo_root: Path) -> None:
    image = _services(repo_root)["postgres"]["image"]
    name, _, tag = image.partition(":")
    assert name == "paradedb/paradedb"
    assert tag.endswith("-pg17")
    assert not tag.startswith("latest")


def test_postgres_has_healthcheck(repo_root: Path) -> None:
    assert "pg_isready" in str(_services(repo_root)["postgres"]["healthcheck"]["test"])


def test_init_sql_creates_both_extensions(repo_root: Path) -> None:
    sql = (repo_root / "infra" / "postgres" / "init" / "01-extensions.sql").read_text("utf-8")
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "CREATE EXTENSION IF NOT EXISTS pg_search" in sql


def test_init_dir_is_mounted_into_postgres_entrypoint(repo_root: Path) -> None:
    """Without this mount the init SQL never runs and neither extension is created."""
    mounts: list[tuple[Path, str, str]] = []
    for volume in _services(repo_root)["postgres"]["volumes"]:
        source, target, *mode = str(volume).split(":")
        mounts.append(((repo_root / source).resolve(), target, mode[0] if mode else "rw"))
    init_dir = (repo_root / "infra" / "postgres" / "init").resolve()
    assert (init_dir, "/docker-entrypoint-initdb.d", "ro") in mounts


def test_postgres_password_has_no_committed_default(repo_root: Path) -> None:
    password = str(_services(repo_root)["postgres"]["environment"]["POSTGRES_PASSWORD"])
    assert password.startswith("${POSTGRES_PASSWORD:?")


def test_phoenix_is_pinned_and_exposes_ui_and_otlp(repo_root: Path) -> None:
    phoenix = _services(repo_root)["phoenix"]
    assert phoenix["image"].startswith("arizephoenix/phoenix:version-")
    ports = " ".join(str(p) for p in phoenix["ports"])
    assert "6006" in ports
    assert "4317" in ports
