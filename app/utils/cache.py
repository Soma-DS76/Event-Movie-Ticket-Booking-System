import json
import logging

from app.redis_client import redis_client


logger = logging.getLogger(__name__)

CACHE_TTL = 300


def get_cache(key):
    try:
        value = redis_client.get(key)
        return json.loads(value) if value is not None else None
    except Exception:
        logger.exception('Redis cache read failed')
        return None


def set_cache(key, value):
    try:
        redis_client.setex(key, CACHE_TTL, json.dumps(value))
    except Exception:
        logger.exception('Redis cache write failed')


def clear_event_cache():
    try:
        cursor = 0

        while True:
            cursor, keys = redis_client.scan(cursor=cursor,match='events:*',count=100)

            if keys:
                redis_client.delete(*keys)

            if cursor == 0:
                break

    except Exception:
        logger.exception('Redis cache invalidation failed')