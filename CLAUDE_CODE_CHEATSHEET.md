# NVR Pro — Claude Code Working Guide
# Keep this open alongside the terminal. These patterns prevent the most common mistakes.

---

## Session ritual (every time, no exceptions)

```bash
# 1. Navigate to project root
cd nvr-pro/

# 2. Open Claude Code
claude

# 3. First message — always this exact opener:
```
Read SPEC.md completely. Before writing any code, confirm you understand:
1. JWT algorithm used and why
2. How camera passwords are stored and retrieved  
3. What the detection service is NOT allowed to do
4. What happens when storage hits 95%
5. What "out of scope" items are listed
```

# 4. Wait for answers. If any answer is wrong, correct it before continuing.
# 5. Paste the session prompt from SESSION_PROMPTS.md.
```

---

## Mid-session control phrases

### Slow Claude Code down
```
Stop. Do not write code yet.
First explain your plan: which files you will create, what each will contain,
and what external dependencies each file has. I will approve before you start.
```

### When output looks wrong
```
Stop. This doesn't match SPEC.md section [X]. 
Re-read that section. Explain the discrepancy. Then fix it.
```

### When Claude Code starts adding features you didn't ask for
```
Revert [filename]. That was out of scope for this session.
Implement ONLY what the session prompt specified.
```

### When tests fail and Claude Code is going in circles
```
Stop trying to fix it. Instead:
1. Read the full error output carefully
2. Explain in plain language what is failing and why
3. Propose ONE fix
4. Wait for my approval before implementing
```

### Session end / handoff
```
Before we close this session:
1. Run the full test suite and show me the output
2. List every file you created or modified
3. List any SPEC.md requirements you deferred or could not implement
4. What assumptions did you make that I should know about?
5. Write a one-paragraph summary I can use to start the next session
```

---

## Code patterns to enforce

These are non-negotiable. Paste as a standing instruction at session start
if you notice violations.

```
Standing rules for all code in this session:
- All FastAPI routes: async def, full type hints, Depends() for all deps
- No direct DB session creation: only via get_db() dependency
- No plaintext secrets in logs, responses, or error messages  
- Camera passwords: only decrypted in memory when making ONVIF calls
- All file path operations: use pathlib.Path, never string concatenation
- All errors: raise custom exceptions from core/exceptions.py, not generic Exception
- All DB queries: SQLAlchemy ORM, never raw f-string SQL
- structlog everywhere, never print()
- Every new function: docstring + type hints
- Every new module: corresponding test file
```

---

## The security non-negotiables checklist

Run this review at the end of sessions 3, 6, 9, 15.

```
Security review — check each item:

AUTH & TOKENS
□ JWT uses RS256, not HS256
□ Access token TTL is 15 minutes
□ Refresh token stored in DB, not in JWT payload
□ Refresh token rotation on every use
□ Double-spend detection (reuse → revoke all sessions)
□ No token in any log line

PASSWORDS & SECRETS  
□ Passwords hashed with argon2, not bcrypt or md5
□ No plaintext password anywhere in the codebase (grep for password=)
□ Camera credentials Fernet-encrypted before DB write
□ No decrypted credential in any API response
□ No secret in any error message

API SECURITY
□ All routes require auth except /health and /auth/login
□ All list endpoints paginated (no unbounded queries)
□ Rate limiting on /auth/login (10 req / 10 min per IP)
□ CORS configured with specific origins, not *
□ All file downloads validated: belongs to requesting user + within allowed path

STORAGE PATHS
□ All file paths use pathlib.Path.resolve() before use
□ No path traversal possible (validate path starts with STORAGE_PATH)
□ Exports accessible only via signed URL, not direct filesystem path

AUDIT
□ Every sensitive action writes AuditLog
□ Audit log is append-only (no UPDATE/DELETE on the table)
□ AuditLog rows sanitised: no passwords, tokens, or secrets in detail JSONB
```

---

## File naming and organisation

```
models/      → singular snake_case.py        camera.py, recording_segment.py
schemas/     → same domain name              camera.py (CameraCreate, CameraResponse...)
routers/     → plural snake_case.py          cameras.py, recordings.py
services/    → domain + _service.py          camera_service.py, auth_service.py
workers/     → noun describing the work      recording.py, purge.py, export.py
utils/       → utility name                  ffmpeg.py, encryption.py
tests/unit/  → test_ + module name           test_auth_service.py
tests/int/   → test_ + feature              test_camera_flow.py
```

---

## Useful docker commands

