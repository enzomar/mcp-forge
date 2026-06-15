from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.config import settings
from api.jobs.processor import cleanup_loop, worker_loop
from api.routes import download, generate, status

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_GENERATE])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Ensure directories exist
    Path(settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    Path(settings.TEMP_PATH).mkdir(parents=True, exist_ok=True)

    # Start background tasks
    worker_task = asyncio.create_task(worker_loop(), name="mcp-worker")
    cleanup_task = asyncio.create_task(cleanup_loop(), name="mcp-cleanup")
    print(f"[STARTUP] Worker and cleanup tasks started. BASE_URL={settings.BASE_URL}")

    yield

    worker_task.cancel()
    cleanup_task.cancel()
    print("[SHUTDOWN] Background tasks cancelled.")


app = FastAPI(
    title="MCP Forge",
    description="Turn any OpenAPI/Swagger spec into a ready-to-run FastMCP server.",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# CORS — tighten in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# API routes
app.include_router(generate.router, prefix="/api")
app.include_router(status.router, prefix="/api")
app.include_router(download.router)  # /download/{token} at root

# Serve frontend
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
async def serve_index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html", media_type="text/html")

