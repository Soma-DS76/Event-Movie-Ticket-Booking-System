import time

from fastapi import HTTPException

from app.redis_client import redis_client


RATE_LIMIT_SCRIPT = "\nlocal count = redis.call('INCR', KEYS[1])\n\nif count == 1 then\n    redis.call('EXPIRE', KEYS[1], ARGV[1])\nend\n\nlocal ttl = redis.call('TTL', KEYS[1])\n\nreturn {count, ttl}\n"


def check_rate_limit(key, limit=5, window=60):
    count, ttl = redis_client.eval(RATE_LIMIT_SCRIPT,1,key,window)

    if int(count) > limit:
        retry_after = max(int(ttl), 1)

        raise HTTPException(status_code=429,
                            detail=('Too many requests. ' f"Try again after {retry_after} seconds."),
                            headers={'Retry-After': str(retry_after)})