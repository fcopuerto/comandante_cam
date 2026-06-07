# NVR Pro — Claude Code Session Prompts
# Each session is a focused, self-contained unit of work.
# Always: (1) open Claude Code in project root, (2) paste SPEC.md first, (3) paste session prompt.

---

## MANDATORY SESSION OPENER (paste this EVERY time before your session prompt)

```
Read SPEC.md completely before doing anything.
Confirm you have read it by answering:
1. What JWT algorithm do we use and why?
2. How are camera passwords stored?
3. What is the only way the detection service communicates with the backend?
4. What happens at 95% storage capacity?
5. Name three things explicitly listed as out of scope.
Do not write any code until you have answered these.
```

---

## SESSION 1 — Infrastructure, project scaffold, RSA key generation

```
Task: Build the complete project foundation. Nothing functional yet — just the skeleton
every other session will build on.

Steps in order:

1. Create the full directory structure from SPEC.md section 3. Create placeholder
   __init__.py and .gitkeep files where needed. Do not write implementation yet.

2. Write scripts/generate_keys.py:
   - Generates RSA-2048 key pair → saves to ./secrets/rsa_private.pem and rsa_public.pem
   - Generates a Fernet key → prints to stdout
   - Generates a 64-char hex SECRET_KEY → prints to stdout
   - README at top of file: "Run once at setup. Never commit the secrets/ directory."
   - Add secrets/ to .gitignore

3. Write docker-compose.yml per SPEC.md section 2 tech stack and section 14 env vars.
   Services: postgres, redis, backend (uvicorn), worker (celery), 
   celery-beat (redbeat), detection, frontend, nginx.
   All secrets via env_file: .env
   Named volumes for: postgres_data, redis_data, recordings_data, hls_data,
   exports_data, alerts_data, models_data, secrets_data.
   Healthchecks on postgres and redis.
   Network: all services on internal bridge "nvr_net". Only nginx exposes ports 80/443.

4. Write docker-compose.prod.yml with overrides for production:
   restart: always on all services. Resource limits. No exposed ports on backend 
   (nginx proxies). Read-only containers where possible.

5. Write .env.example with ALL variables from SPEC.md section 14. 
   Comments explaining each. No real values.

6. Write backend/requirements/base.txt with pinned versions:
   fastapi==0.111.0, uvicorn[standard]==0.29.0, sqlalchemy[asyncio]==2.0.30,
   asyncpg==0.29.0, alembic==1.13.1, pydantic-settings==2.2.1, pydantic[email]==2.7.1,
   python-jose[cryptography]==3.3.0, argon2-cffi==23.1.0, cryptography==42.0.5,
   celery[redis]==5.4.0, redbeat==2.2.0, redis==5.0.4, structlog==24.1.0,
   httpx==0.27.0, python-onvif-zeep==0.2.12, pyotp==2.9.0,
   slowapi==0.1.9, pyzipper==0.3.6

   Write dev.txt (adds): pytest==8.2.0, pytest-asyncio==0.23.6, 
   factory-boy==3.3.0, faker==25.0.0, freezegun==1.5.0

7. Write backend/app/core/logging.py — structlog configuration:
   - JSON output in production (APP_ENV=production), pretty-colored output in development
   - Processors: add_log_level, add_logger_name, TimeStamper(fmt="iso"),
     StackInfoRenderer, format_exc_info, JSONRenderer (prod) or ConsoleRenderer (dev)
   - configure_logging() function called from app startup

8. Write backend/app/config.py using pydantic-settings:
   - One Settings class with all env vars from SPEC.md section 14
   - Field validators: DATABASE_URL must start with postgresql, 
     STORAGE_WARNING_PCT < STORAGE_CRITICAL_PCT
   - get_settings() → lru_cache singleton
   - Settings loaded from .env file + environment

9. Write backend/app/database.py:
   - Async engine with pool_size=20, max_overflow=10, pool_pre_ping=True
   - AsyncSessionFactory
   - get_db() async generator dependency
   - Base declarative class with naming convention for constraints
     (ix_, uq_, ck_, fk_, pk_ prefixes — important for Alembic autogenerate)

10. Write backend/app/main.py:
    - FastAPI app factory create_app() function (not module-level app)
    - Lifespan context manager (startup: log start, run migrations check, 
      shutdown: log stop)
    - Middleware registration order (order matters in FastAPI/Starlette):
      1. TrustedHostMiddleware (ALLOWED_HOSTS)
      2. RequestIDMiddleware (adds X-Request-ID to request state + response header)
      3. SecurityHeadersMiddleware (HSTS, CSP, X-Frame, etc.)
      4. CORSMiddleware (origins from settings)
      5. AuditLogMiddleware
    - Router includes with prefix /api/v1
    - /health endpoint (no auth) returning {"status":"ok","version":APP_VERSION}
    - Exception handlers: RequestValidationError → 422 with field details,
      generic Exception → 500 with request_id (never expose stack trace)

11. Write backend/app/core/exceptions.py:
    Custom exception hierarchy:
    NVRException (base)
    ├── NotFoundError(resource_type, resource_id)
    ├── ForbiddenError(required_permission)
    ├── ValidationError(field, message)
    ├── ConflictError(message)
    ├── CameraConnectionError(ip, reason)
    ├── StorageError(message)
    └── AuthenticationError(reason)

12. Write alembic/env.py configured for async SQLAlchemy.
    Import all models via backend/app/models/__init__.py.

13. Write tests/conftest.py with:
    - pytest-asyncio mode=auto in pytest.ini
    - Async test DB fixture (separate test DB, created/dropped per session)
    - Async TestClient fixture using httpx.AsyncClient
    - settings_override fixture (overrides DATABASE_URL for test DB)

Run: docker compose build. Fix any build errors. Show final output.
```

---

## SESSION 2 — All database models and initial migration

```
Task: Write ALL SQLAlchemy models from SPEC.md section 5. Complete, no placeholders.

Rules:
- Use SQLAlchemy 2.0 mapped_column() style (not Column())
- All PKs: UUID, server_default=text("gen_random_uuid()")
- All created_at: server_default=text("now()"), NOT onupdate
- All updated_at: server_default=text("now()"), onupdate=func.now()
- All ENUM types: use SQLAlchemy Enum(str, ..., name="type_name") — define enum 
  type once in core/constants.py, import everywhere
- All INET columns: use String(45) with a check constraint (IPv4/IPv6 regex)
- All JSONB columns: use JSON type in SQLAlchemy (maps to JSONB in PostgreSQL)
- FK constraints: always explicit name= per naming convention
- Index definitions in __table_args__ per SPEC.md section 5

Write these files (one model per file):
  models/camera.py, models/camera_group.py, models/recording_segment.py,
  models/recording_schedule.py, models/user.py, models/role.py,
  models/camera_permission.py, models/session.py, models/api_key.py,
  models/alert_event.py, models/alert_rule.py, models/detection_zone.py,
  models/export_job.py, models/audit_log.py, models/system_event.py,
  models/notification_channel.py

Write models/__init__.py exporting all models (needed for Alembic autodiscover).

Write core/constants.py with all Enum definitions.

After all models are written:
  Run: alembic revision --autogenerate -m "initial schema"
  Review the generated migration. Fix any issues (missing enum creation,
  wrong column types, missing indexes). Edit the migration file directly.
  Run: alembic upgrade head
  Confirm all tables and indexes were created with:
    SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
    SELECT indexname FROM pg_indexes WHERE schemaname = 'public' ORDER BY tablename;

Write tests/unit/test_models.py:
  - Test that all models can be instantiated with required fields
  - Test that cascade deletes work (delete Camera → segments deleted)
  - Test that audit_log append-only constraint exists
```

