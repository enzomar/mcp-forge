from __future__ import annotations

from pathlib import Path
from typing import Optional

from api.config import settings


def _zip_path(job_id: str) -> Path:
    return Path(settings.STORAGE_PATH) / f"{job_id}.zip"


async def save_zip(job_id: str, src_zip_path: str) -> str:
    """Move/register the zip into permanent storage; return final path."""
    dest = _zip_path(job_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # zip was already written here by the processor; just return the path
    return str(dest)


async def delete_zip(job_id: str) -> None:
    p = _zip_path(job_id)
    if p.exists():
        p.unlink()


async def get_zip_path(job_id: str) -> Optional[str]:
    p = _zip_path(job_id)
    return str(p) if p.exists() else None
