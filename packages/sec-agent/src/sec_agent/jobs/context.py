"""What a handler factory gets from `sec-agent worker` to build its handler."""

import contextlib
from collections.abc import Callable
from dataclasses import dataclass

from sec_agent.jobs.worker import Handler


@dataclass(frozen=True)
class HandlerContext:
    """The worker's database URL, and an ExitStack that closes what the factory opens."""

    database_url: str
    resources: contextlib.ExitStack


HandlerFactory = Callable[[HandlerContext], Handler]
