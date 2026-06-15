# MCP Forge SaaS

A minimal, zero-friction SaaS that converts OpenAPI/Swagger specs into downloadable FastMCP server packages.

> **Upload → Generate → Email download link → Auto-expire in 12 hours**

## Architecture

```
saas/
├── api/
│   ├── main.py                  # FastAPI app + lifespan (worker & cleanup tasks)
│   ├── config.py                # Pydantic Settings (reads .env)
│   ├── models.py                # Job dataclass + JobStatus enum
│   ├── routes/
│   │   ├── generate.py          # POST /api/generate
│   │   ├── status.py            # GET  /api/status/{job_id}
│   │   └── download.py          # GET  /download/{token}
│   ├── jobs/
│   │   ├── queue.py             # In-memory job store + asyncio queue
│   │   └── processor.py        # Background worker + cleanup loop
│   ├── storage/
│   │   └── local.py             # Filesystem storage (swap for S3)
│   ├── email_service/
│   │   └── sender.py            # SMTP email (console fallback in dev)
│   └── security/
│       ├── tokens.py            # itsdangerous HMAC-signed download tokens
│       └── validators.py        # File/URL validation + SSRF prevention
├── frontend/
│   └── index.html               # Single-page app (pure HTML/CSS/JS)
├── requirements.txt
├── .env.example
├── Dockerfile
└── ../docker-compose.yml  (from repo root)
```

## User Flow

```
1  Upload YAML/JSON file  OR  paste Swagger URL
2  Enter email address
3  Click "Generate MCP Server"
4  Watch real-time progress (Uploading → Generating → Packaging → Sending)
5  Receive email with signed download link (12 h TTL)
6  Download ZIP → unzip → run
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/generate` | Submit spec + email, returns `job_id` |
| GET | `/api/status/{job_id}` | Poll job status + progress message |
| GET | `/download/{token}` | Signed download (expires in 12 h) |

## Security

| Control | Implementation |
|---|---|
| File size limit | `MAX_FILE_SIZE_MB` (default 10 MB) |
| Content validation | Must parse as YAML/JSON with `paths` key |
| SSRF prevention | DNS-resolved hostname checked against private IP ranges |
| Rate limiting | `slowapi` — default 5 req/min per IP |
| Token expiry | `itsdangerous` HMAC-signed URL, `TOKEN_EXPIRY_HOURS` TTL |

## Local Development

### Prerequisites

- Python ≥ 3.10
- [uv](https://docs.astral.sh/uv/)

### Setup

```bash
cd saas
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
# install the generator from local source
uv pip install --python .venv/bin/python -e ../
cp .env.example .env
```

### Run

```bash
cd saas
.venv/bin/python -m uvicorn api.main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000)

> **Email in dev mode**: when `SMTP_HOST` is blank, download links are printed to the console instead of sent.

### Email configuration (production)

Set these in `.env`:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your@gmail.com
SMTP_PASSWORD=app-password-here
SMTP_USE_TLS=true
EMAIL_FROM=noreply@yourdomain.com
```

For transactional email services (Mailgun, Postmark, Resend), use their SMTP relay credentials.

## Docker

```bash
# From the repo root
cp saas/.env.example saas/.env
# edit .env — set SECRET_KEY, BASE_URL, and SMTP credentials
docker compose -f docker-compose.yml up --build
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `BASE_URL` | `http://localhost:8000` | Public URL used in email links |
| `SECRET_KEY` | `change-me` | HMAC signing key — **change in production** |
| `STORAGE_PATH` | `storage/outputs` | Where ZIPs are saved |
| `TEMP_PATH` | `storage/tmp` | Temp dir for generation |
| `TOKEN_EXPIRY_HOURS` | `12` | Download link TTL |
| `MAX_FILE_SIZE_MB` | `10` | Max upload size |
| `RATE_LIMIT_GENERATE` | `5/minute` | slowapi rate limit |
| `SMTP_HOST` | `` | SMTP server (blank = console dev mode) |

## Running the Generated Server

After downloading and unzipping:

```bash
cd <server-name>
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python main.py
```

Defaults to **STDIO transport** — connect via Claude Desktop, Cursor, or MCP Inspector.