---

## SESSION 3 — Security: auth service, JWT RS256, argon2, sessions

```
Task: Implement the complete authentication and security infrastructure.

This is security-critical code. After writing each component, review it against
the security requirements in SPEC.md section 4 before moving on.

1. Write utils/encryption.py:
   - FernetEncryption class: encrypt(plaintext: str) → bytes, decrypt(ciphertext: bytes) → str
   - Loads FERNET_KEY from settings. Raises on missing key (never silently fail).
   - Test: encrypt → decrypt round-trip. Test: wrong key raises InvalidToken.

2. Write services/auth_service.py:

   RSA key handling:
   - load_rsa_keys() → loads PEM from paths in settings. Validates both keys on startup.
   
   Password operations:
   - hash_password(plain: str) → str   (argon2, time_cost=2, memory_cost=65536)
   - verify_password(plain: str, hashed: str) → bool
   - validate_password_strength(password: str) → list[str]  (returns list of failures)
   - check_hibp(password: str) → bool  (k-anonymity prefix lookup, True = found in breach)
   
   Token operations:
   - create_access_token(user_id, email, role_name, permissions) → str
     JWT RS256, sub=user_id, exp=now+15min, includes: email, role, permissions[], jti (UUID)
   - create_refresh_token() → str   (secrets.token_urlsafe(32), stored in DB not JWT)
   - decode_access_token(token: str) → TokenPayload | None  (returns None on any error)
   
   Session operations:
   - async create_session(db, user_id, refresh_token, request) → Session
     Stores hashed refresh token. Detects device from User-Agent.
   - async validate_refresh_token(db, token: str) → Session | None
     Checks not revoked, not expired, updates last_used_at.
   - async rotate_refresh_token(db, session: Session) → str
     Revokes old token (reason="rotated"), creates new session row.
   - async detect_refresh_token_reuse(db, token: str) → bool
     If token is revoked and was used again: revoke ALL user sessions (reason="reuse_detected"),
     log security event, return True.
   
   Login:
   - async authenticate(db, email, password, mfa_code, ip) → User
     Check active, check not locked, verify password (argon2), increment fail count,
     check MFA if enabled, reset fail count on success, update last_login.
     Raises AuthenticationError with safe message (never distinguish email vs password).
   
   Lockout:
   - async check_lockout(redis, identifier: str) → LockoutState
   - async record_failed_attempt(redis, identifier: str) → None
   - async clear_lockout(redis, identifier: str) → None

3. Write middleware/auth.py:
   - get_current_user dependency: 
     Reads Authorization header OR X-API-Key header.
     For Bearer: decode JWT, load user from DB, check is_active.
     For API key: hash key, lookup in api_keys, check is_active + not expired + IP whitelist.
     Attaches user to request.state.user.
   - require_permission(permission: str) dependency factory:
     Checks permission in user.role.permissions. Raises ForbiddenError if missing.
     Logs failed attempt to audit log.
   - require_camera_permission(camera_id_param: str, permission: str) dep factory:
     Checks CameraPermission row for this user+camera. Falls back to role permission.
     Camera-level deny overrides role permission.

4. Write middleware/rate_limit.py using slowapi:
   - Different limits per route group (per SPEC.md section 4.4)
   - Identify by: IP for login, user_id for authenticated routes
   - On limit exceeded: log to audit_log as "rate_limit_exceeded"

5. Write middleware/security_headers.py:
   Adds all headers from SPEC.md section 4.4. CSP nonce generation per request.

6. Write middleware/request_id.py:
   Reads X-Request-ID header if present, generates UUID4 if not.
   Attaches to request.state.request_id. Adds to response header.
   Adds to structlog context for all log lines in this request.

7. Write routers/auth.py with all routes from SPEC.md section 6 auth block.
   Refresh token: set as HttpOnly cookie (not just JSON body — support both).
   MFA setup: generate TOTP secret, return otpauth:// URI + QR data URL.
   Backup codes: generate 10 random codes, hash them, store in user.mfa_backup_codes.

8. Write schemas/auth.py: LoginRequest, TokenResponse, MFASetupResponse,
   ChangePasswordRequest, SessionResponse, UserMeResponse.

9. Write tests/integration/test_auth.py:
   - Login with correct credentials → 200 with tokens
   - Login with wrong password → 401, generic message, fail count incremented
   - 5 failed logins → account locked → 429
   - Login after lockout expires → succeeds
   - JWT in request → user loaded correctly
   - Expired JWT → 401
   - Refresh token rotation → new token valid, old invalid
   - Refresh token reuse → all sessions revoked
   - MFA: login without code when MFA enabled → 401
   - MFA: login with correct TOTP → 200
   - Rate limit: 11 login requests in 10 min → 429

Run all tests. Show output. Security review: confirm no passwords or tokens appear in any log output.
```

---

## SESSION 4 — ONVIF integration service

