"""Celery configuration and scheduled SharpAPI odds polling task."""

import asyncio
import logging
import os
from typing import Final
from uuid import uuid4

from celery import Celery
from redis import Redis
from redis.exceptions import RedisError

from db.crud import save_odds_snapshot
from db.database import SessionLocal

from .odds_client import CleanOdds, fetch_upcoming_moneyline_odds as fetch_sharpapi_odds


logger = logging.getLogger(__name__)

REDIS_URL: Final[str] = os.getenv("REDIS_URL", "redis://redis:6379/0")
POLL_TASK_NAME: Final[str] = "workers.celery_app.poll_sharp_odds"
POLL_LOCK_KEY: Final[str] = "line-scanner:locks:sharp-odds-poll"
POLL_LOCK_TTL_SECONDS: Final[int] = 30

celery_app = Celery("line_scanner", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(
    task_soft_time_limit=20,
    task_time_limit=25,
    beat_schedule={
        "poll-sharp-odds-every-10-seconds": {
            "task": POLL_TASK_NAME,
            "schedule": 10.0,
        }
    },
    timezone="UTC",
)


@celery_app.task(name=POLL_TASK_NAME)
def poll_sharp_odds() -> list[CleanOdds]:
    """Poll SharpAPI once, skipping a tick while a prior poll still runs."""
    lock_client = Redis.from_url(REDIS_URL, decode_responses=True)
    lock_token = str(uuid4())
    lock_acquired = False

    try:
        lock_acquired = bool(
            lock_client.set(
                POLL_LOCK_KEY,
                lock_token,
                nx=True,
                ex=POLL_LOCK_TTL_SECONDS,
            )
        )
        if not lock_acquired:
            logger.info("Skipping odds poll because another poll is still active.")
            return []

        raw_odds = asyncio.run(fetch_sharpapi_odds())
        with SessionLocal() as db:
            save_odds_snapshot(db, raw_odds)
        return raw_odds
    except RedisError:
        logger.exception("Unable to acquire the Redis lock for the odds poll.")
        return []
    except Exception:
        logger.exception("SharpAPI odds poll failed.")
        return []
    finally:
        if lock_acquired:
            _release_lock(lock_client, lock_token)
        lock_client.close()


def _release_lock(lock_client: Redis, lock_token: str) -> None:
    """Release a lock only when it is still owned by this task invocation."""
    release_script = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    end
    return 0
    """
    try:
        lock_client.eval(release_script, 1, POLL_LOCK_KEY, lock_token)
    except RedisError:
        logger.warning("Could not release odds-poll lock; it will expire automatically.")