```bash
# Start everything
docker compose up -d

# Watch all logs
docker compose logs -f

# Watch specific service
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f detection

# Run backend tests
docker compose exec backend pytest tests/ -v --cov=app --cov-report=term-missing

# Run only failing tests
docker compose exec backend pytest tests/ -v --lf

# Run specific test file
docker compose exec backend pytest tests/integration/test_auth.py -v

# Run specific test
docker compose exec backend pytest tests/integration/test_auth.py::test_login_lockout -v

# Apply migrations
docker compose exec backend alembic upgrade head

# Generate migration after model change
docker compose exec backend alembic revision --autogenerate -m "add detection zones"

# Check migration SQL before applying
docker compose exec backend alembic upgrade head --sql

# Rollback one migration
docker compose exec backend alembic downgrade -1

# Open Python REPL in backend container
docker compose exec backend python

# Check Celery worker status
docker compose exec worker celery -A app.celery_app inspect active
docker compose exec worker celery -A app.celery_app inspect stats

# Run a specific Celery task manually
docker compose exec worker celery -A app.celery_app call nvr.purge_old_segments

# Connect to PostgreSQL
docker compose exec postgres psql -U nvr nvr

# Connect to Redis
docker compose exec redis redis-cli

# Check detection service health
curl http://localhost:8001/health

# Generate new RSA keys + Fernet key
docker compose exec backend python scripts/generate_keys.py

# Run E2E tests (Playwright)
cd frontend && npx playwright test

# Check coverage
docker compose exec backend pytest tests/ --cov=app --cov-report=html
# Then open backend/htmlcov/index.html
```

---

## Dependency injection map

Understanding this prevents the most common "forgot to add Depends()" bugs.

```
get_db          → AsyncSession      → all service functions that touch DB
get_current_user → User             → all protected routes
require_permission("x:y") → None   → routes that need a specific permission
require_camera_permission(id,"x") → None → routes that check per-camera access
get_settings    → Settings          → any code that needs config (prefer injected)
get_redis       → Redis             → routes/services needing cache or pub/sub
get_hls_manager → HLSStreamManager  → live streaming routes
```

---

## Common failure modes and fixes

**"Camera returns RTSP URL with 0.0.0.0"**
→ Always run RTSP URL through fix_rtsp_url() in onvif_helpers.py.
   This is documented in SPEC.md section 12.

**"Celery task runs twice"**
→ Check idempotency guard at task start. Query DB state before doing work.
   RUNNING_PROCESSES dict is in-worker state — check before starting FFmpeg.

**"HLS stream has 6-10 second delay"**
→ This is expected. See SPEC.md section 8.1. Document for users.
   Do NOT try to reduce by decreasing hls_list_size below 5 (causes buffering stalls).

**"ONVIF connection fails with WSDLParseError"**
→ Initialize ONVIFCamera with Settings(strict=False). See SPEC.md section 12.

**"Test DB shares data between tests"**
→ Each test must run in a transaction that is rolled back. 
   conftest.py must use the transaction fixture pattern (not just a session fixture).

**"argon2 hash verification is slow"**
→ Intentional. Default settings take ~0.3-0.5s. Do NOT reduce memory_cost for speed.
   If tests are slow: use a lower-cost settings override in test conftest ONLY.

**"Detection service not receiving zone config changes"**
→ Backend must publish to Redis "nvr:config:reload:{camera_id}" after saving zones.
   Detection service config_watcher thread must be running (check health endpoint).
   Zone config stored in Redis key "nvr:zones:{camera_id}", not just in zones.json.

**"Export download fails for large files"**
→ Use StreamingResponse with iter_content(), not reading entire file into memory.
   Set Content-Length header from file size for progress bar support.
```

---

## Session progress tracker

Mark sessions as you complete them.

```
Phase 1 — Foundation
[ ] Session 1  — Infrastructure, scaffold, RSA key generation
[ ] Session 2  — All database models and initial migration
[ ] Session 3  — Security: auth service, JWT RS256, argon2, sessions
[ ] Session 4  — ONVIF integration service
[ ] Session 5  — Recording engine: Celery tasks, FFmpeg, storage

Phase 2 — Core features
[ ] Session 6  — User management, roles, audit log, GDPR
[ ] Session 7  — Live view: HLS streaming, WebSocket hub
[ ] Session 8  — Recordings timeline, clip retrieval, export
[ ] Session 9  — Alert system: rules, events, notifications

Phase 3 — Detection + Frontend
[ ] Session 10 — Detection microservice (complete)
[ ] Session 11 — React frontend: scaffold, auth, layout, dashboard
[ ] Session 12 — Frontend: live view and camera management
[ ] Session 13 — Frontend: recordings timeline, alerts, users
[ ] Session 14 — Storage page, settings, system health, notifications UI

Phase 4 — Production
[ ] Session 15 — Production hardening, observability, final integration
```
