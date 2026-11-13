"""EdgarClient: the only way this repository talks to SEC EDGAR.

Per request: refuse non-SEC hosts; answer from the raw cache when possible; otherwise take
one token from the shared bucket per network attempt, send the SEC_USER_AGENT contact, and
retry 429/5xx and transport errors with jittered backoff. Only 2xx bodies are cached.
Redirects are not followed, so every network attempt costs exactly one token.
"""

import json
import os
import random
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from types import TracebackType
from typing import Self

import httpx

from sec_agent.edgar.cache import RawCache
from sec_agent.edgar.errors import (
    EdgarForbiddenError,
    EdgarHTTPError,
    EdgarNotFoundError,
    EdgarUnavailableError,
)
from sec_agent.edgar.rate_limit import RateLimiter, shared_bucket
from sec_agent.edgar.retry import RetryPolicy, is_retryable, parse_retry_after
from sec_agent.edgar.urls import check_allowed
from sec_agent.edgar.user_agent import parse_user_agent, user_agent_from_env

CACHE_DIR_ENV_VAR = "SEC_RAW_CACHE_DIR"
DEFAULT_CACHE_DIR = Path("data/raw")
DEFAULT_TIMEOUT_SECONDS = 30.0


class EdgarClient:
    def __init__(
        self,
        user_agent: str,
        *,
        http: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
        cache: RawCache | None = None,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self.user_agent = parse_user_agent(user_agent)
        self.limiter: RateLimiter = limiter if limiter is not None else shared_bucket()
        self.cache = cache
        self.retry = retry if retry is not None else RetryPolicy()
        self._owns_http = http is None
        self._http = http if http is not None else httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS)
        self._sleep = sleep
        self._rng = rng if rng is not None else random.Random()
        self._sent_lock = threading.Lock()
        self._sent = 0

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        limiter: RateLimiter | None = None,
        retry: RetryPolicy | None = None,
    ) -> Self:
        """Build a client from SEC_USER_AGENT and SEC_RAW_CACHE_DIR (default `data/raw`)."""
        env = os.environ if environ is None else environ
        user_agent = user_agent_from_env(env)
        cache = RawCache(Path(env.get(CACHE_DIR_ENV_VAR) or DEFAULT_CACHE_DIR))
        return cls(user_agent, limiter=limiter, cache=cache, retry=retry)

    @property
    def requests_sent(self) -> int:
        """Network attempts made by this client (cache hits excluded)."""
        return self._sent

    def get(self, url: str, *, refresh: bool = False) -> bytes:
        """Return the body at `url`, from the raw cache unless `refresh` is set."""
        check_allowed(url)
        if self.cache is not None and not refresh:
            cached = self.cache.get(url)
            if cached is not None:
                return cached
        body = self._fetch(url)
        if self.cache is not None:
            self.cache.put(url, body)
        return body

    def get_json(self, url: str, *, refresh: bool = False) -> object:
        return json.loads(self.get(url, refresh=refresh))

    def _fetch(self, url: str) -> bytes:
        attempts = self.retry.max_attempts
        for attempt in range(1, attempts + 1):
            status: int | None = None
            retry_after: float | None = None
            failure: httpx.TransportError | None = None
            try:
                response = self._send(url)
            except httpx.TransportError as exc:
                failure = exc
            else:
                status = response.status_code
                if response.is_success:
                    return response.content
                if status == 403:
                    raise EdgarForbiddenError(url)
                if status == 404:
                    raise EdgarNotFoundError(url)
                if not is_retryable(status):
                    raise EdgarHTTPError(url, status)
                retry_after = parse_retry_after(response.headers.get("Retry-After"))
            give_up = attempt == attempts or (
                retry_after is not None and retry_after > self.retry.max_delay
            )
            if give_up:
                raise EdgarUnavailableError(url, attempt, status, retry_after) from failure
            self._sleep(self.retry.delay(attempt, self._rng, retry_after))
        raise AssertionError("unreachable: the last attempt always returns or raises")

    def _send(self, url: str) -> httpx.Response:
        self.limiter.acquire()
        with self._sent_lock:
            self._sent += 1
        return self._http.get(url, headers={"User-Agent": self.user_agent})

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
