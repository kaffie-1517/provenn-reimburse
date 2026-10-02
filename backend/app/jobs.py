"""A small Postgres-backed job queue.

Jobs are rows in `jobs`. Enqueue inside the caller's transaction, so a job
exists if and only if the data it refers to was committed. Workers claim with
FOR UPDATE SKIP LOCKED, so any number of them can poll without stepping on
each other, and no extra infrastructure (Redis, SQS) is needed.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job

STALE_AFTER = timedelta(minutes=10)

_CLAIM = text(
    """
    UPDATE jobs
       SET state = 'running', locked_at = now(), attempts = attempts + 1
     WHERE id = (
            SELECT id FROM jobs
             WHERE state = 'queued' AND run_at <= now()
             ORDER BY run_at, id
             FOR UPDATE SKIP LOCKED
             LIMIT 1)
    RETURNING id
    """
)


def enqueue(session: AsyncSession, kind: str, payload: dict[str, Any], *, max_attempts: int = 5):
    job = Job(kind=kind, payload=payload, max_attempts=max_attempts)
    session.add(job)
    return job


async def claim(session: AsyncSession) -> Job | None:
    """Locks the next runnable job for this worker and commits the claim."""
    job_id = await session.scalar(_CLAIM)
    await session.commit()
    return await session.get(Job, job_id, populate_existing=True) if job_id else None


async def complete(session: AsyncSession, job: Job) -> None:
    job.state, job.finished_at, job.last_error = "done", func.now(), None
    await session.commit()


async def fail(session: AsyncSession, job: Job, error: str) -> bool:
    """Schedules a retry with exponential backoff. Returns True if given up."""
    job.last_error = error[:2000]
    job.locked_at = None
    if job.attempts >= job.max_attempts:
        job.state, job.finished_at = "failed", func.now()
    else:
        job.state = "queued"
        job.run_at = func.now() + timedelta(seconds=2**job.attempts)
    await session.commit()
    return job.state == "failed"


async def requeue_stale(session: AsyncSession) -> int:
    """Puts back jobs whose worker died mid-run."""
    result = await session.execute(
        update(Job)
        .where(Job.state == "running", Job.locked_at < func.now() - STALE_AFTER)
        .values(state="queued", locked_at=None)
    )
    await session.commit()
    return result.rowcount or 0


async def depth(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).where(Job.state == "queued")) or 0
