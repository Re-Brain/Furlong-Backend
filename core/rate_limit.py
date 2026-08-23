import logging
import os

import redis
from dotenv import load_dotenv
from fastapi import HTTPException, Request

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

logger = logging.getLogger(__name__)

STRICT_LIMIT = 5
STRICT_WINDOW_SECONDS = 15 * 60

LOOSE_LIMIT = 25
LOOSE_WINDOW_SECONDS = 15 * 60


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _get_count(key: str) -> int | None:
    try:
        value = redis_client.get(key)
    except redis.RedisError:
        logger.warning("Redis unavailable for rate-limit check on %s; failing open", key, exc_info=True)
        return None
    return int(value) if value is not None else 0


def _raise_too_many(key: str) -> None:
    try:
        ttl = redis_client.ttl(key)
    except redis.RedisError:
        ttl = None
    retry_after = ttl if ttl and ttl > 0 else STRICT_WINDOW_SECONDS
    raise HTTPException(
        status_code=429,
        detail="Too many attempts. Please try again later.",
        headers={"Retry-After": str(retry_after)},
    )


def check_strict_limit(request: Request, identifier: str, action: str) -> str:
    """Pre-check for the strict tier (keyed on IP + identifier, e.g. email).

    Returns the Redis key so the caller can record the outcome afterward via
    record_attempt() (unconditional) or reset() (on a verified success) --
    whichever this specific endpoint's semantics call for.
    """
    key = f"ratelimit:{action}:{_client_ip(request)}:{identifier.strip().lower()}"
    count = _get_count(key)
    if count is not None and count >= STRICT_LIMIT:
        _raise_too_many(key)
    return key


def enforce_loose_limit(request: Request, action: str) -> None:
    """Combined check+increment for the loose tier (IP-only, no success/failure split)."""
    key = f"ratelimit:loose:{action}:{_client_ip(request)}"
    count = _get_count(key)
    if count is not None and count >= LOOSE_LIMIT:
        _raise_too_many(key)
    record_attempt(key, LOOSE_WINDOW_SECONDS)


def record_attempt(key: str, window_seconds: int = STRICT_WINDOW_SECONDS) -> None:
    try:
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds, nx=True)
        pipe.execute()
    except redis.RedisError:
        logger.warning("Redis unavailable for rate-limit increment on %s; failing open", key, exc_info=True)


def reset(key: str) -> None:
    try:
        redis_client.delete(key)
    except redis.RedisError:
        logger.warning("Redis unavailable for rate-limit reset on %s", key, exc_info=True)
