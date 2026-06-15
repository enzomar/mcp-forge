from __future__ import annotations

import asyncio
import tempfile
import zipfile
from pathlib import Path

from api.config import settings
from api.jobs.queue import cleanup_expired, get_queue, update_job
from api.models import JobStatus
from api.security.tokens import generate_token
from api.storage.local import delete_zip


async def process_job(job_id: str, spec_content: bytes, filename: str) -> None:
    try:
        await update_job(job_id, status=JobStatus.PROCESSING, progress_message="Parsing specification…")

        Path(settings.TEMP_PATH).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=settings.TEMP_PATH) as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Write spec to disk
            spec_path = tmpdir_path / filename
            spec_path.write_bytes(spec_content)

            await update_job(job_id, progress_message="Generating MCP server…")

            # Run the generator (sync; runs in thread to avoid blocking event loop)
            output_path = tmpdir_path / "generated"
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _run_generator, spec_path, output_path)

            await update_job(job_id, status=JobStatus.PACKAGING, progress_message="Packaging files…")

            # Build zip
            zip_dest = Path(settings.STORAGE_PATH) / f"{job_id}.zip"
            zip_dest.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_dest, "w", zipfile.ZIP_DEFLATED) as zf:
                for file in sorted(output_path.rglob("*")):
                    if file.is_file() and ".venv" not in file.parts and "__pycache__" not in file.parts:
                        zf.write(file, file.relative_to(output_path))

            # Generate signed download token and expose URL as relative path
            token = generate_token(job_id)
            download_url = f"/download/{token}"

            await update_job(
                job_id,
                status=JobStatus.DONE,
                download_token=token,
                download_url=download_url,
                output_zip=str(zip_dest),
                progress_message="Your server is ready!",
            )

    except Exception as exc:
        await update_job(job_id, status=JobStatus.FAILED, error=str(exc), progress_message="Generation failed.")
        raise


def _run_generator(spec_path: Path, output_path: Path) -> None:
    """Synchronous wrapper around mcp_forge_generator — safe to run in a thread executor."""
    from mcp_forge_generator.generator import generate_project

    generate_project(input_spec=spec_path, output_dir=output_path)


async def worker_loop() -> None:
    """Long-running background task that drains the job queue."""
    queue = get_queue()
    while True:
        job_id, spec_content, filename = await queue.get()
        try:
            await process_job(job_id, spec_content, filename)
        except Exception as exc:
            print(f"[WORKER] job={job_id} failed: {exc}")
        finally:
            queue.task_done()


async def cleanup_loop() -> None:
    """Periodic sweep that removes expired job files and metadata."""
    while True:
        await asyncio.sleep(3600)  # every hour
        try:
            await cleanup_expired()
            print("[CLEANUP] expired jobs removed")
        except Exception as exc:
            print(f"[CLEANUP] error: {exc}")