```
Task: Implement the complete ONVIF camera integration service.

ONVIF is complex and camera implementations are inconsistent.
Write defensively: catch all exceptions, log specifically, never crash on bad camera data.

1. Write utils/onvif_helpers.py:
   - fix_rtsp_url(url: str, camera_ip: str) → str
     Replace 0.0.0.0 or localhost in RTSP URLs with the actual camera IP.
   - parse_datetime_from_onvif(dt_struct) → datetime
     Handle the zeep datetime struct conversion.
   - safe_get(obj, *attrs, default=None)
     Safely navigate nested ONVIF response objects.

2. Write services/onvif_service.py:

   async discover_cameras(subnet: str, timeout: float = 5.0) → list[DiscoveredCamera]
     WS-Discovery scan. Parse XAddrs from responses.
     Filter duplicates by IP. Return DiscoveredCamera(ip, port, xaddrs).
     Catch: socket.timeout, WSDiscoveryException, all others → log + continue.

   async probe_camera(ip: str, port: int, username: str, password: str) → CameraProbeResult
     Connect with python-onvif-zeep (Settings strict=False).
     Pull: GetDeviceInformation → manufacturer, model, firmware, serial, mac.
     Pull: GetCapabilities → what services exist.
     Pull: GetProfiles → list profiles with tokens.
     Pull: GetStreamUri for main profile (token[0]) and sub profile (token[1] if exists).
     Fix RTSP URLs with fix_rtsp_url().
     Pull: GetVideoEncoderConfigurations → resolution, fps, bitrate, codec.
     Test RTSP reachability: try cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG), 
       read one frame, release. Set rtsp_reachable bool.
     Return CameraProbeResult with all gathered data.
     Raises CameraConnectionError on auth failure, timeout, WSDL error.

   async sync_time(camera: Camera) → bool
     Connect to camera ONVIF. GetSystemDateAndTime to check current time.
     Log drift (current_camera_time - utcnow()).
     SetSystemDateAndTime with UTCDateTime = current UTC.
     Return True on success, False with logged reason on failure.

   async get_snapshot(camera: Camera) → bytes
     Get snapshot URI from ONVIF. Fetch JPEG via httpx (digest auth).
     Return raw JPEG bytes.

   async get_ptz_presets(camera: Camera) → list[PTZPreset]
   async goto_preset(camera: Camera, preset_token: str) → bool
   async save_preset(camera: Camera, preset_name: str) → str  (returns token)
   async continuous_move(camera: Camera, pan: float, tilt: float, zoom: float) → bool
   async stop_ptz(camera: Camera) → bool

   async subscribe_to_events(camera: Camera, callback) → None  (future: motion events)

3. Write services/camera_service.py:
   async register_camera(db, data: CameraCreate, created_by: UUID) → Camera
     Probe camera first. If unreachable: raise CameraConnectionError.
     Encrypt password. Fill all fields from probe result. Save to DB.
     Write audit log entry: camera_added.
   
   async update_camera(db, camera_id, data: CameraUpdate, user: User) → Camera
     If IP/credentials changed: re-probe before saving.
     Re-encrypt password if changed.
     Write audit log: camera_configured, include before/after diff.
   
   async delete_camera(db, camera_id, user: User) → None
     Soft delete: set is_deleted=True, deleted_at=now(). 
     Stop any running recording task.
     Write audit log: camera_removed.
   
   async get_cameras(db, user: User, filters: CameraFilters) → Page[Camera]
     Filter by user's camera permissions. Apply group, status, tags filters.
   
   async get_camera_stats(db, camera_id, days: int = 30) → CameraStats
     Recording hours, storage used, alert count, uptime percentage.

4. Write routers/cameras.py with all camera routes from SPEC.md section 6.
   POST /cameras/discover → runs discover_cameras, returns candidates (not saved yet).
   POST /cameras → calls register_camera (does probe + save).
   POST /cameras/{id}/test-connection → calls probe_camera, returns result without saving.
   GET /cameras/{id}/snapshot → calls get_snapshot, returns JPEG with content-type image/jpeg.

5. Write tests/unit/test_onvif_service.py:
   Mock ONVIFCamera object entirely (no real camera needed).
   Test fix_rtsp_url replaces 0.0.0.0 with camera IP.
   Test probe_camera with mock returns correct CameraProbeResult.
   Test probe_camera with auth failure raises CameraConnectionError.
   Test sync_time sends correct ONVIF call with UTC time (use freezegun).
   Test discover_cameras parses mock WS-Discovery response.
```

---

## SESSION 5 — Recording engine: Celery tasks, FFmpeg, storage

```
Task: Implement the full recording engine.

This is the most critical reliability component. Every edge case must be handled.

1. Write utils/ffmpeg.py:
   class FFmpegProcess:
     __init__(self, camera_id: str, command: list[str])
     start() → subprocess.Popen
     is_running() → bool
     stop(timeout: float = 5.0) → None  (SIGTERM then SIGKILL)
     read_stderr_line() → str | None  (non-blocking)
     parse_stderr(line: str) → FFmpegEvent | None
       Detects: StreamError, Reconnecting, SegmentCreated, ConnectionRefused
   
   build_continuous_command(rtsp_url, output_dir, camera_id) → list[str]
   build_hls_command(rtsp_url, hls_dir, camera_id) → list[str]
   build_export_command(input_files, output_path, watermark_text, crf) → list[str]

2. Write workers/recording.py:

   RUNNING_PROCESSES: dict[str, FFmpegProcess] = {}  # module-level, in-worker state

   @celery_app.task(bind=True, max_retries=20)
   def start_recording(self, camera_id: str) → None:
     - Idempotency: check RUNNING_PROCESSES — if already running, return.
     - Load camera from DB (sync SQLAlchemy for Celery).
     - If recording_mode == off: return.
     - Ensure output directory exists (mkdir -p).
     - Build FFmpeg command (continuous mode).
     - Create FFmpegProcess, start it.
     - Register in RUNNING_PROCESSES[camera_id].
     - Monitor loop (while process.is_running()):
         Read stderr, parse events.
         Every 10 minutes: check that output file was recently written to.
         If segment file detected: close previous RecordingSegment row,
           compute SHA256, generate thumbnail (ffmpeg -ss 1 -vframes 1),
           open new RecordingSegment row.
         If stream error detected: log, increment camera.consecutive_errors.
         If 10 consecutive errors: update camera.status=error, 
           write SystemEvent, send notification, stop task.
     - On process exit: update camera.status, revoke task from RUNNING_PROCESSES.
     - On retry: exponential backoff (30s * retry_number, max 10 minutes).

   @celery_app.task
   def stop_recording(camera_id: str) → None:
     If camera_id in RUNNING_PROCESSES: stop process, remove from dict.
     Update camera.status = offline (if it was recording).

   @celery_app.task
   def start_all_recordings() → None:
     Called on worker startup.
     Query all cameras where recording_mode != 'off' AND is_deleted = FALSE.
     For each: start_recording.delay(camera_id).

   @celery_app.task(name="nvr.purge_old_segments")  ← Celery Beat schedule
   def purge_old_segments() → None:
     Query segments where ended_at < now() - retention_days days 
       AND is_on_legal_hold = FALSE.
     For each in batches of 100:
       Delete file (log warning if file not found, don't fail).
       Delete thumbnail file.
       Delete DB row.
     Query exports where expires_at < now().
     For each: delete file, delete DB row.
     Check storage usage. Write SystemEvent with stats.
     If usage > STORAGE_CRITICAL_PCT: emergency_purge().

   def emergency_purge() → None:
     Delete oldest segments (ignoring retention, but NOT legal holds) until below 85%.

3. Write workers/health_check.py:
   @celery_app.task(name="nvr.camera_health_check")  ← every 60 seconds
   def camera_health_check() → None:
     For each non-deleted camera:
       If camera in RUNNING_PROCESSES: verify process is alive. If not: restart.
       Else if recording_mode != off: start_recording.delay(camera_id).
       Try ONVIF ping (GetSystemDateAndTime — lightweight).
       Update camera.status, camera.last_seen.

4. Write services/recording_service.py:
   async get_timeline(db, camera_id, date) → TimelineDay
     Returns segments for that date, grouped for UI rendering.
     Includes coverage map: which hours have recordings, gaps.
   
   async get_calendar(db, camera_id, year, month) → CalendarMonth
     Per day: has_recordings bool, has_alerts bool, recording_hours float.
   
   async get_segments(db, filters: SegmentFilters) → Page[RecordingSegment]

5. Write workers/export.py:
   @celery_app.task(bind=True)
   def export_clip(self, job_id: str) → None:
     Load ExportJob. Update status=processing, progress=0.
     Collect all segment files spanning from_dt to to_dt for all camera_ids.
     Build FFmpeg concat input file.
     Build watermark text: "Exported: {datetime} | Camera: {name} | User: {email}"
     Run FFmpeg export command. Monitor progress via stderr duration parsing.
     Update progress_pct every 5 seconds.
     On complete: compute SHA256, update ExportJob status=completed, file_path, checksum.
     If password_protected: wrap in AES-256 zip with pyzipper.
     Publish WebSocket event: export_progress.

6. Write tests/unit/test_recording.py:
   Mock subprocess.Popen. Test that start_recording creates segment rows.
   Test that stop_recording terminates FFmpeg.
   Test purge_old_segments with mock filesystem (tmp_path fixture).
   Test emergency_purge triggers at correct threshold.
   Test export_clip produces correct FFmpeg command with watermark.
```

