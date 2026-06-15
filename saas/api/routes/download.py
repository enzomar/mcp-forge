from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api.jobs.queue import get_job
from api.security.tokens import verify_token

router = APIRouter()


@router.get("/download/{token}")
async def download(token: str) -> FileResponse:
    job_id = verify_token(token)
    if not job_id:
        raise HTTPException(404, "Download link has expired or is invalid")

    job = await get_job(job_id)
    if not job or not job.output_zip:
        raise HTTPException(404, "File not found — job may still be processing")

    zip_path = Path(job.output_zip)
    if not zip_path.exists():
        raise HTTPException(410, "File has been deleted (link expired)")

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename="mcp-server.zip",
    )
