# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

NVR Pro is a self-hosted, enterprise-grade network video recorder — a Synology Surveillance Station alternative. This is currently in the **specification/planning phase**; the three `.md` files at the repo root define the full system. No source code exists yet. Implementation follows the 15-session roadmap in `SESSION_PROMPTS.md`.

**Read `SPEC.md` completely before writing any code.** It is the canonical authority on every design decision. If anything below conflicts with SPEC.md, SPEC.md wins.

## Locked tech stack

Do not substitute any of these without a new DECISION_LOG.md entry:

| Layer | Choice |
|---|---|
| Backend | Python 3.12 + FastAPI (async) |
| Database | PostgreSQL 16 via asyncpg + SQLAlchemy async |
| Cache/broker | Redis 7.2 |
| Task queue | Celery 5.4 + RedBeat |
| Video | FFmpeg 6 via subprocess (not ffmpeg-python) |
| ONVIF | python-onvif-zeep 0.2.12 with `Settings(strict=False)` |
| Auth | JWT RS256 (asymmetric), argon2 password hashing |
| Encryption | Fernet AES-128-CBC for camera credentials |
| Frontend | React 18 + TypeScript 5 + Vite 5 + shadcn/ui |
| State | TanStack Query v5 (server state) + Zustand (client state) |
| Detection | YOLOv8 (Ultralytics) + ByteTrack (supervision) + Shapely |

## Commands

All commands run inside Docker containers:

```bash
# Start / build
docker compose up -d
docker compose build
docker compose logs -f [backend|worker|detection]

# Backend tests
docker compose exec backend pytest tests/ -v --cov=app --cov-report=term-missing
docker compose exec backend pytest tests/ -v --lf                          # failing only
docker compose exec backend pytest tests/integration/test_auth.py::test_login_lockout -v

# Migrations
docker compose exec backend alembic upgrade head
docker compose exec backend alembic revision --autogenerate -m "description"
docker compose exec backend alembic upgrade head --sql                     # preview SQL
docker compose exec backend alembic downgrade -1

# One-time setup
docker compose exec backend python scripts/generate_keys.py                # RSA + Fernet keys
docker compose exec backend python scripts/seed_roles.py

# Ops
docker compose exec worker celery -A app.celery_app inspect active
docker compose exec worker celery -A app.celery_app call nvr.purge_old_segments
docker compose exec postgres psql -U nvr nvr
docker compose exec redis redis-cli
curl http://localhost:8001/health                                           # detection service

# Frontend
cd frontend && npx playwright test
docker compose exec backend pytest tests/ --cov=app --cov-report=html     # then open htmlcov/index.html
```

## Architecture

Three independent services communicate only via Redis pub/sub — no direct HTTP between backend and detection service.

```
nginx (TLS termination, HLS serving)
  └─ backend/app/          FastAPI — all business logic
       ├─ routers/          HTTP layer only; raises HTTPException
       ├─ services/         Business logic; raises custom exceptions from core/exceptions.py
       ├─ models/           SQLAlchemy ORM (16 models, singular snake_case filenames)
       ├─ schemas/          Pydantic v2 (extra='forbid'), same domain name as models
       ├─ workers/          Celery tasks (must be idempotent)
       ├─ middleware/        Auth, audit, rate limit, security headers
       └─ utils/            ffmpeg.py, encryption.py, onvif_helpers.py

detection_service/         Isolated microservice; YOLOv8 + ByteTrack
  └─ communicates via Redis pub/sub only; reads zone config from Redis key nvr:zones:{camera_id}

frontend/src/
  ├─ pages/               14 page components
  ├─ components/          Domain-grouped UI components
  ├─ api/                 TanStack Query v5 hooks
  └─ store/               Zustand slices
```

Recording storage layout: `/data/recordings/{camera_id}/{YYYY-MM-DD}/{HH-MM-SS}_{type}.mp4`

## Session ritual

Start every implementation session with this exact prompt (paste into Claude):

> Read SPEC.md completely. Before writing any code, confirm you understand:
> 1. JWT algorithm used and why
> 2. How camera passwords are stored and retrieved
> 3. What the detection service is NOT allowed to do
> 4. What happens when storage hits 95%
> 5. What "out of scope" items are listed