---

## SESSION 6 — User management, roles, audit log, GDPR

```
Task: Complete user management system including GDPR erasure and the full audit log.

1. Write services/user_service.py:
   async create_user(db, data: UserCreate, created_by: User) → User
     Validate password strength. Check HIBP. Hash with argon2. 
     Assign role. Set must_change_password=True.
     Send invite email (or generate invite link).
     Write audit: user_created.
   
   async update_user(db, user_id, data: UserUpdate, acting_user: User) → User
     If role changed: write audit user role_changed with old and new role.
     If email changed: require re-verification (future feature, stub for now).
   
   async deactivate_user(db, user_id, acting_user: User) → None
     Set is_active=False. Revoke ALL sessions. Write audit: user_deactivated.
   
   async anonymise_user(db, user_id, acting_user: User) → None  (GDPR erasure)
     Replace email with sha256(email)@deleted.local.
     Replace full_name with "Deleted User".
     Set hashed_password to invalid hash (cannot login).
     Clear mfa_secret, mfa_backup_codes.
     Clear last_login_ip.
     Set anonymised_at = now().
     Revoke all sessions.
     KEEP: audit log entries (referenced by user_id, email was snapshotted at log time).
     Write audit: user_anonymised.
   
   async unlock_user(db, user_id, acting_user: User) → None
     Clear failed_login_count, locked_until. Write audit: user_unlocked.
   
   async set_camera_permissions(db, user_id, permissions: list[CameraPermissionSet]) → None
     Bulk upsert CameraPermission rows. Write audit: permission_granted / permission_revoked.

2. Write services/audit_service.py:
   async log(db, action: str, user: User | None, resource_type: str | None,
             resource_id: str | None, detail: dict | None, request: Request | None) → None
   
   This must be non-blocking — use fire-and-forget (asyncio.create_task) 
   so audit logging never delays the response.
   
   Sanitise detail: recursively remove any key containing "password", "token", 
   "secret", "key", "credential" before writing.

3. Write middleware/audit.py:
   Intercepts all mutating requests (POST, PUT, PATCH, DELETE).
   After response: logs action derived from method + path.
   Include request_id for correlation.

4. Write routers/users.py with all user routes from SPEC.md.
   DELETE /users/{id} → calls anonymise_user (not hard delete).
   Requires: manager or admin cannot modify another admin. superadmin only.

5. Write routers/roles.py:
   All CRUD for roles. Cannot modify or delete is_system_role=True roles.
   GET /roles/permissions → returns hardcoded list of all valid permission strings
   with descriptions (for the UI permission picker).

6. Write routers/audit.py (admin-only):
   GET /system/audit-log with filters. Paginated. Export to CSV (streaming response).

7. Write tests/integration/test_users.py:
   - Create user, login, must_change_password enforced.
   - Deactivate user → sessions revoked → subsequent API calls 401.
   - Anonymise user → cannot login, audit log preserved, name replaced.
   - Permission matrix: viewer cannot call cameras:configure route.
   - Role assignment: manager cannot assign superadmin role.
```

---

## SESSION 7 — Live view: HLS streaming, WebSocket hub, real-time status

```
Task: Implement live video streaming and the WebSocket real-time update system.

1. Write services/hls_service.py:
   class HLSStreamManager:
     Singleton managing all active HLS FFmpeg processes.
     _streams: dict[str, FFmpegProcess]
     _locks: dict[str, asyncio.Lock]   # per-camera lock to prevent double-start
     
     async start_stream(camera: Camera) → str  (returns HLS URL path)
       Acquire camera lock. If already running: return URL (idempotent).
       Ensure HLS directory exists. Start FFmpeg HLS process.
       Return /hls/{camera_id}/index.m3u8
     
     async stop_stream(camera_id: str) → None
       Stop FFmpeg process. Delete HLS segment files.
     
     async stop_all() → None   (called on shutdown)
     
     async get_status() → dict[str, str]  (camera_id → "running"|"stopped")
     
     background task: every 60 seconds, check all HLS processes still alive.
       If dead and camera still has viewers: restart.
       Track viewer count per stream via WebSocket connection tracking.
       Auto-stop HLS stream when viewer count drops to 0.

2. Write routers/live.py:
   GET /live/{camera_id}/stream-url
     Check permission cameras:view_live.
     Start HLS stream (idempotent).
     Return {"hls_url": "https://{host}/hls/{camera_id}/index.m3u8",
             "sub_hls_url": "...", "camera": CameraResponse}.
   
   DELETE /live/{camera_id}/stream  (admin only — force stop)
   GET /live/active  → list cameras with active HLS streams + viewer counts
   GET /live/{camera_id}/snapshot → calls onvif_service.get_snapshot, returns JPEG

3. Write routers/ws.py — WebSocket hub:
   
   Connection manager:
   class ConnectionManager:
     connections: dict[str, list[WebSocket]]  # user_id → websockets
     
     async connect(ws: WebSocket, user: User) → None
       Check user has ≤5 active WebSocket connections. Reject if exceeded.
       Authenticate: extract token from query param ?token=... (no header in WS).
       Accept connection. Add to connections dict.
       Send initial state: camera statuses, unacknowledged alert count.
     
     async disconnect(ws: WebSocket, user_id: str) → None
     
     async broadcast(message: dict) → None  (send to all connected users)
     async send_to_user(user_id: str, message: dict) → None
     async send_to_permission(permission: str, message: dict) → None
       Only send to users who have the given permission (e.g., alerts:view).
   
   WS /ws endpoint:
     Authenticate, connect.
     Subscribe to Redis channels: nvr:ws:broadcast, nvr:ws:user:{user_id}.
     Forward Redis messages to WebSocket.
     Heartbeat: send {"type":"ping"} every 30s. Close if no pong in 10s.
     On disconnect: decrement HLS viewer counts for cameras this user was viewing.
   
   Redis subscriber task (runs in Celery worker):
   async def redis_to_ws_forwarder():
     Subscribe to nvr:ws:broadcast and all nvr:ws:user:* channels.
     Forward to ConnectionManager. Runs in the backend process on startup.

4. Nginx configuration (nginx/nginx.conf):
   - HTTPS termination with TLS 1.3 minimum.
   - Proxy /api/ and /ws to backend upstream.
   - Serve /hls/ as static files from hls_data volume (NOT proxied to backend).
   - Serve / from frontend container.
   - WebSocket upgrade headers for /ws.
   - Gzip for API responses. No gzip for video (.ts, .mp4 — already compressed).
   - Client max body size: 10MB (for snapshot uploads etc.)
   - Buffer settings optimised for video streaming.

5. Write tests/integration/test_live.py:
   Mock FFmpegProcess. Test stream-url starts HLS, returns URL.
   Test second call returns same URL (idempotent).
   Test WebSocket connection authentication (valid token → connected, invalid → 4001).
   Test WebSocket message received when camera status changes.
   Test viewer count tracking and auto-stop on 0 viewers.
```

