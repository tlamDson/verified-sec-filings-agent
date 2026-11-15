"""EdgarClient: User-Agent, rate limit per attempt, raw cache, retry. No network: MockTransport."""

import random
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

from sec_agent.edgar.cache import RawCache
from sec_agent.edgar.client import EdgarClient
from sec_agent.edgar.errors import (
    DisallowedHostError,
    EdgarConfigError,
    EdgarForbiddenError,
    EdgarHTTPError,
    EdgarNotFoundError,
    EdgarUnavailableError,
)
from sec_agent.edgar.rate_limit import shared_bucket
from sec_agent.edgar.retry import RetryPolicy

UA = "Test Runner test-runner@example.com"
URL = "https://data.sec.gov/submissions/CIK0000320193.json"

Reply = httpx.Response | Exception


class CountingLimiter:
    def __init__(self) -> None:
        self.acquired = 0

    def acquire(self) -> None:
        self.acquired += 1


class Server:
    """Scripted SEC stand-in: answers each request with the next reply and records it."""

    def __init__(self, *replies: Reply) -> None:
        self._replies: Iterator[Reply] = iter(replies)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = next(self._replies)
        if isinstance(reply, Exception):
            raise reply
        return reply


class Harness:
    def __init__(self, tmp_path: Path, *replies: Reply, cache: bool = True) -> None:
        self.server = Server(*replies)
        self.limiter = CountingLimiter()
        self.sleeps: list[float] = []
        self.cache = RawCache(tmp_path / "raw") if cache else None
        self.client = EdgarClient(
            UA,
            http=httpx.Client(transport=httpx.MockTransport(self.server)),
            limiter=self.limiter,
            cache=self.cache,
            retry=RetryPolicy(max_attempts=4, base_delay=0.5, max_delay=30.0),
            sleep=self.sleeps.append,
            rng=random.Random(0),
        )


def ok(body: bytes = b'{"cik": "320193"}') -> httpx.Response:
    return httpx.Response(200, content=body)


