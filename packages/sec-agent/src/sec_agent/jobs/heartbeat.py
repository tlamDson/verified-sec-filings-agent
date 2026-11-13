"""Background thread that renews a job's lease while its handler runs."""

import logging
import threading
from collections.abc import Callable
from types import TracebackType
from typing import Self

log = logging.getLogger(__name__)


class Heartbeat:
    """Call `beat` every `interval` seconds until the block exits or `beat` returns False.

    An exception from `beat` (a dropped connection) is logged and the next beat tried;
    only a definite False, meaning another worker holds the lease now, stops the thread.
    """

    def __init__(self, beat: Callable[[], bool], interval: float) -> None:
        self._beat = beat
        self._interval = interval
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread = threading.Thread(target=self._run, name="job-heartbeat", daemon=True)

    @property
    def lost(self) -> bool:
        return self._lost.is_set()

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._stop.set()
        self._thread.join()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                alive = self._beat()
            except Exception:
                log.warning("heartbeat failed; retrying at next interval", exc_info=True)
                continue
            if not alive:
                self._lost.set()
                return
