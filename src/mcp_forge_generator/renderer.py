from __future__ import annotations

import keyword
import re
from textwrap import dedent
from typing import Any

from .spec_ir import APISpecIR, Operation, Parameter, SecurityScheme


def _safe_name(value: str) -> str:
    candidate = re.sub(r"[^a-zA-Z0-9_]", "_", value)
    if not candidate:
        candidate = "value"
    if candidate[0].isdigit():
        candidate = f"p_{candidate}"
    if keyword.iskeyword(candidate):
        candidate = f"{candidate}_"
    return candidate


def _pascal(value: str) -> str:
    parts = re.split(r"[^a-zA-Z0-9]", value)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def _py_type(schema: dict[str, Any] | None) -> str:
    if not schema:
        return "Any"
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return _pascal(ref.rsplit("/", 1)[-1])

    schema_type = schema.get("type")
    if schema_type == "string":
        return "str"
    if schema_type == "integer":
        return "int"
    if schema_type == "number":
        return "float"
    if schema_type == "boolean":
        return "bool"
    if schema_type == "array":
        item = schema.get("items") if isinstance(schema.get("items"), dict) else {}
        return f"list[{_py_type(item)}]"
    if schema_type == "object":
        return "dict[str, Any]"
    return "Any"


def _render_models(spec: APISpecIR) -> str:
    classes: list[str] = []
    for schema_name, schema in sorted(spec.schemas.items()):
        cls_name = _pascal(schema_name)
        if schema.get("type") != "object":
            classes.append(f"class {cls_name}(BaseModel):\n    value: {_py_type(schema)}\n")
            continue

        properties = schema.get("properties", {}) if isinstance(schema.get("properties"), dict) else {}
        required = set(schema.get("required", [])) if isinstance(schema.get("required"), list) else set()

        if not properties:
            classes.append(f"class {cls_name}(BaseModel):\n    model_config = ConfigDict(extra='allow')\n")
            continue

        lines = [f"class {cls_name}(BaseModel):"]
        for field_name, field_schema in properties.items():
            if not isinstance(field_schema, dict):
                field_schema = {"type": "string"}
            py_name = _safe_name(field_name)
            field_type = _py_type(field_schema)
            if field_name in required:
                lines.append(f"    {py_name}: {field_type}")
            else:
                lines.append(f"    {py_name}: {field_type} | None = None")
        classes.append("\n".join(lines) + "\n")

    if not classes:
        classes.append("class EmptyModel(BaseModel):\n    pass\n")

    header = dedent(
        """
        from __future__ import annotations

        from typing import Any

        from pydantic import BaseModel, ConfigDict


        class GenericResponse(BaseModel):
            data: Any
        """
    ).strip()
    return header + "\n\n" + "\n\n".join(classes)


def _render_config(spec: APISpecIR) -> str:
    title = spec.title.replace('"', "'")
    base_url = spec.base_url or "https://api.example.com"
    return dedent(
        f"""
        from __future__ import annotations

        from pydantic import Field
        from pydantic_settings import BaseSettings, SettingsConfigDict


        class Settings(BaseSettings):
            model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

            APP_NAME: str = "{title}"
            APP_VERSION: str = "{spec.version}"
            API_BASE_URL: str = "{base_url}"

            ENABLE_CACHE: bool = True
            CACHE_TTL_SECONDS: int = 300
            CACHE_BACKEND: str = Field(default='memory', pattern='^(memory|redis)$')
            REDIS_URL: str = 'redis://redis:6379/0'

            ENABLE_RATE_LIMIT: bool = True
            RATE_LIMIT_PER_MINUTE: int = 100

            ENABLE_RETRIES: bool = True
            MAX_RETRIES: int = 3
            RETRY_BASE_DELAY_MS: int = 200

            TRANSPORT: str = Field(default='stdio', pattern='^(stdio|sse|streamable-http)$')
            SERVER_HOST: str = '0.0.0.0'
            SERVER_PORT: int = 8000

            LOG_LEVEL: str = 'INFO'
            HTTP_TIMEOUT_SECONDS: float = 30.0

            BEARER_TOKEN: str = ''
            API_KEY: str = ''
            BASIC_AUTH_USERNAME: str = ''
            BASIC_AUTH_PASSWORD: str = ''
            CLIENT_ID: str = ''
            CLIENT_SECRET: str = ''
            OAUTH_TOKEN_URL: str = ''

            OTEL_ENABLED: bool = False
            OTEL_SERVICE_NAME: str = 'mcp-generated-server'


        settings = Settings()
        """
    ).strip() + "\n"