---

## SESSION 8 — Recordings timeline, clip retrieval, export

```
Task: Build the full recording retrieval and export system.

1. Write services/recording_service.py (complete):
   
   async get_timeline(db, camera_id, date: date, tz: str) → TimelineResponse
     Query segments for that date (convert to UTC range for query).
     Return: list of TimelineSegment (start, end, type, has_alert, segment_id).
     Include gap detection: periods with no segments in the 24h window.
     Include coverage_pct: percentage of the day that has recordings.
   
   async get_calendar(db, camera_id, year: int, month: int) → CalendarResponse
     One entry per day: has_recordings, has_alerts, recording_hours, storage_mb.
     Used by the calendar day-picker in UI.
   
   async find_segment_at(db, camera_id, timestamp: datetime) → RecordingSegment | None
     Find which segment contains the given timestamp.
   
   async find_segments_in_range(db, camera_ids, from_dt, to_dt) → list[RecordingSegment]
     For export: find all segments spanning the requested range.
     Include partial segments (trim timestamps stored in ExportJob).

2. Write services/export_service.py:
   
   async create_export_job(db, data: ExportCreate, user: User) → ExportJob
     Validate: from_dt < to_dt. Max range: 4 hours.
     Validate: all camera_ids accessible by user.
     Find segments. If no segments found: raise ValidationError.
     Estimate output size (sum segment sizes * trim ratio). Warn if > 4GB.
     Create ExportJob row. Queue export_clip Celery task.
     Return job with estimated_size_bytes.
   
   async get_export_status(db, job_id, user: User) → ExportJob
     Check job belongs to user (or user is admin).
     If completed: generate signed download URL (time-limited, 1 hour).
   
   async stream_export_file(db, job_id, user: User) → StreamingResponse
     Verify job completed and belongs to user.
     Stream file with correct Content-Disposition, Content-Length headers.
     Log download to audit log: clip_exported, include checksum.

3. Write routers/recordings.py and routers/export.py (all routes from SPEC.md).

4. Write tests/integration/test_recordings.py:
   Seed segments in DB. Test timeline returns correct structure.
   Test calendar returns correct coverage.
   Test export job creation → status polling → download works end-to-end.
   Test export size limit (reject if > 4 hours).
   Test that user cannot download another user's export.
   Test watermark is applied (check FFmpeg command includes drawtext).
```

---

## SESSION 9 — Alert system: rules, events, notifications

```
Task: Build the complete alert management system and notification pipeline.

1. Write services/alert_service.py:
   
   async create_alert_from_detection(db, event: DetectionEvent) → AlertEvent
     Called by alert_consumer worker when Redis message arrives.
     Find matching AlertRule for camera + detection_type.
     Determine severity from rule (or event itself if no rule match).
     Save frame (already base64 in event or path to pre-saved frame).
     Queue save_alert_clip Celery task.
     Queue send_alert_notifications Celery task.
     Publish to WebSocket: {"type": "alert", ...}
   
   async acknowledge_alert(db, alert_id, user: User, notes: str) → AlertEvent
     Set acknowledged=True, acknowledged_by, acknowledged_at, notes.
     Write audit: alert_acknowledged.
   
   async mark_false_positive(db, alert_id, user: User, notes: str) → AlertEvent
     Set is_false_positive=True. Write audit: alert_false_positive.
     This feedback should be logged (future: feed back to model tuning).
   
   async set_legal_hold(db, alert_id, hold: bool, user: User) → AlertEvent
     Set is_on_legal_hold. Write audit. 
     Legal hold prevents: clip deletion, segment purge.
   
   async get_alert_stats(db, hours: int, user: User) → AlertStats
     Counts by severity, by camera, by rule, by hour bucket.
     Only cameras user has access to.

2. Write workers/alert_consumer.py:
   @celery_app.task(name="nvr.consume_alerts")
   def consume_alerts() → None:
     Subscribe to Redis "nvr:alerts" channel (blocking loop).
     Parse DetectionEvent from JSON.
     Validate schema. Drop malformed events (log warning).
     Call alert_service.create_alert_from_detection (via sync DB session).
     Acknowledgement: publish receipt back to detection service (future).

   @celery_app.task
   def save_alert_clip(alert_id: str) → None:
     Load alert from DB. Find recording segment at triggered_at for camera.
     If no segment: log warning (recording may be off), return.
     Clip ±30 seconds around triggered_at using FFmpeg.
     Save to ALERT_CLIPS_PATH/{alert_id}/clip.mp4.
     Compute checksum. Update alert: clip_path, clip_checksum.

3. Write services/notification_service.py:
   
   async send_alert_notifications(alert: AlertEvent, camera: Camera) → None
     Load AlertRule notification_channels for this alert.
     For each channel: dispatch to appropriate sender.
     All sending is async + retry (3 attempts, exponential backoff).
     Log send result to SystemEvent.
   
   Senders (each in own function):
   send_email(channel_config, alert, camera) → None
     Render plain text + HTML email body.
     Attach thumbnail JPEG if available.
     Use smtplib with STARTTLS.
   
   send_webhook(channel_config, alert, camera) → None
     POST JSON payload to webhook URL.
     Sign payload with HMAC-SHA256 (X-NVR-Signature header).
     Respect custom headers from channel config.
   
   send_telegram(channel_config, alert, camera) → None
     sendMessage API. sendPhoto if thumbnail available.
   
   send_slack(channel_config, alert, camera) → None
     Blocks API with attachment for thumbnail.
   
   send_pushover(channel_config, alert, camera) → None
     Map severity to Pushover priority (-1/0/1/2).

4. Write routers/alerts.py and routers/notifications.py (all routes from SPEC.md).

5. Write tests/integration/test_alerts.py:
   Test consume_alerts creates AlertEvent row from Redis message.
   Test save_alert_clip finds correct segment and clips correctly.
   Test acknowledge_alert sets fields and writes audit.
   Test legal hold prevents segment from appearing in purge candidates.
   Test notification send (mock smtplib, httpx).
   Test alert stats returns correct counts per severity.
```

---