def status(code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(code, headers=headers, content=b"error page")


@pytest.fixture
def harness(tmp_path: Path) -> Callable[..., Harness]:
    def make(*replies: Reply, cache: bool = True) -> Harness:
        return Harness(tmp_path, *replies, cache=cache)

    return make


def test_sends_the_user_agent(harness: Callable[..., Harness]) -> None:
    h = harness(ok())
    assert h.client.get(URL) == b'{"cik": "320193"}'
    assert h.server.requests[0].headers["User-Agent"] == UA
    assert h.server.requests[0].url == URL


def test_rejects_a_bad_user_agent() -> None:
    with pytest.raises(EdgarConfigError):
        EdgarClient("no email here")


def test_each_network_attempt_takes_one_token(harness: Callable[..., Harness]) -> None:
    h = harness(ok(), ok(), cache=False)
    h.client.get(URL)
    h.client.get(URL)
    assert h.limiter.acquired == 2
    assert h.client.requests_sent == 2


def test_cache_hit_costs_no_request_and_no_token(harness: Callable[..., Harness]) -> None:
    h = harness(ok(b"first"))
    assert h.client.get(URL) == b"first"
    assert h.client.get(URL) == b"first"
    assert len(h.server.requests) == 1
    assert h.limiter.acquired == 1


def test_refresh_bypasses_and_rewrites_the_cache(harness: Callable[..., Harness]) -> None:
    h = harness(ok(b"old"), ok(b"new"))
    h.client.get(URL)
    assert h.client.get(URL, refresh=True) == b"new"
    assert h.cache is not None
    assert h.cache.get(URL) == b"new"


def test_get_json_parses_the_body(harness: Callable[..., Harness]) -> None:
    h = harness(ok(b'{"cik": "320193", "tickers": ["AAPL"]}'))
    assert h.client.get_json(URL) == {"cik": "320193", "tickers": ["AAPL"]}


def test_retries_server_errors_with_jittered_backoff(harness: Callable[..., Harness]) -> None:
    h = harness(status(503), status(500), ok())
    assert h.client.get(URL) == b'{"cik": "320193"}'
    assert len(h.server.requests) == 3
    assert h.limiter.acquired == 3
    assert len(h.sleeps) == 2
    assert 0 <= h.sleeps[0] <= 0.5
    assert 0 <= h.sleeps[1] <= 1.0


def test_retries_transport_errors(harness: Callable[..., Harness]) -> None:
    h = harness(httpx.ConnectError("reset"), httpx.ReadTimeout("slow"), ok())
    assert h.client.get(URL) == b'{"cik": "320193"}'
    assert len(h.sleeps) == 2


def test_honours_retry_after_on_429(harness: Callable[..., Harness]) -> None:
    h = harness(status(429, {"Retry-After": "7"}), ok())
    h.client.get(URL)
    assert h.sleeps[0] >= 7


def test_gives_up_when_retry_after_exceeds_the_cap(harness: Callable[..., Harness]) -> None:
    h = harness(status(429, {"Retry-After": "600"}))
    with pytest.raises(EdgarUnavailableError) as info:
        h.client.get(URL)
    assert info.value.retry_after == 600
    assert info.value.status == 429
    assert h.sleeps == []


def test_gives_up_after_max_attempts(harness: Callable[..., Harness]) -> None:
    h = harness(*(status(503) for _ in range(4)))
    with pytest.raises(EdgarUnavailableError) as info:
        h.client.get(URL)
    assert info.value.attempts == 4
    assert info.value.status == 503
    assert len(h.server.requests) == 4
    assert len(h.sleeps) == 3


def test_transport_failure_is_chained(harness: Callable[..., Harness]) -> None:
    h = harness(*(httpx.ConnectError("down") for _ in range(4)))
    with pytest.raises(EdgarUnavailableError) as info:
        h.client.get(URL)
    assert info.value.status is None
    assert isinstance(info.value.__cause__, httpx.ConnectError)


def test_403_fails_at_once_and_points_at_the_user_agent(harness: Callable[..., Harness]) -> None:
    h = harness(status(403))
    with pytest.raises(EdgarForbiddenError, match="SEC_USER_AGENT"):
        h.client.get(URL)
    assert len(h.server.requests) == 1


def test_404_raises_not_found(harness: Callable[..., Harness]) -> None:
    h = harness(status(404))
    with pytest.raises(EdgarNotFoundError) as info:
        h.client.get(URL)
    assert info.value.status == 404
    assert info.value.url == URL


def test_other_client_errors_are_not_retried(harness: Callable[..., Harness]) -> None:
    h = harness(status(400))
    with pytest.raises(EdgarHTTPError) as info:
        h.client.get(URL)
    assert info.value.status == 400
    assert len(h.server.requests) == 1


def test_redirects_are_not_followed(harness: Callable[..., Harness]) -> None:
    h = harness(status(301, {"Location": "https://example.com/"}))
    with pytest.raises(EdgarHTTPError):
        h.client.get(URL)
    assert len(h.server.requests) == 1


@pytest.mark.parametrize(
    "location", ["https://example.com/", "https://www.sec.gov/files/company_tickers.json"]
)
def test_injected_client_that_follows_redirects_is_overridden(
    tmp_path: Path, location: str
) -> None:
    server = Server(status(302, {"Location": location}), ok(b"should never be fetched"))
    limiter = CountingLimiter()
    http = httpx.Client(transport=httpx.MockTransport(server), follow_redirects=True)
    client = EdgarClient(UA, http=http, limiter=limiter, cache=RawCache(tmp_path))
    with pytest.raises(EdgarHTTPError) as info:
        client.get(URL)
    assert info.value.status == 302
    assert [str(r.url) for r in server.requests] == [URL]
    assert limiter.acquired == 1


@pytest.mark.parametrize("reply", [status(404), status(400), status(403)])
def test_errors_are_never_cached(harness: Callable[..., Harness], reply: httpx.Response) -> None:
    h = harness(reply)
    with pytest.raises(EdgarHTTPError):
        h.client.get(URL)
    assert h.cache is not None
    assert h.cache.get(URL) is None


def test_non_sec_hosts_are_refused_before_any_request(harness: Callable[..., Harness]) -> None:
    h = harness()
    with pytest.raises(DisallowedHostError):
        h.client.get("https://example.com/data.json")
    assert h.limiter.acquired == 0
    assert h.server.requests == []


def test_default_limiter_is_the_shared_bucket() -> None:
    with EdgarClient(UA) as first, EdgarClient(UA) as second:
        assert first.limiter is shared_bucket()
        assert second.limiter is shared_bucket()


def test_from_env_reads_the_user_agent_and_cache_dir(tmp_path: Path) -> None:
    env = {"SEC_USER_AGENT": UA, "SEC_RAW_CACHE_DIR": str(tmp_path / "cache")}
    with EdgarClient.from_env(env) as client:
        assert client.user_agent == UA
        assert client.cache is not None
        assert client.cache.root == tmp_path / "cache"


def test_from_env_defaults_the_cache_to_data_raw() -> None:
    with EdgarClient.from_env({"SEC_USER_AGENT": UA}) as client:
        assert client.cache is not None
        assert client.cache.root == Path("data/raw")


def test_from_env_without_user_agent_fails() -> None:
    with pytest.raises(EdgarConfigError, match="SEC_USER_AGENT"):
        EdgarClient.from_env({})