def _render_auth(schemes: list[SecurityScheme]) -> str:
    rows = []
    for s in schemes:
        rows.append(
            f"{{'name': {s.name!r}, 'type': {s.type!r}, 'scheme': {s.scheme!r}, 'in': {s.in_!r}}}"
        )
    joined = ",\n    ".join(rows)
    return dedent(
        f"""
        from __future__ import annotations

        import base64

        from config_layer.config import settings


        SECURITY_SCHEMES = [
            {joined}
        ]


        class AuthInjector:
            def inject(self, headers: dict[str, str], params: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
                for scheme in SECURITY_SCHEMES:
                    stype = str(scheme.get('type', ''))
                    sname = str(scheme.get('name', 'X-API-Key'))
                    sscheme = str(scheme.get('scheme', '')).lower()
                    if stype == 'http' and sscheme == 'bearer' and settings.BEARER_TOKEN:
                        headers['Authorization'] = f'Bearer {{settings.BEARER_TOKEN}}'
                    elif stype == 'apiKey' and settings.API_KEY:
                        if str(scheme.get('in', 'header')).lower() == 'query':
                            params[sname] = settings.API_KEY
                        else:
                            headers[sname] = settings.API_KEY
                    elif stype == 'http' and sscheme == 'basic' and settings.BASIC_AUTH_USERNAME:
                        raw = f'{{settings.BASIC_AUTH_USERNAME}}:{{settings.BASIC_AUTH_PASSWORD}}'.encode('utf-8')
                        headers['Authorization'] = 'Basic ' + base64.b64encode(raw).decode('utf-8')
                    elif stype == 'oauth2' and settings.BEARER_TOKEN:
                        headers['Authorization'] = f'Bearer {{settings.BEARER_TOKEN}}'
                return headers, params


        auth_injector = AuthInjector()
        """
    ).strip() + "\n"


def _resource_graph(spec: APISpecIR) -> str:
    graph: dict[str, set[str]] = {}
    for op in spec.operations:
        for dep in op.dependencies:
            graph.setdefault(dep, set()).add(op.resource)
    lines = [f"    {key!r}: {sorted(value)!r}," for key, value in sorted(graph.items())]
    if not lines:
        lines.append("    'default': ['default'],")
    return "\n".join(lines)


def _render_cache(spec: APISpecIR) -> str:
    graph_literal = _resource_graph(spec)
    template = dedent("""
from __future__ import annotations

import json
import time
from typing import Any, Awaitable, Callable

from config_layer.config import settings

try:
    import redis.asyncio as redis
except Exception:
    redis = None


CACHE_METRICS = {'cache_hits': 0, 'cache_misses': 0, 'cache_invalidations': 0}


class BaseCache:
    async def get(self, key: str) -> Any | None:
        raise NotImplementedError

    async def set(self, key: str, value: Any, ttl: int) -> None:
        raise NotImplementedError

    async def invalidate_prefix(self, prefix: str) -> int:
        raise NotImplementedError


class InMemoryCache(BaseCache):
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}

    async def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: Any, ttl: int) -> None:
        self._store[key] = (time.time() + ttl, value)

    async def invalidate_prefix(self, prefix: str) -> int:
        keys = [k for k in self._store if k.startswith(prefix)]
        for key in keys:
            self._store.pop(key, None)
        return len(keys)


class RedisCache(BaseCache):
    def __init__(self) -> None:
        if redis is None:
            msg = 'redis package is required for CACHE_BACKEND=redis'
            raise RuntimeError(msg)
        self._client = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def get(self, key: str) -> Any | None:
        payload = await self._client.get(key)
        return json.loads(payload) if payload else None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        await self._client.set(key, json.dumps(value, default=str), ex=ttl)

    async def invalidate_prefix(self, prefix: str) -> int:
        deleted = 0
        async for key in self._client.scan_iter(match=prefix + '*'):
            deleted += await self._client.delete(key)
        return deleted


class ResourceGraph:
    def __init__(self) -> None:
        self._graph: dict[str, list[str]] = {
""" + graph_literal + """
        }

    def dependents(self, resource: str) -> set[str]:
        seen: set[str] = set()
        stack = [resource]
        while stack:
            node = stack.pop()
            for dep in self._graph.get(node, []):
                if dep not in seen:
                    seen.add(dep)
                    stack.append(dep)
        return seen


_cache: BaseCache = InMemoryCache() if settings.CACHE_BACKEND == 'memory' else RedisCache()
_graph = ResourceGraph()


def _build_key(resource: str, operation: str, kwargs: dict[str, Any]) -> str:
    parts = [resource, operation]
    for name in sorted(kwargs):
        if name == 'request_id':
            continue
        value = kwargs[name]
        if value is not None:
            parts.append(str(value))
    return ':'.join(parts)


async def invalidate_resource(resource: str) -> None:
    targets = {resource} | _graph.dependents(resource)
    removed = 0
    for target in targets:
        removed += await _cache.invalidate_prefix(target + ':')
    CACHE_METRICS['cache_invalidations'] += removed


def smart_cache(resource: str, operation: str, ttl: int | None = None) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not settings.ENABLE_CACHE:
                return await func(*args, **kwargs)
            key = _build_key(resource, operation, kwargs)
            cached = await _cache.get(key)
            if cached is not None:
                CACHE_METRICS['cache_hits'] += 1
                return cached
            CACHE_METRICS['cache_misses'] += 1
            result = await func(*args, **kwargs)
            await _cache.set(key, result, ttl or settings.CACHE_TTL_SECONDS)
            return result

        return wrapper

    return decorator
""")
    return template.strip() + "\n"


