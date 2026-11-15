"""G-public: FinanceBench loads only when licence and answers are checked and files pinned."""

import datetime as dt
import hashlib
from pathlib import Path

import pytest
from golden_data import GOLDEN_FIXTURES, split_company

from sec_agent.cli import main
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.golden.public.financebench import (
    FINANCEBENCH_TICKERS,
    PublicQuestion,
    load_g_public,
)
from sec_agent.golden.public.manifest import (
    GPublicManifest,
    NotVerifiedError,
    PinnedFile,
    read_manifest,
    write_manifest,
)
from sec_agent.golden.split import CompanySplit, write_split
from sec_agent.golden.universe import load_universe

QUESTIONS = GOLDEN_FIXTURES / "financebench_open_source.sim.jsonl"
DOCUMENTS = GOLDEN_FIXTURES / "financebench_document_information.sim.jsonl"


def _pin(path: Path) -> PinnedFile:
    body = path.read_bytes()
    return PinnedFile(sha256=hashlib.sha256(body).hexdigest(), rows=len(body.splitlines()))


def _manifest(**changes: object) -> GPublicManifest:
    base = GPublicManifest(
        source="https://github.com/patronus-ai/financebench",
        license="cc-by-nc-4.0",
        license_source="simulated test manifest",
        license_checked_on=dt.date(2026, 11, 13),
        license_note="simulated",
        answers_checked_on=dt.date(2026, 11, 13),
        answers_note="simulated",
        files={
            "financebench_open_source.jsonl": _pin(QUESTIONS),
            "financebench_document_information.jsonl": _pin(DOCUMENTS),
        },
    )
    return base.model_copy(update=changes)


@pytest.fixture
def split() -> CompanySplit:
    return CompanySplit(
        seed=1,
        universe_sha256="0" * 64,
        companies=(
            split_company("MMM", 66740, "dev", sector="Industrials", name="3M"),
            split_company("PEP", 77476, "test", sector="Consumer Staples", name="PepsiCo"),
        ),
    )


def test_verified_files_load_with_company_split_and_scope(split: CompanySplit) -> None:
    questions = load_g_public(QUESTIONS, DOCUMENTS, _manifest(), split)
    by_id = {q.id: q for q in questions}
    assert list(by_id) == [
        "financebench_id_sim01",
        "financebench_id_sim02",
        "financebench_id_sim03",
    ]
    mmm = by_id["financebench_id_sim01"]
    assert (mmm.ticker, mmm.cik, mmm.split, mmm.in_scope) == ("MMM", 66740, "dev", True)
    assert (mmm.doc_type, mmm.doc_period, mmm.question_type) == ("10k", 2022, "metrics-generated")
    assert mmm.evidence == ("Simulated evidence passage.",)
    activision = by_id["financebench_id_sim02"]
    assert (activision.ticker, activision.cik, activision.split) == (None, None, "none")
    assert activision.in_scope is False  # outside the universe (E7)
    pepsi = by_id["financebench_id_sim03"]
    assert (pepsi.ticker, pepsi.split, pepsi.in_scope) == ("PEP", "test", False)  # an 8-K


def test_unchecked_answers_block_loading(split: CompanySplit) -> None:
    with pytest.raises(NotVerifiedError, match="answers"):
        load_g_public(QUESTIONS, DOCUMENTS, _manifest(answers_checked_on=None), split)


def test_unchecked_licence_blocks_loading(split: CompanySplit) -> None:
    with pytest.raises(NotVerifiedError, match="licen"):
        load_g_public(QUESTIONS, DOCUMENTS, _manifest(license_checked_on=None), split)


def test_a_file_that_differs_from_its_pin_blocks_loading(
    split: CompanySplit, tmp_path: Path
) -> None:
    changed = tmp_path / "financebench_open_source.jsonl"
    changed.write_bytes(QUESTIONS.read_bytes() + b"\n")
    with pytest.raises(NotVerifiedError, match="sha256"):
        load_g_public(changed, DOCUMENTS, _manifest(), split)


def test_a_question_whose_document_is_unknown_is_refused(
    split: CompanySplit, tmp_path: Path
) -> None:
    lines = DOCUMENTS.read_text("utf-8").splitlines()[:2]  # drop the PepsiCo document
    docs = tmp_path / "docs.jsonl"
    docs.write_text("".join(f"{line}\n" for line in lines), "utf-8")
    files = {**_manifest().files, "financebench_document_information.jsonl": _pin(docs)}
    with pytest.raises(ValueError, match="PEPSICO_2023_8K"):
        load_g_public(QUESTIONS, docs, _manifest(files=files), split)


def test_every_mapped_financebench_company_is_in_the_universe() -> None:
    tickers = {c.ticker for c in load_universe()}
    assert set(FINANCEBENCH_TICKERS.values()) <= tickers
    assert FINANCEBENCH_TICKERS["3M"] == "MMM"
    assert "Activision Blizzard" not in FINANCEBENCH_TICKERS


def test_manifest_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    write_manifest(path, _manifest())
    assert read_manifest(path) == _manifest()


def _cli(tmp_path: Path, split: CompanySplit, manifest: GPublicManifest) -> list[str]:
    split_file, manifest_file = tmp_path / "split.json", tmp_path / "manifest.json"
    write_split(split_file, split)
    write_manifest(manifest_file, manifest)
    args = ["golden", "public", "--questions", str(QUESTIONS), "--documents", str(DOCUMENTS)]
    args += ["--manifest", str(manifest_file), "--split-file", str(split_file)]
    return [*args, "--out", str(tmp_path / "g_public.jsonl")]


def test_cli_writes_the_loaded_questions_with_counts(
    tmp_path: Path, split: CompanySplit, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_cli(tmp_path, split, _manifest())) == 0
    assert len(read_jsonl(tmp_path / "g_public.jsonl", PublicQuestion)) == 3
    assert "3 questions, 1 in scope" in capsys.readouterr().out


def test_cli_refuses_unverified_data_and_writes_nothing(
    tmp_path: Path, split: CompanySplit, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_cli(tmp_path, split, _manifest(answers_checked_on=None))) == 2
    assert "not verified" in capsys.readouterr().err
    assert not (tmp_path / "g_public.jsonl").exists()
