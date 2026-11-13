"""Committed golden-set data: the company split and the G-public manifest."""

from pathlib import Path

from sec_agent.golden.public.manifest import read_manifest
from sec_agent.golden.split import SPLIT_SEED, build_split, read_split
from sec_agent.golden.universe import load_universe


def test_committed_split_is_the_seeded_split_of_the_packaged_universe(repo_root: Path) -> None:
    committed = read_split(repo_root / "data" / "golden" / "company_split.json")
    assert committed == build_split(load_universe(), seed=SPLIT_SEED)


def test_g_public_manifest_records_the_licence_and_pins_both_files(repo_root: Path) -> None:
    manifest = read_manifest(repo_root / "data" / "golden" / "g_public_manifest.json")
    assert manifest.license == "cc-by-nc-4.0"
    assert manifest.license_checked_on is not None
    assert set(manifest.files) == {
        "financebench_open_source.jsonl",
        "financebench_document_information.jsonl",
    }
    assert manifest.files["financebench_open_source.jsonl"].rows == 150