def _tool_signature(op: Operation) -> str:
    args: list[str] = []
    for param in op.parameters:
        name = _safe_name(param.name)
        annotation = _py_type(param.schema)
        if param.required or param.location == "path":
            args.append(f"{name}: {annotation}")
        else:
            args.append(f"{name}: {annotation} | None = None")

    if op.request_body and op.request_body.model_name:
        model_name = _pascal(op.request_body.model_name)
        if op.request_body.required:
            args.append(f"payload: {model_name}")
        else:
            args.append(f"payload: {model_name} | None = None")

    args.append("request_id: str | None = None")
    return ", ".join(args)


def _tool_description(op: Operation) -> str:
    pieces: list[str] = []
    if op.summary:
        pieces.append(op.summary)
    if op.description:
        pieces.append(op.description)
    if op.parameters:
        summary = "; ".join(f"{p.name}: {p.description or 'n/a'}" for p in op.parameters)
        pieces.append(f"Parameters: {summary}")
    return "\\n".join(pieces)


def _map_for_location(op: Operation, location: str) -> str:
    entries = [f'"{p.name}": {_safe_name(p.name)}' for p in op.parameters if p.location == location]
    return "{" + ", ".join(entries) + "}"


def _render_tools(spec: APISpecIR) -> str:
    blocks: list[str] = []
    for op in spec.operations:
        sig = _tool_signature(op)
        query_map = _map_for_location(op, "query")
        path_map = _map_for_location(op, "path")
        invalidates = "{" + ", ".join(f'"{x}"' for x in sorted(op.invalidates)) + "}"
        payload_expr = "payload.model_dump(exclude_none=True) if 'payload' in locals() and payload is not None else None"
        cache_deco = ""
        if op.cacheable:
            cache_deco = f"@smart_cache(resource=\"{op.resource}\", operation=\"{op.operation_id}\")\n"
        description_literal = repr(_tool_description(op))

        function_src = (
            f"{cache_deco}"
            f"@rate_limited('{op.operation_id}')\n"
            f"@mcp.tool(name='{op.operation_id}', description={description_literal})\n"
            f"async def {op.operation_id}({sig}) -> dict[str, Any]:\n"
            f"    return await api_service.invoke(\n"
            f"        operation_id='{op.operation_id}',\n"
            f"        method='{op.method}',\n"
            f"        path_template='{op.path}',\n"
            f"        path_params={path_map},\n"
            f"        query_params={query_map},\n"
            f"        payload={payload_expr},\n"
            f"        invalidates={invalidates},\n"
            f"        cache_hit={'True' if op.cacheable else 'False'},\n"
            f"    )\n"
        )
        blocks.append(function_src)

    header = dedent(
        """
        from __future__ import annotations

        from typing import Any

        from fastmcp import FastMCP

        from cache_layer.cache import smart_cache
        from config_layer.config import settings
        from models_layer.models import *  # noqa: F403
        from services_layer.api_service import api_service
        from services_layer.rate_limit import rate_limited

        mcp = FastMCP(name=settings.APP_NAME)
        """
    ).strip()
    return header + "\n\n" + "\n\n".join(blocks)


