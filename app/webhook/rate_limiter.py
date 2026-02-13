import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self._max_requests = max_requests
        self._window = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        q = self._requests[key]

        # Remove expired entries
        while q and q[0] <= now - self._window:
            q.popleft()

        if len(q) >= self._max_requests:
            return False

        q.append(now)
        return True
