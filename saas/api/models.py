from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PACKAGING = "packaging"
    DONE = "done"
    FAILED = "failed"


class Job(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    expires_at: datetime
    output_zip: Optional[str] = None
    download_token: Optional[str] = None
    download_url: Optional[str] = None
    error: Optional[str] = None
    progress_message: Optional[str] = None
