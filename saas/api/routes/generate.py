from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from api.jobs.queue import create_job, enqueue
from api.security.validators import validate_openapi_content, validate_url

router = APIRouter()


@router.post("/generate")
async def generate(
    request: Request,
    spec_file: Optional[UploadFile] = File(default=None),
    spec_url: Optional[str] = Form(default=None),
    spec_text: Optional[str] = Form(default=None),
) -> dict:
    has_file = spec_file is not None
    has_url = bool(spec_url and spec_url.strip())
    has_text = bool(spec_text and spec_text.strip())

    if sum([has_file, has_url, has_text]) != 1:
        raise HTTPException(400, "Provide exactly one input: spec_file, spec_url, or spec_text")

    # ── File upload path ──────────────────────────────────────────────────────
    if has_file:
        assert spec_file is not None
        # Size guard — read() is needed anyway so check after
        content = await spec_file.read()
        filename = spec_file.filename or "spec.yaml"
    elif has_url:
        # ── URL fetch path ────────────────────────────────────────────────────
        assert spec_url is not None
        url_error = validate_url(spec_url)
        if url_error:
            raise HTTPException(400, url_error)
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(spec_url)
                resp.raise_for_status()
                content = resp.content
        except httpx.HTTPStatusError as exc:
            raise HTTPException(400, f"Remote server returned {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise HTTPException(400, f"Failed to fetch URL: {exc}") from exc

        raw_name = spec_url.rstrip("/").rsplit("/", 1)[-1] or "spec"
        filename = raw_name if raw_name.endswith((".yaml", ".yml", ".json")) else raw_name + ".yaml"
    else:
        assert spec_text is not None
        content = spec_text.encode("utf-8")
        filename = "pasted_spec.yaml"

    # ── Validate spec content ─────────────────────────────────────────────────
    content_error = validate_openapi_content(content)
    if content_error:
        raise HTTPException(422, content_error)

    # ── Create and queue the job ──────────────────────────────────────────────
    job = await create_job()
    await enqueue(job.job_id, content, filename)

    return {"job_id": job.job_id, "status": job.status}