## SESSION 10 — Detection microservice (complete)

```
Task: Build the production-quality detection microservice in detection_service/.
This service must be robust enough to run 24×7 unattended.

Follow SPEC.md sections 9.1 through 9.6 exactly.

1. Write detection_service/health_server.py:
   Minimal HTTP server (http.server) on port 8001.
   GET /health → {"status":"ok","cameras":N,"running":N,"redis":"ok"}
   Used by Docker healthcheck.

2. Write detection_service/config_watcher.py:
   Thread that subscribes to Redis "nvr:config:reload:*".
   On message for camera_id: fetch updated zone config from Redis key 
   "nvr:zones:{camera_id}" (backend writes this when zones are updated).
   Update the shared zones dict (thread-safe with RLock).
   Log reload event.

3. Write detection_service/frame_buffer.py:
   class FrameBuffer:
     Ring buffer of (timestamp, frame_bytes) tuples.
     Max size: 30 seconds * sample_fps frames.
     Thread-safe with deque(maxlen=N).
     get_frames_since(dt: datetime) → list[FrameRecord]
     Serialize to JPEG on access (lazy, not stored as JPEG).

4. Write detection_service/tracker.py:
   Wraps supervision ByteTrack tracker.
   update(detections: sv.Detections) → sv.Detections  (with track_ids)
   get_dwell_time(track_id: int, zone: str) → float  (seconds in zone)
   First-seen tracking: record first time each track_id entered each zone.
   Expire tracks after 5 seconds of no detection.

5. Write detection_service/zone_filter.py:
   class ZoneFilter:
     zones: list[Zone]  (loaded from config)
     filter(detections, frame_shape) → list[ZoneDetection]
       Normalise bbox to 0.0-1.0 coordinates.
       Compute centroid. Check point-in-polygon (Shapely) for each zone.
       Apply privacy mask: zero out bbox if centroid inside any privacy mask polygon.
       Return detections with matched zone name.

6. Write detection_service/rules_engine.py per SPEC.md section 9.5.
   All 5 rules implemented.
   Alert cooldown per (camera_id, rule, zone, track_id).
   Return AlertPayload or None.

7. Write detection_service/detector.py — DetectionWorker:
   Load YOLOv8n model ONCE at module level (shared across workers via thread-safe 
   inference — YOLOv8 model.predict() is thread-safe with individual calls).
   Full lifecycle per SPEC.md section 9.2.
   On alert: save frame to ALERT_CLIPS_PATH (mount the same volume as backend).
   Include pre-event frames from FrameBuffer as context (log frame count saved).

8. Write detection_service/redis_publisher.py:
   Publish AlertPayload to Redis "nvr:alerts" as JSON.
   Include base64-encoded thumbnail frame in payload (if frame available).
   If Redis unavailable: buffer up to 100 events in memory, retry on reconnect.

9. Write detection_service/main.py:
   Full lifecycle per SPEC.md section 9.1.
   Signal handling: SIGTERM → set stop_event, join all threads (max 10s), exit 0.

10. Write detection_service/Dockerfile:
    python:3.11-slim. 
    Install: ultralytics, opencv-python-headless, redis, shapely, supervision.
    Download yolov8n.pt during build (cache in Docker layer):
      RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
    Copy model to /models/yolov8n.pt.
    HEALTHCHECK CMD curl -f http://localhost:8001/health || exit 1

11. Write detection_service/tests/test_zone_filter.py (comprehensive):
    Test centroid inside polygon → included.
    Test centroid outside → excluded.
    Test privacy mask zeroes bbox.
    Test with normalized vs pixel coordinates.
    
    Write detection_service/tests/test_rules_engine.py:
    All 5 rules tested with time mocking (freezegun).
    Test cooldown suppresses repeated same-rule+zone+track alerts.
    Test different track_id same zone → not suppressed.
    
    Write detection_service/tests/test_tracker.py:
    Test dwell time increments correctly.
    Test track expiry after 5 seconds.

Run all tests. Build Docker image. Verify health endpoint responds.
```

---

## SESSION 11 — React frontend: scaffold, auth, layout, dashboard

```
Task: Build the React frontend foundation and the first three screens.

1. Initialise Vite + React + TypeScript + Tailwind + shadcn/ui in frontend/.
   Install all packages from SPEC.md tech stack (frontend section).
   Configure Tailwind. Run shadcn/ui init.
   Install shadcn components: button, card, badge, dialog, dropdown-menu,
   input, label, select, separator, sheet, skeleton, table, tabs, toast,
   tooltip, switch, slider, progress, avatar, alert, calendar.

2. Write frontend/src/lib/api.ts:
   Axios instance. Interceptors:
   Request: add Authorization header from auth store.
   Response 401: attempt token refresh. If refresh fails: redirect to /login.
   Response: extract X-Request-ID, add to error objects for support.

3. Write frontend/src/store/authStore.ts (Zustand + persist):
   State: user, accessToken, isAuthenticated, isLoading.
   Actions: login, logout, refreshToken, updateUser.
   Refresh token stored in HttpOnly cookie (not Zustand — cookie is automatic).
   Persist: accessToken in sessionStorage (not localStorage for security).

4. Write frontend/src/store/wsStore.ts:
   Manages WebSocket connection.
   Actions: connect(token), disconnect, subscribe(type, callback), unsubscribe.
   Auto-reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s).
   Heartbeat: receive ping, send pong.

5. Write frontend/src/pages/Login.tsx:
   Per SPEC.md section 10.1. 
   Conditional MFA field. Generic error messages. Lockout countdown timer.
   Accessible: proper label associations, keyboard navigation, focus management.

6. Write frontend/src/components/shared/Layout.tsx:
   Sidebar navigation (collapsible to icons).
   Nav items: Dashboard, Live View, Recordings, Alerts (with unread badge),
   Cameras, Users (role-gated), Settings.
   Top bar: facility name, current user avatar + dropdown (profile, sessions, logout).
   Alert banner: if system events exist (storage warning etc.), show banner.
   WebSocket connection indicator (green dot / amber reconnecting / red disconnected).

7. Write frontend/src/pages/Dashboard.tsx per SPEC.md section 10.2:
   All widgets. Use TanStack Query for data. Loading skeletons.
   Storage donut: recharts PieChart.
   Recording coverage heatmap: custom SVG grid (hours × cameras).
   Real-time alert feed: subscribes to wsStore, auto-scrolls.

8. Write frontend/src/api/ TanStack Query hooks:
   cameras.ts: useCameras, useCamera, useUpdateCamera, useCreateCamera,
               useDiscoverCameras, useTestConnection, useSyncTime, useSnapshot
   recordings.ts: useTimeline, useCalendar, useSegments
   alerts.ts: useAlerts, useAlertStats, useAcknowledgeAlert, useLegalHold
   users.ts: useUsers, useUser, useCreateUser, useUpdateUser
   system.ts: useSystemHealth, useStorageStatus, useSystemEvents
   live.ts: useStreamUrl, useActiveStreams

9. Write tests (Vitest):
   test_login.tsx: renders, submits, shows MFA field after credentials, handles lockout.
   test_layout.tsx: sidebar navigation, role-gating on Users link, WS indicator.
   test_dashboard.tsx: renders all widgets, handles loading state, handles error state.
```

