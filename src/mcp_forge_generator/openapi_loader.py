from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


class OpenAPILoadError(RuntimeError):
    """Raised when the OpenAPI file cannot be loaded."""


def load_openapi_document(path: str | Path) -> dict[str, Any]:
    input_path = Path(path)
    if not input_path.exists():
        msg = f"Input spec not found: {input_path}"
        raise OpenAPILoadError(msg)

    raw = input_path.read_text(encoding="utf-8")
    suffix = input_path.suffix.lower()

    try:
        if suffix in {".json"}:
            parsed = json.loads(raw)
        elif suffix in {".yaml", ".yml"}:
            parsed = yaml.safe_load(raw)
        else:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = yaml.safe_load(raw)
    except Exception as exc:  # pragma: no cover - defensive parsing path
        msg = f"Unable to parse OpenAPI document at {input_path}: {exc}"
        raise OpenAPILoadError(msg) from exc

    if not isinstance(parsed, dict):
        msg = "OpenAPI document root must be an object"
        raise OpenAPILoadError(msg)

    return parsed