def _render_main() -> str:
    return dedent(
        """
        from __future__ import annotations

        import asyncio

        from config_layer.config import settings
        from services_layer.logging import configure_logging
        try:
            from tools import mcp
        except ModuleNotFoundError as exc:
            if exc.name in {'fastmcp', 'httpx', 'pydantic', 'pydantic_settings'}:
                msg = (
                    'Missing runtime dependency. Install generated server dependencies with '\
                    '"uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt" '\
                    'before running main.py.'
                )
                raise SystemExit(msg) from exc
            raise


        async def run() -> None:
            configure_logging()
            if settings.TRANSPORT == 'stdio':
                await mcp.run_async(transport='stdio')
            elif settings.TRANSPORT == 'sse':
                await mcp.run_async(transport='sse', host=settings.SERVER_HOST, port=settings.SERVER_PORT)
            else:
                await mcp.run_async(transport='streamable-http', host=settings.SERVER_HOST, port=settings.SERVER_PORT)


        if __name__ == '__main__':
            asyncio.run(run())
        """
    ).strip() + "\n"


def _render_services() -> dict[str, str]:
    return {
        "services_layer/__init__.py": dedent(
            """
            # Keep package imports lazy so startup does not require optional runtime deps.
            __all__ = []
            """
        ).strip()
        + "\n",
        "services_layer/logging.py": dedent(
            """
            from __future__ import annotations

            import json
            import logging
            import sys
            from typing import Any

            from config_layer.config import settings


            class JsonFormatter(logging.Formatter):
                def format(self, record: logging.LogRecord) -> str:
                    payload: dict[str, Any] = {
                        'level': record.levelname,
                        'logger': record.name,
                        'message': record.getMessage(),
                    }
                    if hasattr(record, 'event'):
                        payload.update(getattr(record, 'event'))
                    return json.dumps(payload, default=str)


            def configure_logging() -> None:
                root = logging.getLogger()
                root.setLevel(settings.LOG_LEVEL)
                stream = sys.stderr if settings.TRANSPORT == 'stdio' else sys.stdout
                handler = logging.StreamHandler(stream)
                handler.setFormatter(JsonFormatter())
                root.handlers = [handler]
            """
        ).strip()
        + "\n",
        "services_layer/observability.py": dedent(
            """
            from __future__ import annotations

            from contextlib import asynccontextmanager
            from typing import Any

            from config_layer.config import settings

            try:
                from opentelemetry import trace
            except Exception:
                trace = None


            @asynccontextmanager
            async def traced(name: str, attrs: dict[str, Any] | None = None):
                if not settings.OTEL_ENABLED or trace is None:
                    yield
                    return
                tracer = trace.get_tracer(settings.OTEL_SERVICE_NAME)
                with tracer.start_as_current_span(name) as span:
                    if attrs:
                        for key, value in attrs.items():
                            span.set_attribute(key, value)
                    yield
            """
        ).strip()
        + "\n",
        "services_layer/rate_limit.py": dedent(
            """
            from __future__ import annotations

            import asyncio
            import time
            from collections import defaultdict
            from typing import Any, Awaitable, Callable

            from config_layer.config import settings


            class TokenBucket:
                def __init__(self) -> None:
                    self.capacity = max(settings.RATE_LIMIT_PER_MINUTE, 1)
                    self.tokens = float(self.capacity)
                    self.refill_per_sec = self.capacity / 60.0
                    self.last = time.monotonic()

                def allow(self) -> bool:
                    now = time.monotonic()
                    elapsed = now - self.last
                    self.last = now
                    self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
                    if self.tokens >= 1:
                        self.tokens -= 1
                        return True
                    return False


            _buckets: dict[str, TokenBucket] = defaultdict(TokenBucket)


            def rate_limited(operation_id: str) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
                def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
                    async def wrapper(*args: Any, **kwargs: Any) -> Any:
                        if settings.ENABLE_RATE_LIMIT:
                            while not _buckets[operation_id].allow():
                                await asyncio.sleep(0.05)
                        return await func(*args, **kwargs)

                    return wrapper

                return decorator
            """
        ).strip()
        + "\n",
        "services_layer/http_client.py": dedent(
            """
            from __future__ import annotations

            import asyncio
            import random
            from typing import Any

            try:
                import httpx
            except Exception:
                httpx = None

            from auth_layer.auth import auth_injector
            from config_layer.config import settings
            from services_layer.observability import traced

            RETRYABLE = {429, 500, 502, 503, 504}
            _client: httpx.AsyncClient | None = None


            async def get_client() -> httpx.AsyncClient:
                global _client
                if httpx is None:
                    msg = (
                        'Missing dependency: httpx. Install generated server dependencies with '
                        '"uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt".'
                    )
                    raise RuntimeError(msg)
                if _client is None:
                    limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
                    timeout = httpx.Timeout(settings.HTTP_TIMEOUT_SECONDS)
                    _client = httpx.AsyncClient(http2=True, timeout=timeout, limits=limits)
                return _client


            async def request_with_retry(
                *,
                method: str,
                url: str,
                params: dict[str, Any],
                headers: dict[str, str],
                payload: dict[str, Any] | None,
                operation_id: str,
            ) -> httpx.Response:
                headers, params = auth_injector.inject(headers, {k: str(v) for k, v in params.items() if v is not None})
                client = await get_client()
                retries = settings.MAX_RETRIES if settings.ENABLE_RETRIES else 0

                for attempt in range(retries + 1):
                    async with traced('external_api_call', {'operation_id': operation_id, 'attempt': attempt}):
                        response = await client.request(method=method, url=url, params=params, headers=headers, json=payload)
                    if response.status_code not in RETRYABLE or attempt == retries:
                        return response
                    delay = (settings.RETRY_BASE_DELAY_MS / 1000.0) * (2**attempt)
                    delay += random.uniform(0, delay / 4)
                    await asyncio.sleep(delay)
                return response
            """
        ).strip()
        + "\n",
        "services_layer/api_service.py": dedent(
            """
            from __future__ import annotations

            import logging
            import time
            import uuid
            from typing import Any

            from cache_layer.cache import CACHE_METRICS, invalidate_resource
            from config_layer.config import settings
            from services_layer.http_client import request_with_retry
            from services_layer.observability import traced

            logger = logging.getLogger('mcp.api')


            class APIService:
                async def invoke(
                    self,
                    *,
                    operation_id: str,
                    method: str,
                    path_template: str,
                    path_params: dict[str, Any],
                    query_params: dict[str, Any],
                    payload: dict[str, Any] | None,
                    invalidates: set[str],
                    cache_hit: bool,
                ) -> Any:
                    request_id = str(uuid.uuid4())
                    path = path_template
                    for key, value in path_params.items():
                        path = path.replace('{' + key + '}', str(value))
                    url = settings.API_BASE_URL.rstrip('/') + path

                    started = time.perf_counter()
                    async with traced('tool_execution', {'operation_id': operation_id, 'request_id': request_id}):
                        response = await request_with_retry(
                            method=method,
                            url=url,
                            params=query_params,
                            headers={'x-request-id': request_id},
                            payload=payload,
                            operation_id=operation_id,
                        )
                    duration_ms = int((time.perf_counter() - started) * 1000)

                    if response.status_code >= 400:
                        logger.error('external_api_failure', extra={'event': {'operation_id': operation_id, 'status_code': response.status_code, 'duration_ms': duration_ms}})
                        response.raise_for_status()

                    for pattern in invalidates:
                        await invalidate_resource(pattern.split(':', 1)[0])

                    logger.info(
                        'tool_execution',
                        extra={
                            'event': {
                                'request_id': request_id,
                                'operation_id': operation_id,
                                'duration_ms': duration_ms,
                                'cache_hit': cache_hit,
                                'status_code': response.status_code,
                                'cache_hits': CACHE_METRICS['cache_hits'],
                                'cache_misses': CACHE_METRICS['cache_misses'],
                                'cache_invalidations': CACHE_METRICS['cache_invalidations'],
                            }
                        },
                    )

                    if 'application/json' in response.headers.get('content-type', ''):
                        return response.json()
                    return {'raw': response.text}


            api_service = APIService()
            """
        ).strip()
        + "\n",
    }


