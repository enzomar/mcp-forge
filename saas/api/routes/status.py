from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.jobs.queue import get_job

router = APIRouter()


@router.get("/status/{job_id}")
async def status(job_id: str) -> dict:
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress_message": job.progress_message,
        "error": job.error,
        "expires_at": job.expires_at.isoformat(),
        "download_url": job.download_url,
    }