---

## SESSION 12 — Frontend: live view and camera management

```
Task: Build Live View and Camera Management pages. Most complex frontend work.

1. Write frontend/src/components/live/CameraPlayer.tsx:
   Props: cameraId, label, location, hasAlert, onFullscreen, onSnapshot.
   HLS.js integration with proper cleanup on unmount.
   States: loading (spinner), buffering (spinner overlay), playing, offline (placeholder), error (red border + retry).
   Controls overlay (hover): fullscreen button, snapshot button, PTZ button (if enabled).
   Alert badge (top-right, red, count).
   Name/location overlay (bottom-left, semi-transparent).
   Auto-reconnect on error: 3 attempts with increasing delay.

2. Write frontend/src/components/live/CameraGrid.tsx:
   Props: layout (1|4|9|16), cells: CameraSlot[].
   CSS grid with enforced 16:9 aspect ratio per cell.
   Empty cell: dashed border + "Click to add camera" placeholder.
   Drag-and-drop (dnd-kit): drag camera from picker to grid cell. Swap cells by drag.

3. Write frontend/src/components/live/CameraPicker.tsx:
   Collapsible sidebar. Camera list with group tree.
   Search input. Filter by status (online only toggle).
   Each camera: status dot, name, location. Click to add to first empty cell.
   Cameras already in grid: shown with checkmark, click removes.

4. Write frontend/src/pages/LiveView.tsx per SPEC.md section 10.3:
   Layout toolbar: 1/4/9/16 buttons.
   "Save layout" → saves to user preferences via PATCH /auth/me.
   Preset layouts dropdown: "All loading dock", "Floor 1" etc. (from camera groups).
   Keyboard: Escape = exit fullscreen, Arrow keys navigate grid selection.
   WebSocket: subscribe to camera_status events, update player states in real-time.
   Subscribe to alert events: flash alert badge on relevant camera cell.

5. Write frontend/src/pages/Cameras.tsx per SPEC.md section 10.5:
   Data table (TanStack Table): sortable, filterable columns.
   Bulk actions toolbar (when rows selected): enable recording, disable recording, sync time.
   "Discover cameras" button → slide-over panel:
     Subnet input with validation. Scan button.
     Progress indicator during scan.
     Results table: IP, manufacturer, model, status, "Add" button per row.
   Quick add: opens CameraForm with pre-filled values from discovery.

6. Write frontend/src/components/cameras/CameraForm.tsx:
   Full form per SPEC.md section 10.5 Settings tab.
   "Test connection" button: calls POST /cameras/{id}/test-connection, shows 
   success (ONVIF ✓, RTSP ✓) or failure with specific error message.
   Unsaved changes guard: warn before leaving with changes.
   Validation: IP format, port range, FPS range, bitrate range.

7. Write frontend/src/pages/CameraDetail.tsx with all tabs per SPEC.md section 10.5:
   Tab: Overview, Settings, Schedule, Detection, PTZ, Permissions, Stats.
   Schedule tab: weekly grid component (7 columns, 24 rows, click-drag to add slots).
   Stats tab: recharts charts for recording hours trend, storage trend, alert frequency.

8. Write frontend/src/components/cameras/ZoneEditor.tsx:
   Background: camera snapshot image. Canvas overlay for polygon drawing.
   Click to add vertices. Double-click to close polygon.
   Drag vertices to adjust. Delete key removes selected vertex.
   Zone list below: name, restricted toggle, working hours, dwell threshold.
   Color picker per zone (for overlay display).
   Save → PUT /cameras/{id}/zones. Triggers config reload.

9. Write tests:
   test_camera_player.tsx: renders loading, transitions to playing, shows offline state.
   test_camera_grid.tsx: 2×2 layout renders 4 cells, drag-drop swaps cells.
   test_zone_editor.tsx: draw polygon adds vertices, save calls API.
```

---

## SESSION 13 — Frontend: recordings timeline, alerts, users

```
Task: Build Recordings, Alerts, and User Management pages.

1. Write frontend/src/components/recordings/Timeline.tsx:
   Horizontal 24-hour axis. Segments rendered as coloured bands.
   Zoom with scroll wheel (24h → 1h → 15min, snapping to natural boundaries).
   Click-drag selection: shows selected range duration.
   Hover tooltip: segment type, start time, duration, size.
   Alert markers: red triangles at alert timestamps within segments.
   Keyboard: Escape clears selection, Enter opens player for selection.

2. Write frontend/src/components/recordings/RecordingPlayer.tsx:
   Custom video.js player wrapper.
   Speed controls: 0.5×, 1×, 2×, 4×, 8×.
   Frame advance: ← → arrow keys at 1× speed.
   Alert timestamp markers on scrubber.
   "Add to export" button with time range from current selection.

3. Write frontend/src/components/recordings/MultiCameraPlayer.tsx:
   Side-by-side players (max 4). Shared scrubber.
   Single play/pause controls all. Seek syncs all players.
   Timeline overlay showing all cameras' segments for the selected date.

4. Write frontend/src/pages/Recordings.tsx per SPEC.md section 10.4:
   Calendar date picker. Camera selector tree.
   Timeline + player layout. Export panel.
   Export panel: selected ranges list, options (watermark, password), submit.
   Export progress: polling via useExportStatus, progress bar.
   Download: triggers /export/{id}/download. Shows SHA256 on completion.

5. Write frontend/src/pages/Alerts.tsx per SPEC.md section 10.6:
   Table with all columns. Filter bar.
   Alert detail slide-over:
     Frame with bbox overlay (draw rectangle on <img> with CSS overlay div).
     Metadata table. Player for alert clip. Acknowledge form. Legal hold.
   Bulk operations: multi-select checkboxes, bulk acknowledge, bulk false-positive.
   Alert stats chart: recharts AreaChart, severity stacked, time buckets.
   CSV export: calls /alerts with current filters + accept: text/csv.

6. Write frontend/src/pages/Users.tsx per SPEC.md section 10.7:
   User table. Invite user dialog.
   User detail slide-over: edit, role change, session list (revoke individual sessions), deactivate.
   Camera permissions matrix: TanStack Table with boolean cell editors.
   Role management page: list roles, permission picker for custom roles.

7. Write frontend/src/pages/AuditLog.tsx per SPEC.md section 10.8:
   Large filterable table (virtual scrolling for performance — use @tanstack/react-virtual).
   JSON diff for config_change entries (react-diff-viewer or custom).
   CSV export button.

8. Write tests:
   test_timeline.tsx: renders segments, zoom changes visible range, drag creates selection.
   test_alerts.tsx: table renders, filter updates query, acknowledge calls API, bulk select.
   test_users.tsx: invite form validates, permission matrix checkboxes work.
```

---

## SESSION 14 — Storage page, settings, system health, notifications UI

