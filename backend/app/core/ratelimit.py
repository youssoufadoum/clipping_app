"""Fixed-window rate limiter backed by Redis, with an in-process fallback.

The fallback keeps development and tests working without Redis; production
deployments always have Redis because the job queue depends on it.
"""

from __future__ import annotations

import logging
import threading
import time
from functools import lru_cache

import redis

from app.core.config import get_settings
from app.core.errors import RateLimited

log = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, redis_url: str | None) -> None:
        self._redis = redis.Redis.from_url(redis_url, socket_timeout=1) if redis_url else None
        self._local: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> None:
        bucket = int(time.time() // window_seconds)
        full_key = f"rl:{key}:{bucket}"
        count: int
        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.incr(full_key)
                pipe.expire(full_key, window_seconds + 1)
                count = int(pipe.execute()[0])
            except redis.RedisError:
                log.warning("rate limiter redis unavailable; using in-process fallback")
                count = self._local_hit(full_key, window_seconds)
        else:
            count = self._local_hit(full_key, window_seconds)
        if count > limit:
            raise RateLimited(details={"retry_after_seconds": window_seconds})

    def _local_hit(self, key: str, window: int) -> int:
        now = time.time()
        with self._lock:
            count, expires = self._local.get(key, (0, now + window))
            if expires < now:
                count, expires = 0, now + window
            count += 1
            self._local[key] = (count, expires)
            return count

    def reset(self) -> None:
        with self._lock:
            self._local.clear()


@lru_cache
def get_rate_limiter() -> RateLimiter:
    settings = get_settings()
    return RateLimiter(None if settings.app_env == "test" else settings.redis_url)
