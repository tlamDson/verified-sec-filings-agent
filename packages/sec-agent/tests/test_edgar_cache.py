"""Raw cache: every SEC response body is kept on disk so re-runs cost no requests."""

from pathlib import Path

from sec_agent.edgar.cache import RawCache

URL = "https://data.sec.gov/submissions/CIK0000320193.json"
OTHER = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"


def test_miss_returns_none(tmp_path: Path) -> None:
    assert RawCache(tmp_path).get(URL) is None


def test_put_then_get_returns_the_same_bytes(tmp_path: Path) -> None:
    cache = RawCache(tmp_path)
    cache.put(URL, b'{"cik": "320193"}')
    assert cache.get(URL) == b'{"cik": "320193"}'


def test_survives_a_new_instance(tmp_path: Path) -> None:
    RawCache(tmp_path).put(URL, b"body")
    assert RawCache(tmp_path).get(URL) == b"body"


def test_put_overwrites(tmp_path: Path) -> None:
    cache = RawCache(tmp_path)
    cache.put(URL, b"old")
    cache.put(URL, b"new")
    assert cache.get(URL) == b"new"


def test_paths_are_stable_distinct_and_inside_root(tmp_path: Path) -> None:
    cache = RawCache(tmp_path)
    assert cache.path_for(URL) == RawCache(tmp_path).path_for(URL)
    assert cache.path_for(URL) != cache.path_for(OTHER)
    assert cache.path_for(URL).is_relative_to(tmp_path / "data.sec.gov")
    assert cache.path_for(OTHER).is_relative_to(tmp_path / "www.sec.gov")
    assert cache.path_for(OTHER).suffix == ".htm"


def test_query_string_is_part_of_the_key(tmp_path: Path) -> None:
    cache = RawCache(tmp_path)
    assert cache.path_for(URL + "?a=1") != cache.path_for(URL)


def test_write_leaves_no_temporary_files(tmp_path: Path) -> None:
    cache = RawCache(tmp_path)
    path = cache.put(URL, b"body")
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == [path]
