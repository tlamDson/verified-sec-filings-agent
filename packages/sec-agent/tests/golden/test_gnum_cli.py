"""`sec-agent golden gnum`: latest facts from Postgres -> G-num JSONL, with a report."""

from pathlib import Path

import pytest
from xbrl_docs import APPLE, NVIDIA

from sec_agent.cli import main
from sec_agent.golden.gnum.models import NumQuestion
from sec_agent.golden.gnum.source import PostgresFactSource
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.golden.split import CompanySplit, write_split
from sec_agent.xbrl.companyfacts import parse_companyfacts
from sec_agent.xbrl.normalize import normalize
from sec_agent.xbrl.store import PostgresFactStore


@pytest.fixture
def facts_v1(facts_db_url: str) -> str:
    with PostgresFactStore.connect(facts_db_url) as store:
        for path in (APPLE, NVIDIA):
            doc = parse_companyfacts(path.read_bytes())
            store.write(
                index_version="v1",
                cik=doc.cik,
                entity_name=doc.entity_name,
                normalized=normalize(doc),
            )
    return facts_db_url


def test_source_reads_the_latest_version_of_each_fact(facts_v1: str) -> None:
    with PostgresFactSource.connect(facts_v1) as source:
        apple = source.latest(index_version="v1", cik=320193)
        assert apple
        assert {x.fact.cik for x in apple} == {320193}
        assert source.latest(index_version="v2", cik=320193) == []


def test_gnum_writes_questions_and_prints_the_report(
    facts_v1: str,
    two_company_split: CompanySplit,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DATABASE_URL", facts_v1)
    split_file, out = tmp_path / "split.json", tmp_path / "g_num.jsonl"
    write_split(split_file, two_company_split)
    args = ["golden", "gnum", "--index-version", "v1", "--split-file", str(split_file)]
    args += ["--out", str(out), "--totals", "train=5,dev=5,test=25", "--seed", "3"]
    assert main(args) == 0
    questions = read_jsonl(out, NumQuestion)
    assert len(questions) == 25
    assert {q.split for q in questions} == {"test"}
    assert {q.index_version for q in questions} == {"v1"}
    printed = capsys.readouterr().out
    assert "peer_comparison" in printed
    assert "wrote 25 questions" in printed
    assert "no facts in v1 for: DEV1, TRN1" in printed


def test_gnum_rejects_bad_totals(
    two_company_split: CompanySplit,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DATABASE_URL", "host=/nonexistent dbname=none")
    split_file = tmp_path / "split.json"
    write_split(split_file, two_company_split)
    args = ["golden", "gnum", "--index-version", "v1", "--split-file", str(split_file)]
    assert main([*args, "--out", str(tmp_path / "o.jsonl"), "--totals", "test=x"]) == 2
    assert "totals" in capsys.readouterr().err
