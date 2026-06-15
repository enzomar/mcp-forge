# MCP Forge Generator

**MCP Forge Generator** turns any OpenAPI 3.x or Swagger 2 spec (YAML or JSON) into a production-ready [FastMCP](https://gofastmcp.com) server in seconds.

## Features

| Feature | Details |
|---|---|
| **One tool per operation** | Every OpenAPI path+method becomes an async MCP tool |
| **Transports** | STDIO (default), SSE, Streamable HTTP |
| **Layer architecture** | `auth_layer`, `cache_layer`, `config_layer`, `models_layer`, `services_layer` |
| **Pydantic models** | Request/response schemas auto-generated from `components/schemas` |
| **Auth injection** | Bearer token, API key (header/query), HTTP Basic, OAuth2 client credentials |
| **Smart caching** | Resource-aware in-memory or Redis cache with dependency graph invalidation |
| **Rate limiting** | Per-operation token bucket (configurable per-minute limit) |
| **Retry with backoff** | Jittered exponential backoff on 429/5xx responses |
| **Structured logging** | JSON logs to stderr (stdio-safe) or stdout for HTTP transports |
| **OpenTelemetry** | Optional OTLP tracing hooks |
| **Docker ready** | Multi-stage Dockerfile + docker-compose with Redis sidecar |
| **Dev tooling** | Ruff, Black, Mypy, Pytest pre-configured in generated output |
| **Startup scripts** | `Makefile` (macOS/Linux) and `start.bat` (Windows) using `uv` |

## Requirements

- Python ≥ 3.10
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

## Installation

```bash
git clone <this-repo>
cd mcp-forge-generator
uv venv .venv
uv pip install --python .venv/bin/python -e .[dev]
```

Activate the environment before running commands:

```bash
source .venv/bin/activate   # macOS/Linux
.venv\Scripts\activate      # Windows
```

## Usage

### Non-interactive

```bash
mcp-forge --input petstore.yaml --output generated_server
```

### Interactive (press Enter to accept defaults)

```bash
mcp-forge --interactive
# OpenAPI spec path [petstore.yaml]:
# Output directory [generated_server]:
```

### Python module

```bash
python -m mcp_forge_generator.cli --input petstore.json --output generated_server
```

## Generated Project Layout

```
generated_server/
├── main.py                    # Entrypoint — defaults to STDIO transport
├── tools.py                   # One @mcp.tool per OpenAPI operation
├── auth_layer/
│   ├── __init__.py
│   └── auth.py                # Auth injection (Bearer / API key / Basic / OAuth2)
├── cache_layer/
│   ├── __init__.py
│   └── cache.py               # In-memory or Redis cache + resource graph
├── config_layer/
│   ├── __init__.py
│   └── config.py              # Pydantic Settings (reads .env)
├── models_layer/
│   ├── __init__.py
│   └── models.py              # Auto-generated Pydantic request/response models
├── services_layer/
│   ├── api_service.py         # HTTP invocation + cache invalidation + logging
│   ├── http_client.py         # httpx client with retry + backoff
│   ├── logging.py             # JSON structured logger
│   ├── observability.py       # OpenTelemetry tracing context manager
│   └── rate_limit.py          # Token bucket rate limiter
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── Makefile                   # macOS/Linux helper targets
├── start.bat                  # Windows startup script
├── .env.example               # All environment variables with defaults
└── README.md
```

## Included Sample

A complete Swagger Petstore spec is included as a quick-start:

```bash
mcp-forge --input petstore.yaml --output generated_server
```

## Validate the Generator

```bash
ruff check .
black --check .
mypy src
pytest
```