def _security_envs(schemes: list[SecurityScheme]) -> list[str]:
    envs: set[str] = {
        "API_KEY=",
        "BEARER_TOKEN=",
        "BASIC_AUTH_USERNAME=",
        "BASIC_AUTH_PASSWORD=",
        "CLIENT_ID=",
        "CLIENT_SECRET=",
        "OAUTH_TOKEN_URL=",
    }
    for s in schemes:
        st = s.type.lower()
        if st == "apikey":
            envs.add("API_KEY=")
        elif st == "oauth2":
            envs.add("CLIENT_ID=")
            envs.add("CLIENT_SECRET=")
    return sorted(envs)


def _render_makefile() -> str:
    return dedent(
        """
        .PHONY: install run run-dev run-http clean test lint format type-check help

        help:
        \t@echo "MCP Server - Available Commands"
        \t@echo "================================"
        \t@echo "make install       - Install dependencies"
        \t@echo "make run           - Run server (streamable-http, 8000)"
        \t@echo "make run-dev       - Run server with auto-reload"
        \t@echo "make run-sse       - Run server with SSE transport"
        \t@echo "make clean         - Remove pycache and build artifacts"
        \t@echo "make test          - Run tests"
        \t@echo "make lint          - Run linting"
        \t@echo "make format        - Format code with black"
        \t@echo "make type-check    - Run type checking"

        install:
        	uv venv .venv
        	uv pip install --python .venv/bin/python -r requirements.txt

        run:
        	TRANSPORT=streamable-http .venv/bin/python main.py

        run-dev:
        	TRANSPORT=streamable-http .venv/bin/python main.py

        run-sse:
        	TRANSPORT=sse .venv/bin/python main.py

        clean:
        	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
        \tfind . -type f -name "*.pyc" -delete 2>/dev/null || true
        \trm -rf .pytest_cache dist build *.egg-info 2>/dev/null || true

        test:
        \tpytest -v

        lint:
        \truff check .
        \tblack --check .

        format:
        \tblack .
        \truff check --fix .

        type-check:
        \tmypy .
        """
    ).strip() + "\n"


