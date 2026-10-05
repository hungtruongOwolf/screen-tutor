"""A small sliding-window rate limiter.

Per process: on AWS Lambda each warm instance has its own counters, so this is a
brake against a runaway client or a leaked token, not a hard global quota. A hard
cap on spend belongs in an AWS Budget.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0, clock=time.monotonic) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """Record a request for `key`; False when it would exceed the limit."""
        now = self._clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True
