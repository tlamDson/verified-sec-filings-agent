"""Terraform for Neon (Postgres) and Vercel (web app): free tiers, pinned providers, no secret
in the repository, no Azure."""

import re
from pathlib import Path

TF = Path("infra") / "terraform"


def _tf(repo_root: Path) -> str:
    files = sorted((repo_root / TF).glob("*.tf"))
    assert files, "no .tf files"
    return "\n".join(path.read_text("utf-8") for path in files)


def _block(text: str, header: str) -> str:
    """The body of the first block whose header line starts with `header`."""
    start = text.index(header)
    depth = 0
    for index in range(text.index("{", start), len(text)):
        depth += {"{": 1, "}": -1}.get(text[index], 0)
        if depth == 0:
            return text[start : index + 1]
    raise AssertionError(f"unclosed block {header}")


def test_providers_are_neon_and_vercel_with_pinned_versions(repo_root: Path) -> None:
    providers = _block(_tf(repo_root), "required_providers")
    for source in ("kislerdm/neon", "vercel/vercel"):
        match = re.search(rf'source\s*=\s*"{source}"\s*\n\s*version\s*=\s*"([^"]+)"', providers)
        assert match, source
        assert match.group(1).startswith("~>") or match.group(1)[0].isdigit(), source


def test_lock_file_pins_both_providers(repo_root: Path) -> None:
    lock = (repo_root / TF / ".terraform.lock.hcl").read_text("utf-8")
    assert 'provider "registry.terraform.io/kislerdm/neon"' in lock
    assert 'provider "registry.terraform.io/vercel/vercel"' in lock


def test_no_azure_and_no_paid_provider(repo_root: Path) -> None:
    text = _tf(repo_root).lower()
    for banned in ("azurerm", "azuread", "hashicorp/aws", "hashicorp/google"):
        assert banned not in text, banned


def test_tokens_come_from_the_environment_not_the_files(repo_root: Path) -> None:
    text = _tf(repo_root)
    # NEON_API_KEY and VERCEL_API_TOKEN are read by the providers from the environment.
    assert not re.search(r"\b(api_key|api_token)\s*=", text)


def test_neon_project_is_postgres_17_within_the_free_history_window(repo_root: Path) -> None:
    project = _block(_tf(repo_root), 'resource "neon_project"')
    assert re.search(r"pg_version\s*=\s*17\b", project)
    match = re.search(r"history_retention_seconds\s*=\s*(\d+)", project)
    assert match
    assert int(match.group(1)) <= 21600  # free plan: at most 6 hours of history


def test_vercel_project_builds_the_web_folder_as_nextjs(repo_root: Path) -> None:
    project = _block(_tf(repo_root), 'resource "vercel_project"')
    assert re.search(r'framework\s*=\s*"nextjs"', project)
    assert re.search(r'root_directory\s*=\s*"web"', project)


def test_vercel_gets_every_variable_the_web_app_needs(repo_root: Path) -> None:
    text = _tf(repo_root)
    for name in ("API_BASE_URL", "API_AUTH_SECRET", "NEXTAUTH_SECRET", "NEXTAUTH_URL"):
        assert f'"{name}"' in text, name


def test_api_base_url_points_at_the_hugging_face_space(repo_root: Path) -> None:
    assert ".hf.space" in _tf(repo_root)


def test_secret_variables_are_sensitive(repo_root: Path) -> None:
    text = _tf(repo_root)
    for name in ("api_auth_secret", "nextauth_secret"):
        assert re.search(r"sensitive\s*=\s*true", _block(text, f'variable "{name}"')), name
    assert re.search(r"sensitive\s*=\s*true", _block(text, 'output "database_url"'))


def test_example_tfvars_holds_placeholders_only(repo_root: Path) -> None:
    example = (repo_root / TF / "terraform.tfvars.example").read_text("utf-8")
    for line in example.splitlines():
        if "secret" in line.split("=")[0]:
            assert '"change-me' in line, line


def test_state_and_real_tfvars_are_git_ignored(repo_root: Path) -> None:
    ignored = (repo_root / ".gitignore").read_text("utf-8").splitlines()
    for pattern in ("*.tfstate", "*.tfstate.*", ".terraform/", "*.tfvars"):
        assert pattern in ignored, pattern
