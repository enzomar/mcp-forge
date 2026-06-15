from __future__ import annotations

from pathlib import Path

from .analyzer import build_ir
from .openapi_loader import load_openapi_document
from .renderer import render_generated_files


def generate_project(input_spec: str | Path, output_dir: str | Path) -> None:
    document = load_openapi_document(input_spec)
    ir = build_ir(document)
    files = render_generated_files(ir)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for relative_path, content in files.items():
        target = out / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