def _render_start_bat() -> str:
    return dedent(
        """
        @echo off
        REM MCP Server Startup Script for Windows
        REM Starts the server in streamable-http mode on localhost:8000

        setlocal enabledelayedexpansion

        where uv >nul 2>&1
        if errorlevel 1 (
            echo uv is required but not found in PATH.
            echo Install uv from https://docs.astral.sh/uv/
            exit /b 1
        )

        REM Check if .venv exists
        if not exist ".venv" (
            echo Creating virtual environment...
            uv venv .venv
            echo Installing dependencies...
            uv pip install --python .venv\\Scripts\\python.exe -r requirements.txt
        )

        REM Start the server
        echo.
        echo Starting MCP Server...
        echo Transport: streamable-http
        echo URL: http://localhost:8000
        echo.

        set TRANSPORT=streamable-http
        .venv\\Scripts\\python.exe main.py

        pause
        """
    ).strip() + "\n"


def _render_readme(spec: APISpecIR) -> str:
    title = spec.title
    base_url = spec.base_url or "https://api.example.com"
    op_count = len(spec.operations)
    tool_list = "\n".join(
        f"- `{op.operation_id}` \u2014 {op.method} {op.path}" + (f" \u2014 {op.summary}" if op.summary else "")
        for op in spec.operations
    )
    # Build the readme without leading indent so dedent works cleanly
    lines: list[str] = [
        f"# {title} \u2014 MCP Server",
        "",
        "Production-ready FastMCP server auto-generated from an OpenAPI/Swagger spec by",
        "[MCP Forge Generator](https://github.com/your-org/mcp-forge-generator).",
        "",
        f"> **{op_count} MCP tools** wrapping `{base_url}`",
        "",
        "## Available Tools",
        "",
        tool_list,
        "",
        "## Requirements",
        "",
        "- Python \u2265 3.10",
        "- [uv](https://docs.astral.sh/uv/) \u2014 `curl -LsSf https://astral.sh/uv/install.sh | sh`",
        "",
        "## Setup",
        "",
        "```bash",
        "# 1. Create virtual environment and install deps",
        "uv venv .venv",
        "uv pip install --python .venv/bin/python -r requirements.txt",
        "",
        "# 2. Copy and configure environment variables",
        "cp .env.example .env",
        "$EDITOR .env",
        "```",
        "",
        "Key variables in `.env`:",
        "",
        "| Variable | Default | Description |",
        "|---|---|---|",
        f"| `API_BASE_URL` | `{base_url}` | Upstream API base URL |",
        "| `TRANSPORT` | `stdio` | `stdio` or `sse` or `streamable-http` |",
        "| `SERVER_HOST` | `0.0.0.0` | Bind address (HTTP transports) |",
        "| `SERVER_PORT` | `8000` | Port (HTTP transports) |",
        "| `ENABLE_CACHE` | `true` | Toggle response caching |",
        "| `CACHE_BACKEND` | `memory` | `memory` or `redis` |",
        "| `CACHE_TTL_SECONDS` | `300` | Cache entry lifetime |",
        "| `ENABLE_RATE_LIMIT` | `true` | Toggle rate limiting |",
        "| `RATE_LIMIT_PER_MINUTE` | `100` | Requests per minute per operation |",
        "| `ENABLE_RETRIES` | `true` | Toggle retry logic |",
        "| `MAX_RETRIES` | `3` | Retry attempts on 429/5xx |",
        "| `BEARER_TOKEN` | `` | Bearer auth token |",
        "| `API_KEY` | `` | API key |",
        "| `LOG_LEVEL` | `INFO` | Logging level |",
        "",
        "## Run",
        "",
        "### macOS / Linux",
        "",
        "```bash",
        "# STDIO (default \u2014 used by Claude Desktop, Cursor, MCP Inspector)",
        ".venv/bin/python main.py",
        "",
        "# Or use make",
        "make install   # first time only",
        "make run       # streamable-http on :8000",
        "make run-sse   # SSE on :8000",
        "```",
        "",
        "### Windows",
        "",
        "```bat",
        "start.bat",
        "```",
        "",
        "## MCP Client Configuration",
        "",
        "### MCP Inspector (STDIO)",
        "",
        "| Field | Value |",
        "|---|---|",
        "| Transport | STDIO |",
        "| Server Script Path | `/absolute/path/to/.venv/bin/python` |",
        "| Script Arguments | `/absolute/path/to/main.py` |",
        "",
        "### MCP Inspector (Streamable HTTP)",
        "",
        "Start the server first:",
        "```bash",
        "TRANSPORT=streamable-http .venv/bin/python main.py",
        "```",
        "Then connect Inspector to: `http://localhost:8000/mcp`",
        "",
        "### Claude Desktop",
        "",
        "Add to `claude_desktop_config.json`:",
        "```json",
        "{",
        '  "mcpServers": {',
        f'    "{title.lower().replace(" ", "-")}": {{',
        '      "command": "/absolute/path/to/.venv/bin/python",',
        '      "args": ["/absolute/path/to/main.py"]',
        "    }",
        "  }",
        "}",
        "```",
        "",
        "### Cursor",
        "",
        "Add to `.cursor/mcp.json`:",
        "```json",
        "{",
        '  "mcpServers": {',
        f'    "{title.lower().replace(" ", "-")}": {{',
        '      "command": "/absolute/path/to/.venv/bin/python",',
        '      "args": ["/absolute/path/to/main.py"]',
        "    }",
        "  }",
        "}",
        "```",
        "",
        "### OpenAI / HTTP clients",
        "",
        "```bash",
        "TRANSPORT=streamable-http .venv/bin/python main.py",
        "# Server URL: http://localhost:8000",
        "```",
        "",
        "## Docker",
        "",
        "```bash",
        "docker compose up --build",
        "# Runs in streamable-http mode on :8000",
        "```",
        "",
        "Includes a Redis sidecar for `CACHE_BACKEND=redis`.",
        "",
        "## Project Layout",
        "",
        "```",
        ".",
        "\u251c\u2500\u2500 main.py                    # Entrypoint",
        "\u251c\u2500\u2500 tools.py                   # MCP tool definitions",
        "\u251c\u2500\u2500 auth_layer/auth.py         # Auth injection",
        "\u251c\u2500\u2500 cache_layer/cache.py       # Caching layer",
        "\u251c\u2500\u2500 config_layer/config.py     # Pydantic Settings",
        "\u251c\u2500\u2500 models_layer/models.py     # Request/response models",
        "\u251c\u2500\u2500 services_layer/",
        "\u2502   \u251c\u2500\u2500 api_service.py",
        "\u2502   \u251c\u2500\u2500 http_client.py",
        "\u2502   \u251c\u2500\u2500 logging.py",
        "\u2502   \u251c\u2500\u2500 observability.py",
        "\u2502   \u2514\u2500\u2500 rate_limit.py",
        "\u251c\u2500\u2500 Makefile",
        "\u251c\u2500\u2500 start.bat",
        "\u251c\u2500\u2500 Dockerfile",
        "\u251c\u2500\u2500 docker-compose.yml",
        "\u2514\u2500\u2500 .env.example",
        "```",
        "",
        "## Quality",
        "",
        "```bash",
        ".venv/bin/python -m pytest -v",
        ".venv/bin/python -m ruff check .",
        ".venv/bin/python -m black --check .",
        ".venv/bin/python -m mypy .",
        "```",
    ]
    return "\n".join(lines) + "\n"


