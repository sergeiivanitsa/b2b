import time
from dataclasses import dataclass


@dataclass
class RateLimitConfig:
    max_requests: int = 5
    window_seconds: int = 60


class RateLimiter:
    def __init__(self, config: RateLimitConfig) -> None:
        self._config = config
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        window_start = now - self._config.window_seconds
        hits = self._hits.get(key, [])
        hits = [t for t in hits if t >= window_start]
        if len(hits) >= self._config.max_requests:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True


class MultiRateLimiter:
    def __init__(self, config: RateLimitConfig) -> None:
        self._limiter = RateLimiter(config)

    def allow_all(self, keys: list[str]) -> bool:
        for key in keys:
            if not self._limiter.allow(key):
                return False
        return True