```
Task: Complete the remaining frontend pages and polish the system settings.

1. Write frontend/src/pages/Storage.tsx per SPEC.md section 10.9:
   Donut chart with total / used / free.
   Per-camera table: sortable by storage used. Inline retention edit.
   Purge preview: slider for retention days, live calculation of space freed.
   Pending exports: list with sizes, cancel button.
   Storage trend chart: recharts AreaChart, last 30 days, total + per top camera.

2. Write frontend/src/pages/Settings.tsx per SPEC.md section 10.10:
   Tabbed: General, Storage, Notifications, Security, Backup, API Keys, About.
   
   Notifications tab:
     Channel list: type icon, name, enabled toggle, test button, edit/delete.
     "Add channel" wizard: step 1 = select type, step 2 = type-specific config form.
     Test button: calls /notifications/channels/{id}/test, shows success/error.
   
   Security tab:
     Session timeout setting. Current password policy display.
     MFA enforcement: toggle (forces all users to enable MFA within 24h).
     Active session overview (count of sessions across all users).
   
   API Keys tab:
     List with prefix shown (never full key). Created date, last used, permissions.
     Create: shows full key ONCE in a copy-to-clipboard modal. Never shown again.
     Revoke: confirm dialog.
   
   About tab:
     App version, uptime (live via WebSocket), DB version, camera count, 
     total recordings count, total storage managed.

3. Write frontend/src/components/shared/SystemHealthBar.tsx:
   Always visible in layout top bar.
   Services: API, Database, Task workers, Detection service.
   Green dot = healthy. Amber = degraded. Red = down.
   Click → modal with detailed health info per service.
   Data from useSystemHealth (polls every 30s, plus WebSocket system_event updates).

4. Write frontend/src/components/shared/NotificationToast.tsx:
   Global toast system (shadcn/ui toast or react-hot-toast).
   WebSocket alert events → show toast with camera name, severity, dismiss button.
   Severity-coloured: critical=red, high=orange, medium=amber, low=blue.
   Max 3 toasts visible. Queue others. Auto-dismiss after 5s (critical: stays until dismissed).
   Click toast → navigate to alert detail.

5. Polish pass:
   - Loading skeletons on every data table and chart (use shadcn Skeleton).
   - Empty states on every table (descriptive message + action button).
   - Error boundaries on all page-level components.
   - 404 page.
   - Responsive: test at 768px (tablet) and 1280px (desktop). 
     Mobile (< 768px): alert user that a desktop browser is recommended (not fully mobile).
   - Keyboard navigation: all interactive elements reachable via Tab, activated via Enter/Space.
   - ARIA labels on icon-only buttons.
   - Page titles: update document.title on route change.

6. Write Playwright E2E tests (playwright.config.ts):
   e2e/auth.spec.ts: full login flow, MFA, logout.
   e2e/live-view.spec.ts: navigate to live view, add camera to grid, player loads.
   e2e/alerts.spec.ts: alert appears via WS mock, click to view detail, acknowledge.
   e2e/export.spec.ts: select time range, request export, download when complete.
```

---

## SESSION 15 — Production hardening, observability, final integration

```
Task: Everything needed to run this safely in production.

1. Write backend/app/core/events.py (lifespan handlers):
   On startup:
     - Validate all required env vars are set (FERNET_KEY, RSA keys, etc.)
     - Test DB connection. Fail fast if unreachable.
     - Test Redis connection. Fail fast if unreachable.
     - Check RSA key pair validity (encrypt/decrypt test).
     - Log startup with version, environment, storage path free space.
     - Seed default roles if not exist (idempotent).
     - Start HLS stream manager background cleanup task.
     - Start Redis→WS forwarder task.
   On shutdown:
     - Stop all HLS streams gracefully.
     - Close all WebSocket connections.
     - Log shutdown.

2. Implement Prometheus metrics endpoint (GET /system/metrics, internal only):
   Counters: alerts_total, recordings_started, exports_completed, login_attempts_total,
             login_failures_total, api_requests_total (by route + status code).
   Gauges: cameras_online, cameras_recording, hls_streams_active, 
           storage_used_bytes, storage_free_bytes, ws_connections_active.
   Histograms: api_request_duration_seconds, export_duration_seconds.
   Use prometheus-client library. Expose via /system/metrics (protected by internal IP check only).

3. Write scripts/seed_roles.py:
   Idempotent script to create default roles with permissions from SPEC.md section 4.3.
   Creates superadmin user if no users exist (one-time password → stdout only).

4. Write scripts/backup_db.sh:
   pg_dump → gzip → BACKUP_PATH.
   Keep last 7 daily backups. Remove older.
   Log to SystemEvent on completion.
   Intended to be run from Celery Beat daily.

5. Implement data retention for audit log separately from recordings:
   audit_log older than AUDIT_LOG_RETENTION_DAYS (default 365) → delete.
   IP address in audit_log older than IP_RETENTION_DAYS (default 90) → 
     anonymise (set to NULL) without deleting the row.

6. Security review checklist — verify each item in the code:
   ✓ No camera passwords in any log line (search for password in log calls)
   ✓ No tokens or secrets in any API response body (check auth schemas)
   ✓ All list endpoints paginated (search for routes without page param)
   ✓ All file paths validated to be within allowed directories (path traversal check)
   ✓ Export download validates job belongs to requesting user
   ✓ RTSP URLs never returned to frontend (frontend only gets HLS URL)
   ✓ CSRF: not needed (JWT in header, not cookie-only) — document this
   ✓ SQL injection: verify no string formatting in any DB query
   ✓ XSS: React handles this by default, but verify any dangerouslySetInnerHTML usage
   ✓ Rate limiting on all auth endpoints
   ✓ Storage path traversal: validate all file paths with pathlib.Path.resolve()
   For each ✗ found: fix it before proceeding.

7. Write the final integration test suite (tests/integration/test_e2e_flows.py):
   Full flow 1: Register camera → recording starts → motion alert fires → 
     operator acknowledges → clip exported → downloaded.
   Full flow 2: Create user with viewer role → can see live view → 
     cannot export → cannot configure camera.
   Full flow 3: Detection event via Redis → AlertEvent created → 
     WebSocket notification sent → notification email triggered.
   Full flow 4: Storage reaches 90% → SystemEvent created → 
     notification sent → purge triggers.

8. Write DEPLOYMENT.md:
   Prerequisites (Docker, Nginx, SSL certs).
   Step 1: Generate secrets (run scripts/generate_keys.py).
   Step 2: Configure .env.
   Step 3: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d.
   Step 4: Run migrations (docker compose exec backend alembic upgrade head).
   Step 5: Seed roles (docker compose exec backend python scripts/seed_roles.py).
   Step 6: First login (check logs for one-time password).
   Step 7: Add cameras, configure detection.
   Backup strategy. Update procedure. Rollback procedure.
   Monitoring: what to watch (Grafana dashboard JSON included).

Run the full test suite. Target: ≥80% coverage. Fix any failures.
Show final test output and coverage report.
```