def render_generated_files(spec: APISpecIR) -> dict[str, str]:
    env_lines = [
        f"API_BASE_URL={spec.base_url or 'https://api.example.com'}",
        "",
        "ENABLE_CACHE=true",
        "CACHE_TTL_SECONDS=300",
        "CACHE_BACKEND=memory",
        "REDIS_URL=redis://redis:6379/0",
        "",
        "ENABLE_RATE_LIMIT=true",
        "RATE_LIMIT_PER_MINUTE=100",
        "",
        "ENABLE_RETRIES=true",
        "MAX_RETRIES=3",
        "RETRY_BASE_DELAY_MS=200",
        "",
        "TRANSPORT=stdio",
        "SERVER_HOST=0.0.0.0",
        "SERVER_PORT=8000",
        "",
        "LOG_LEVEL=INFO",
        "HTTP_TIMEOUT_SECONDS=30",
        "",
        "OTEL_ENABLED=false",
        "OTEL_SERVICE_NAME=mcp-generated-server",
        "",
        *_security_envs(spec.security_schemes),
    ]

    files: dict[str, str] = {
        "main.py": _render_main(),
        "config_layer/config.py": _render_config(spec),
        "cache_layer/cache.py": _render_cache(spec),
        "auth_layer/auth.py": _render_auth(spec.security_schemes),
        "models_layer/models.py": _render_models(spec),
        "tools.py": _render_tools(spec),
        "requirements.txt": dedent(
            """
            fastmcp>=2.0.0
            httpx[http2]>=0.27.0
            pydantic>=2.8.0
            pydantic-settings>=2.3.0
            redis>=5.0.7
            opentelemetry-api>=1.26.0
            opentelemetry-sdk>=1.26.0
            opentelemetry-exporter-otlp>=1.26.0
            black>=24.8.0
            ruff>=0.6.8
            mypy>=1.11.2
            pytest>=8.3.2
            """
        ).strip()
        + "\n",
        "Dockerfile": dedent(
            """
            FROM python:3.12-slim AS builder
            WORKDIR /build
            COPY requirements.txt ./
            RUN pip install --no-cache-dir --upgrade pip && \
                pip install --no-cache-dir --prefix=/install -r requirements.txt

            FROM python:3.12-slim AS runtime
            RUN useradd --create-home --uid 10001 appuser
            WORKDIR /app
            ENV TRANSPORT=streamable-http
            COPY --from=builder /install /usr/local
            COPY . /app
            RUN chown -R appuser:appuser /app
            USER appuser
            EXPOSE 8000
            HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
              CMD python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1', 8000)); s.close()" || exit 1
            CMD ["python", "main.py"]
            """
        ).strip()
        + "\n",
        "docker-compose.yml": dedent(
            """
            services:
              mcp-server:
                build:
                  context: .
                env_file:
                  - .env
                                environment:
                                    - TRANSPORT=streamable-http
                ports:
                  - "8000:8000"
                depends_on:
                  - redis

              redis:
                image: redis:7-alpine
                ports:
                  - "6379:6379"
            """
        ).strip()
        + "\n",
        "README.md": _render_readme(spec),
        ".env.example": "\n".join(env_lines) + "\n",
        "pyproject.toml": dedent(
            """
            [tool.black]
            line-length = 100
            target-version = ["py312"]

            [tool.ruff]
            line-length = 100
            target-version = "py312"

            [tool.ruff.lint]
            select = ["E", "F", "I", "UP", "B"]
            ignore = ["E501"]

            [tool.mypy]
            python_version = "3.12"
            strict = true
            """
        ).strip()
        + "\n",
        "pytest.ini": "[pytest]\npythonpath = .\n",
        "Makefile": _render_makefile(),
        "start.bat": _render_start_bat(),
    }

    files.update(_render_services())
    files.update(
        {
            "cache_layer/__init__.py": dedent(
                """
                from .cache import (
                    CACHE_METRICS,
                    BaseCache,
                    InMemoryCache,
                    RedisCache,
                    ResourceGraph,
                    invalidate_resource,
                    smart_cache,
                )

                __all__ = [
                    'CACHE_METRICS',
                    'BaseCache',
                    'InMemoryCache',
                    'RedisCache',
                    'ResourceGraph',
                    'invalidate_resource',
                    'smart_cache',
                ]
                """
            ).strip()
            + "\n",
            "auth_layer/__init__.py": dedent(
                """
                from .auth import AuthInjector, SECURITY_SCHEMES, auth_injector

                __all__ = ['AuthInjector', 'SECURITY_SCHEMES', 'auth_injector']
                """
            ).strip()
            + "\n",
            "models_layer/__init__.py": dedent(
                """
                from .models import *  # noqa: F401, F403
                """
            ).strip()
            + "\n",
            "config_layer/__init__.py": dedent(
                """
                from .config import settings

                __all__ = ['settings']
                """
            ).strip()
            + "\n",
        }
    )
    return files
