from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from api.config import settings
from api.models import Job, JobStatus

# In-memory store — swap for Redis/DB in production
_jobs: Dict[str, Job] = {}
_lock = asyncio.Lock()
_queue: asyncio.Queue[Tuple[str, bytes, str]] = asyncio.Queue()


async def create_job() -> Job:
    async with _lock:
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        job = Job(
            job_id=job_id,
            status=JobStatus.PENDING,
            created_at=now,
            expires_at=now + timedelta(hours=settings.TOKEN_EXPIRY_HOURS),
        )
        _jobs[job_id] = job
        return job


async def get_job(job_id: str) -> Optional[Job]:
    async with _lock:
        return _jobs.get(job_id)


async def update_job(job_id: str, **kwargs: object) -> None:
    async with _lock:
        job = _jobs.get(job_id)
        if job:
            _jobs[job_id] = job.model_copy(update=kwargs)


async def enqueue(job_id: str, spec_content: bytes, filename: str) -> None:
    await _queue.put((job_id, spec_content, filename))


async def cleanup_expired() -> None:
    from api.storage.local import delete_zip

    now = datetime.now(timezone.utc)
    async with _lock:
        expired = [jid for jid, job in _jobs.items() if job.expires_at < now]
    for jid in expired:
        await delete_zip(jid)
        async with _lock:
            _jobs.pop(jid, None)


def get_queue() -> asyncio.Queue[Tuple[str, bytes, str]]:
    return _queue