Then paste the relevant session prompt from `SESSION_PROMPTS.md`.

## Code standards (non-negotiable)

- All FastAPI routes: `async def`, full type hints, `Depends()` for all shared state — no module-level singletons
- DB access only via `get_db()` dependency; never create sessions directly
- Service layer raises custom exceptions from `core/exceptions.py`; routers translate to `HTTPException`
- No raw f-string SQL — SQLAlchemy ORM or `text()` with explicit params only
- `structlog` everywhere; never `print()`. No secrets in any log line or error message
- Camera credentials decrypted in-memory only when making ONVIF calls; never in API responses
- All file paths via `pathlib.Path.resolve()`; validate path is within `STORAGE_PATH` before use
- All list endpoints paginated (default 50, max 100)
- Celery tasks must be idempotent (check DB state before starting work)
- Alembic migration required for every model change
- Test DB isolation: each test runs in a rolled-back transaction (never a plain session fixture)
- argon2 is intentionally slow (~0.3–0.5 s) — lower `memory_cost` in test conftest only

## Security invariants

These must hold at all times — check at end of sessions 3, 6, 9, 15:

- JWT: RS256 (not HS256), 15-minute access token TTL; refresh tokens are opaque UUIDs stored in DB, rotated on every use with double-spend detection (reuse → revoke all sessions)
- Passwords: argon2 hash only; grep for `password=` to verify no plaintext
- Camera passwords: Fernet-encrypted before DB write; decrypted only for ONVIF calls
- All routes require auth except `/health` and `/auth/login`
- Rate limits: `/auth/login` 10 req/10 min per IP; `/auth/refresh` 60 req/hour per user
- CORS: specific origins only, never `*` in production
- Audit log: every sensitive action appended; no `UPDATE`/`DELETE` on `audit_log`; no secrets in JSONB detail
- Exports: signed URLs only, not direct filesystem paths
- MFA (TOTP): optional per user, mandatory for superadmin

## Known gotchas

- **RTSP URLs with `0.0.0.0`**: always pass through `fix_rtsp_url()` in `onvif_helpers.py`
- **HLS latency 6–10 s**: expected, do not reduce `hls_list_size` below 5
- **ONVIF `WSDLParseError`**: initialize `ONVIFCamera` with `Settings(strict=False)`
- **Detection zone config changes**: backend must publish to `nvr:config:reload:{camera_id}`; config stored in `nvr:zones:{camera_id}` (not only in DB)
- **Large export downloads**: use `StreamingResponse` with `iter_content()` + `Content-Length` header
- **Celery double-run**: check `RUNNING_PROCESSES` dict in worker before starting FFmpeg subprocess

## File naming

```
models/      singular snake_case    camera.py, recording_segment.py
schemas/     same domain name       camera.py  (CameraCreate, CameraResponse…)
routers/     plural snake_case      cameras.py, recordings.py
services/    domain + _service.py   camera_service.py, auth_service.py
workers/     noun for the work      recording.py, purge.py, export.py
utils/       utility name           ffmpeg.py, encryption.py
tests/unit/  test_ + module         test_auth_service.py
tests/int/   test_ + feature        test_camera_flow.py
```

## Implementation progress

```
Phase 1 — Foundation
[x] Session 1  — Infrastructure, scaffold, RSA key generation
[x] Session 2  — All database models and initial migration
[x] Session 3  — Auth service, JWT RS256, argon2, sessions
[x] Session 4  — ONVIF integration service
[x] Session 5  — Recording engine: Celery, FFmpeg, storage

Phase 2 — Core features
[x] Session 6  — User management, roles, audit log, GDPR
[x] Session 7  — Live view: HLS streaming, WebSocket hub
[x] Session 8  — Recordings timeline, clip retrieval, export
[x] Session 9  — Alert system: rules, events, notifications

Phase 3 — Detection + Frontend
[x] Session 10 — Detection microservice (complete)
[x] Session 11 — React frontend: scaffold, auth, layout, dashboard
[x] Session 12 — Frontend: live view and camera management
[x] Session 13 — Frontend: recordings timeline, alerts, users
[x] Session 14 — Storage, settings, system health, notifications UI

Phase 4 — Production
[x] Session 15 — Production hardening, observability, final integration
```

Update this checklist as sessions complete.
