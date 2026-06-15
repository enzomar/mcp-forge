from __future__ import annotations

from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from api.config import settings

_SALT = "mcp-forge-download"


def generate_token(job_id: str) -> str:
    s = URLSafeTimedSerializer(settings.SECRET_KEY)
    return s.dumps(job_id, salt=_SALT)


def verify_token(token: str) -> Optional[str]:
    """Returns job_id if valid, None if expired or tampered."""
    s = URLSafeTimedSerializer(settings.SECRET_KEY)
    try:
        job_id: str = s.loads(
            token,
            salt=_SALT,
            max_age=settings.TOKEN_EXPIRY_HOURS * 3600,
        )
        return job_id
    except (SignatureExpired, BadSignature):
        return None
