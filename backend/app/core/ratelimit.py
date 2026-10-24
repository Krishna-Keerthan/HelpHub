"""In-process sliding-window rate limiter.

State lives in this process only: it resets on restart and is not shared
between instances (one instance today; see AR-13). Memory is bounded: past
``max_keys`` tracked keys the oldest-inserted keys are dropped, which only ever
loosens a limit, never tightens it.
"""

import time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self._clock = clock
        self._max_keys = max_keys
        self._events: dict[str, deque[float]] = {}

    def hit(self, key: str, limit: int, window_seconds: float) -> float | None:
        """Record an attempt. Returns None when allowed, else seconds until retry.

        A blocked attempt is not recorded, so waiting out the window always works.
        """
        now = self._clock()
        events = self._events.get(key)
        if events is None:
            self._make_room()
            events = self._events[key] = deque()
        while events and now - events[0] >= window_seconds:
            events.popleft()
        if len(events) >= limit:
            return max(window_seconds - (now - events[0]), 0.001)
        events.append(now)
        return None

    def reset(self) -> None:
        self._events.clear()

    def _make_room(self) -> None:
        while len(self._events) >= self._max_keys:
            del self._events[next(iter(self._events))]


limiter = RateLimiter()
