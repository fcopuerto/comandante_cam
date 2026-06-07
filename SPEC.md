# NVR Pro — Master Project Specification
# Version: 1.0  |  Classification: Internal
# Load this file at the start of EVERY Claude Code session.
# Do not deviate from any decision herein without creating a DECISION_LOG.md entry.

---

## 1. Project Vision

A self-hosted, enterprise-grade Network Video Recorder application that matches or
exceeds the feature depth of Synology Surveillance Station. The system is deployed
on-premise, records IP cameras 24×7, provides secure remote access over VPN, and
includes a real-time AI theft detection module.

Design philosophy:
- Security is not a feature — it is the foundation every other decision sits on
- Every action in the system is auditable and reversible where possible
- Degraded operation is always better than no operation (fail-safe defaults)
- The UI must be usable by non-technical security staff without training docs

---

## 2. Tech Stack — Fixed, No Deviations

| Layer                  | Choice                                      | Rationale                                      |
|------------------------|---------------------------------------------|------------------------------------------------|
| Backend language       | Python 3.12                                 | ONVIF/FFmpeg ecosystem, YOLOv8 native          |
| Web framework          | FastAPI 0.111 (async)                       | WebSocket + REST in one, excellent performance |
| Task queue             | Celery 5.4 + Redis broker                   | Mature, reliable for long-running tasks        |
| Task scheduler         | Celery Beat + RedBeat (Redis-backed)        | Cluster-safe scheduling                        |
| ORM                    | SQLAlchemy 2.0 async + Alembic              | Type-safe, async-native                        |
| Database               | PostgreSQL 16                               | JSONB, row-level locking, mature               |
| Cache                  | Redis 7.2                                   | Pub/sub, session store, task broker            |
| Video ingest           | FFmpeg 6 via subprocess (not ffmpeg-python) | Direct process control, signal handling        |
| ONVIF client           | python-onvif-zeep 0.2.12                    | Most complete Python ONVIF implementation      |
| Streaming              | FFmpeg → HLS segments served via Nginx      | Battle-tested, low latency HLS                 |
| Frontend               | React 18 + TypeScript 5 + Vite 5            | Type safety, fast builds                       |
| UI components          | shadcn/ui + Tailwind CSS 3                  | Accessible, unstyled primitives                |
| State — server         | TanStack Query v5                           | Caching, background refresh, optimistic UI     |
| State — client         | Zustand 4                                   | Minimal, no boilerplate                        |
| Video player           | HLS.js 1.5                                  | MSE-based, adaptive bitrate support            |
| Auth tokens            | python-jose (JWT RS256)                     | Asymmetric keys, more secure than HS256        |
| Password hashing       | argon2-cffi                                 | OWASP-recommended over bcrypt                  |
| Credential encryption  | cryptography (Fernet AES-128-CBC + HMAC)   | Camera passwords at rest                       |
| TLS termination        | Nginx (reverse proxy)                       | Handles HTTPS, HLS serving, WebSocket upgrade  |
| Secrets management     | HashiCorp Vault (optional) or .env + SOPS  | Never plaintext secrets in repo                |
| Containerisation       | Docker Compose (dev) / Docker Swarm (prod)  | Simple multi-host if needed                    |
| Testing — backend      | pytest + pytest-asyncio + factory-boy       | Async-native, fixtures                         |
| Testing — frontend     | Vitest + Testing Library + Playwright       | Unit + E2E                                     |
| API documentation      | OpenAPI (auto via FastAPI) + Scalar UI      | Replaces Swagger UI                            |
| Logging                | structlog (JSON structured logs)            | Machine-parseable, correlatable                |
| Metrics                | Prometheus + Grafana (optional sidecar)     | Disk, stream health, detection latency         |
| Detection              | Ultralytics YOLOv8 + OpenCV + Shapely       | Isolated microservice                          |

---

## 3. Repository Structure

```
nvr-pro/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI factory, lifespan, middleware registration
│   │   ├── config.py                # Pydantic-settings, all env vars, validation
│   │   ├── database.py              # Async engine, session factory, get_db dep
│   │   ├── celery_app.py            # Celery instance, task autodiscovery
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── camera.py
│   │   │   ├── camera_group.py
│   │   │   ├── recording_segment.py
│   │   │   ├── recording_schedule.py
│   │   │   ├── user.py
│   │   │   ├── role.py
│   │   │   ├── permission.py
│   │   │   ├── camera_permission.py
│   │   │   ├── alert_event.py
│   │   │   ├── alert_rule.py
│   │   │   ├── detection_zone.py
│   │   │   ├── export_job.py
│   │   │   ├── audit_log.py
│   │   │   ├── system_event.py
│   │   │   ├── session.py           # Refresh token sessions
│   │   │   ├── api_key.py           # Machine-to-machine auth
│   │   │   └── notification_channel.py
│   │   ├── schemas/                 # Pydantic v2 request/response models
│   │   ├── routers/                 # FastAPI routers, one per domain
│   │   │   ├── auth.py
│   │   │   ├── cameras.py
│   │   │   ├── camera_groups.py
│   │   │   ├── recordings.py
│   │   │   ├── live.py              # HLS stream management
│   │   │   ├── alerts.py
│   │   │   ├── detection.py
│   │   │   ├── users.py
│   │   │   ├── roles.py
│   │   │   ├── export.py
│   │   │   ├── system.py
│   │   │   ├── notifications.py
│   │   │   └── ws.py                # WebSocket hub
│   │   ├── services/                # Business logic, no FastAPI deps
│   │   │   ├── onvif_service.py
│   │   │   ├── camera_service.py
│   │   │   ├── recording_service.py
│   │   │   ├── hls_service.py
│   │   │   ├── export_service.py
│   │   │   ├── auth_service.py
│   │   │   ├── user_service.py
│   │   │   ├── alert_service.py
│   │   │   ├── notification_service.py
│   │   │   ├── storage_service.py
│   │   │   ├── schedule_service.py
│   │   │   └── health_service.py
│   │   ├── workers/                 # Celery tasks
│   │   │   ├── recording.py
│   │   │   ├── export.py
│   │   │   ├── health_check.py
│   │   │   ├── purge.py
│   │   │   ├── alert_consumer.py
│   │   │   └── notifications.py
│   │   ├── middleware/
│   │   │   ├── auth.py              # JWT validation, current_user dep
│   │   │   ├── audit.py             # AuditLog middleware
│   │   │   ├── rate_limit.py        # Per-IP and per-user rate limiting
│   │   │   ├── security_headers.py  # HSTS, CSP, X-Frame-Options etc.
│   │   │   └── request_id.py        # X-Request-ID propagation
│   │   ├── core/
│   │   │   ├── exceptions.py        # Custom exception hierarchy
│   │   │   ├── events.py            # Lifespan startup/shutdown handlers
│   │   │   ├── logging.py           # structlog configuration
│   │   │   └── constants.py
│   │   └── utils/
│   │       ├── encryption.py        # Fernet helpers
│   │       ├── ffmpeg.py            # FFmpeg subprocess wrappers
│   │       ├── onvif_helpers.py
│   │       └── time_utils.py
│   ├── alembic/
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── factories/               # factory-boy model factories
│   │   ├── unit/
│   │   ├── integration/
│   │   └── fixtures/                # test video files, mock ONVIF responses
│   ├── requirements/
│   │   ├── base.txt
│   │   ├── dev.txt
│   │   └── prod.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Dashboard.tsx        # System overview
│   │   │   ├── LiveView.tsx         # Multi-camera live grid
│   │   │   ├── Recordings.tsx       # Timeline + playback
│   │   │   ├── Cameras.tsx          # Camera management
│   │   │   ├── CameraDetail.tsx
│   │   │   ├── Alerts.tsx
│   │   │   ├── Detection.tsx        # Zone config + tuning
│   │   │   ├── Users.tsx
│   │   │   ├── Roles.tsx
│   │   │   ├── AuditLog.tsx
│   │   │   ├── Storage.tsx
│   │   │   ├── Notifications.tsx
│   │   │   └── Settings.tsx
│   │   ├── components/
│   │   │   ├── cameras/
│   │   │   ├── live/
│   │   │   ├── recordings/
│   │   │   ├── alerts/
│   │   │   ├── detection/
│   │   │   ├── users/
│   │   │   └── shared/
│   │   ├── hooks/
│   │   ├── store/
│   │   ├── api/
│   │   ├── types/
│   │   ├── utils/
│   │   └── lib/
│   ├── Dockerfile
│   └── nginx.conf                   # Frontend Nginx config
├── detection_service/
│   ├── main.py
│   ├── detector.py
│   ├── zone_filter.py
│   ├── rules_engine.py
│   ├── tracker.py                   # Multi-object tracking (ByteTrack)
│   ├── frame_buffer.py              # Ring buffer for pre-event frames
│   ├── config_watcher.py            # Hot-reload zones.json from Redis
│   ├── redis_publisher.py
│   ├── health_server.py             # HTTP /health for Docker healthcheck
│   ├── zones.json
│   ├── tests/
│   └── Dockerfile
├── nginx/
│   ├── nginx.conf
│   └── ssl/                         # TLS certs (gitignored)
├── scripts/
│   ├── generate_keys.py             # Generates SECRET_KEY, FERNET_KEY, RSA pair
│   ├── seed_roles.py                # Seeds default roles and permissions
│   └── backup_db.sh
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── SPEC.md                          # ← this file
├── DECISION_LOG.md
└── CLAUDE_CODE_CHEATSHEET.md

```

---

## 4. Security Architecture — Non-Negotiable

### 4.1 Authentication

- **JWT with RS256** (asymmetric). Private key signs tokens; public key verifies.
  Never HS256 (shared secret). Key pair generated at first boot.
- **Access token TTL**: 15 minutes. Short-lived to limit exposure.
- **Refresh token**: opaque UUID stored in `sessions` table, never in JWT.
  TTL: 7 days. One refresh token per device per user.
- **Refresh token rotation**: every use issues a new refresh token and invalidates
  the old one. Detect reuse attacks (double-spend detection).
- **Secure cookie option**: for browser clients, refresh token in HttpOnly, 
  SameSite=Strict, Secure cookie. Never in localStorage.
- **MFA (TOTP)**: optional per user, mandatory for superadmin role.
  Use `pyotp`. QR code provisioning. Backup codes (10, one-time use, hashed).
- **Login lockout**: 5 failed attempts → 15-minute lockout. Tracked per IP + per 
  email independently. Lockout state in Redis.
- **Session management**: users can see all active sessions (device, IP, last used)
  and revoke individual sessions or all-except-current.
- **Password policy**: minimum 12 characters, must contain upper, lower, digit,
  special. Check against HaveIBeenPwned API hash prefix lookup on password set.
- **First boot**: system generates a superadmin account with a one-time password
  printed to stdout only (never logged). Forces password change on first login.

### 4.2 Authorisation (RBAC + ABAC hybrid)

```
Permission string format: resource:action[:qualifier]
Examples:
  cameras:view_live
  cameras:view_live:own_zone          ← zone-scoped
  cameras:configure
  recordings:export
  recordings:export:watermarked_only  ← restricted export
  alerts:acknowledge
  users:manage
  system:admin
  audit:read
  api_keys:manage
```

- Permissions stored as a JSON array in the Role model.
- CameraPermission table provides per-camera overrides (can grant or deny 
  specific cameras to a user regardless of their role).
- Permission checks via FastAPI dependency: `Depends(require_permission("cameras:view_live"))`
- Camera-level checks: `Depends(require_camera_access(camera_id, "view_live"))`
- All 403 responses log the attempted permission to the audit log.

### 4.3 Default Roles

| Role          | Key permissions                                                      |
|---------------|----------------------------------------------------------------------|
| superadmin    | All permissions. Cannot be deleted. Only role that can create admins.|
| admin         | All except system:admin. Can manage users, cameras, roles.           |
| manager       | cameras:*, recordings:*, alerts:*, notifications:read               |
| operator      | cameras:view_live, recordings:view, alerts:view, alerts:acknowledge  |
| viewer        | cameras:view_live on explicitly permitted cameras only               |
| api_client    | Programmatic access. No UI access. Scoped at creation time.         |

### 4.4 Network Security

- All external traffic terminates at Nginx with TLS 1.3 minimum.
- TLS 1.0 and 1.1 explicitly disabled.
- HSTS header: `max-age=31536000; includeSubDomains; preload`
- CSP header: strict policy, no `unsafe-inline`, nonce-based scripts.
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy: disable camera, microphone, geolocation API access
- API rate limiting:
  - `/auth/login`: 10 requests / 10 minutes per IP
  - `/auth/refresh`: 60 requests / hour per user
  - General API: 300 requests / minute per authenticated user
  - WebSocket connections: max 5 per user
- Camera RTSP streams: cameras must be on a dedicated VLAN. The backend 
  container reaches cameras; the frontend never gets RTSP URLs directly.
- Camera credentials: encrypted with Fernet (AES-128-CBC + HMAC-SHA256)
  before DB write. Decrypted only in memory when needed. Never in logs.

### 4.5 Audit Log

Every significant system action writes an AuditLog entry:

```
- Authentication: login, logout, failed_login, mfa_setup, password_change,
                  session_revoke, lockout_triggered
- Cameras: camera_added, camera_removed, camera_configured, time_synced
- Recordings: recording_started, recording_stopped, clip_exported, clip_deleted
- Alerts: alert_created, alert_acknowledged, alert_false_positive
- Users: user_created, user_updated, user_deactivated, role_changed,
         permission_granted, permission_revoked
- System: system_started, system_shutdown, storage_warning, storage_critical,
          backup_completed, config_changed, api_key_created, api_key_revoked
- Detection: zone_added, zone_modified, detection_enabled, detection_disabled
```

Audit log is append-only. No UPDATE or DELETE allowed on audit_log table.
Implement via PostgreSQL row-level security + a dedicated audit DB user that 
only has INSERT + SELECT privileges on that table.

### 4.6 Data Protection

- All data encrypted at rest at filesystem level (host responsibility, documented).
- Camera passwords: Fernet-encrypted per above.
- Export files: optional password-protected ZIP using `pyzipper` (AES-256).
- PII in audit log (IP addresses): configurable retention separate from main audit.
- GDPR/data protection: 
  - Configurable data retention per camera (default 30 days, min 1, max 365).
  - Legal hold flag on AlertEvent: prevents auto-purge regardless of retention.
  - Right to erasure: user accounts can be anonymised (email → sha256, name → "Deleted User"), preserving referential integrity in audit log.
  - Data processing register endpoint for compliance documentation.

---

## 5. Database Schema — Complete

### 5.1 cameras
```
id                  UUID PK  DEFAULT gen_random_uuid()
name                VARCHAR(100) NOT NULL
description         TEXT
ip_address          INET NOT NULL
rtsp_main_url       TEXT              -- main stream (pulled from ONVIF, stored)
rtsp_sub_url        TEXT              -- sub stream for HLS (lower quality)
onvif_port          INTEGER DEFAULT 80
username            VARCHAR(100)
password_encrypted  BYTEA             -- Fernet-encrypted
onvif_profile_main  VARCHAR(50)       -- ONVIF profile token for main stream
onvif_profile_sub   VARCHAR(50)       -- ONVIF profile token for sub stream
manufacturer        VARCHAR(100)
model               VARCHAR(100)
firmware_version    VARCHAR(50)
serial_number       VARCHAR(100)
mac_address         MACADDR
is_vpn              BOOLEAN DEFAULT FALSE
vpn_host            INET
group_id            UUID FK → camera_groups(id) NULLABLE
zone_location       VARCHAR(200)      -- human label "Loading Dock North"
building            VARCHAR(100)
floor               VARCHAR(50)
map_x               FLOAT             -- facility map overlay X (0.0–1.0)
map_y               FLOAT             -- facility map overlay Y (0.0–1.0)
status              camera_status_enum DEFAULT 'unknown'
                    -- ENUM: online, offline, error, recording, unauthorized, unknown
recording_mode      recording_mode_enum DEFAULT 'continuous'
                    -- ENUM: continuous, motion, scheduled, off
resolution_main     VARCHAR(20)       -- e.g. "1920x1080"
resolution_sub      VARCHAR(20)       -- e.g. "640x360"
fps                 SMALLINT DEFAULT 25
bitrate_kbps        INTEGER DEFAULT 2000
codec               codec_enum DEFAULT 'h264'
                    -- ENUM: h264, h265, mjpeg
retention_days      SMALLINT DEFAULT 30
pre_event_seconds   SMALLINT DEFAULT 5   -- buffer before motion trigger
post_event_seconds  SMALLINT DEFAULT 10  -- record after motion ends
ntp_synced          BOOLEAN DEFAULT FALSE
last_ntp_sync       TIMESTAMPTZ
last_seen           TIMESTAMPTZ
last_error          TEXT
consecutive_errors  SMALLINT DEFAULT 0
detection_enabled   BOOLEAN DEFAULT FALSE
privacy_mask        JSONB             -- [{polygon: [[x,y]...], label: "masked"}]
ptz_enabled         BOOLEAN DEFAULT FALSE
ptz_presets         JSONB             -- [{token, name, x, y, z}]
tags                TEXT[]            -- searchable tags
notes               TEXT              -- operator notes
created_at          TIMESTAMPTZ DEFAULT now()
updated_at          TIMESTAMPTZ DEFAULT now()
created_by          UUID FK → users(id)
```

### 5.2 camera_groups
```
id                  UUID PK
name                VARCHAR(100) NOT NULL
description         TEXT
parent_group_id     UUID FK → camera_groups(id) NULLABLE  -- tree structure
color               VARCHAR(7)         -- hex color for UI
icon                VARCHAR(50)        -- icon name
sort_order          INTEGER DEFAULT 0
created_at          TIMESTAMPTZ DEFAULT now()
```

### 5.3 recording_segments
```
id                  UUID PK
camera_id           UUID FK → cameras(id) ON DELETE CASCADE
started_at          TIMESTAMPTZ NOT NULL
ended_at            TIMESTAMPTZ
duration_seconds    INTEGER              -- computed on segment close
file_path           TEXT NOT NULL        -- absolute path on host
file_name           VARCHAR(255) NOT NULL
file_size_bytes     BIGINT
segment_type        segment_type_enum
                    -- ENUM: continuous, motion, scheduled, event, manual
has_motion          BOOLEAN DEFAULT FALSE
motion_score        FLOAT                -- 0.0–1.0 motion intensity
has_alert           BOOLEAN DEFAULT FALSE
alert_event_id      UUID FK → alert_events(id) NULLABLE
checksum_sha256     VARCHAR(64)
is_corrupt          BOOLEAN DEFAULT FALSE
is_on_legal_hold    BOOLEAN DEFAULT FALSE
thumbnail_path      TEXT                 -- path to a keyframe JPEG
width               SMALLINT
height              SMALLINT
fps                 SMALLINT
codec               VARCHAR(20)
created_at          TIMESTAMPTZ DEFAULT now()

INDEXES:
  (camera_id, started_at, ended_at)    -- timeline queries
  (camera_id, segment_type)
  (has_alert) WHERE has_alert = TRUE
  (started_at) BRIN                    -- efficient range scans on time
```

### 5.4 recording_schedules
```
id                  UUID PK
camera_id           UUID FK → cameras(id) ON DELETE CASCADE
name                VARCHAR(100)
days_of_week        SMALLINT[]           -- [0,1,2,3,4,5,6] (0=Mon)
time_start          TIME NOT NULL
time_end            TIME NOT NULL
recording_mode      recording_mode_enum
enabled             BOOLEAN DEFAULT TRUE
created_at          TIMESTAMPTZ DEFAULT now()
```

### 5.5 users
```
id                  UUID PK
email               VARCHAR(254) UNIQUE NOT NULL
full_name           VARCHAR(200) NOT NULL
hashed_password     VARCHAR(200) NOT NULL    -- argon2
role_id             UUID FK → roles(id)
is_active           BOOLEAN DEFAULT TRUE
is_mfa_enabled      BOOLEAN DEFAULT FALSE
mfa_secret          BYTEA                    -- Fernet-encrypted TOTP secret
mfa_backup_codes    JSONB                    -- [{code_hash, used}]
password_changed_at TIMESTAMPTZ
must_change_password BOOLEAN DEFAULT FALSE
failed_login_count  SMALLINT DEFAULT 0
locked_until        TIMESTAMPTZ
last_login          TIMESTAMPTZ
last_login_ip       INET
preferred_language  VARCHAR(10) DEFAULT 'en'
preferred_timezone  VARCHAR(50) DEFAULT 'UTC'
ui_preferences      JSONB                    -- grid layout, theme, etc.
created_at          TIMESTAMPTZ DEFAULT now()
updated_at          TIMESTAMPTZ DEFAULT now()
created_by          UUID FK → users(id)
anonymised_at       TIMESTAMPTZ              -- GDPR erasure timestamp
```

### 5.6 roles
```
id                  UUID PK
name                VARCHAR(100) UNIQUE NOT NULL
display_name        VARCHAR(200)
description         TEXT
permissions         TEXT[]               -- permission strings
is_system_role      BOOLEAN DEFAULT FALSE -- system roles cannot be deleted
created_at          TIMESTAMPTZ DEFAULT now()
updated_at          TIMESTAMPTZ DEFAULT now()
```

### 5.7 camera_permissions
```
user_id             UUID FK → users(id) ON DELETE CASCADE
camera_id           UUID FK → cameras(id) ON DELETE CASCADE
can_view_live       BOOLEAN DEFAULT FALSE
can_view_recordings BOOLEAN DEFAULT FALSE
can_export_clips    BOOLEAN DEFAULT FALSE
can_configure       BOOLEAN DEFAULT FALSE
can_ptz             BOOLEAN DEFAULT FALSE
granted_by          UUID FK → users(id)
granted_at          TIMESTAMPTZ DEFAULT now()
PRIMARY KEY (user_id, camera_id)
```

### 5.8 sessions (refresh tokens)
```
id                  UUID PK              -- this IS the refresh token value
user_id             UUID FK → users(id) ON DELETE CASCADE
device_name         VARCHAR(200)         -- "Chrome on macOS", "NVR Mobile App"
device_fingerprint  VARCHAR(64)          -- hash of user-agent + accept headers
ip_address          INET
is_revoked          BOOLEAN DEFAULT FALSE
revoked_at          TIMESTAMPTZ
revoked_reason      VARCHAR(50)          -- "logout","admin","reuse_detected","expired"
last_used_at        TIMESTAMPTZ
created_at          TIMESTAMPTZ DEFAULT now()
expires_at          TIMESTAMPTZ NOT NULL
```

### 5.9 api_keys
```
id                  UUID PK
name                VARCHAR(200) NOT NULL
key_hash            VARCHAR(64) NOT NULL UNIQUE  -- SHA-256 of the actual key
key_prefix          VARCHAR(10)                  -- first 8 chars, for identification
user_id             UUID FK → users(id)          -- owner
permissions         TEXT[]                       -- subset of owner's permissions
allowed_ips         INET[]                       -- IP whitelist, NULL = any
expires_at          TIMESTAMPTZ                  -- NULL = never
last_used_at        TIMESTAMPTZ
last_used_ip        INET
is_active           BOOLEAN DEFAULT TRUE
created_at          TIMESTAMPTZ DEFAULT now()
```

### 5.10 alert_events
```
id                  UUID PK
camera_id           UUID FK → cameras(id)
alert_rule_id       UUID FK → alert_rules(id) NULLABLE
triggered_at        TIMESTAMPTZ NOT NULL
detection_type      VARCHAR(50)          -- person, vehicle, custom, motion, tampering
zone_name           VARCHAR(100)
confidence          FLOAT
severity            severity_enum        -- ENUM: low, medium, high, critical
rule_triggered      VARCHAR(100)
bbox                JSONB                -- {x1,y1,x2,y2} normalised 0.0–1.0
track_id            INTEGER              -- ByteTrack object ID
frame_path          TEXT                 -- saved still frame at detection moment
clip_path           TEXT                 -- auto-saved ±30s clip
clip_checksum       VARCHAR(64)
is_false_positive   BOOLEAN DEFAULT FALSE
is_on_legal_hold    BOOLEAN DEFAULT FALSE
acknowledged        BOOLEAN DEFAULT FALSE
acknowledged_by     UUID FK → users(id) NULLABLE
acknowledged_at     TIMESTAMPTZ
notes               TEXT                 -- operator notes on acknowledgement
created_at          TIMESTAMPTZ DEFAULT now()

INDEXES:
  (camera_id, triggered_at DESC)
  (acknowledged, severity) WHERE acknowledged = FALSE
  (triggered_at) BRIN
```

### 5.11 alert_rules
```
id                  UUID PK
name                VARCHAR(200) NOT NULL
camera_id           UUID FK → cameras(id) NULLABLE  -- NULL = applies to all
detection_types     TEXT[]
severity            severity_enum
schedule            JSONB             -- {days:[0..6], time_start, time_end} or NULL (always)
enabled             BOOLEAN DEFAULT TRUE
notification_channels UUID[]          -- FK → notification_channels(id)
created_at          TIMESTAMPTZ DEFAULT now()
```

### 5.12 detection_zones
```
id                  UUID PK
camera_id           UUID FK → cameras(id) ON DELETE CASCADE
name                VARCHAR(100) NOT NULL
polygon             JSONB NOT NULL    -- [[x,y],...] normalised 0.0–1.0
restricted          BOOLEAN DEFAULT FALSE
enabled             BOOLEAN DEFAULT TRUE
working_hours_start TIME
working_hours_end   TIME
timezone            VARCHAR(50) DEFAULT 'UTC'
dwell_threshold_s   SMALLINT DEFAULT 30
color               VARCHAR(7)        -- hex, for zone editor UI overlay
created_at          TIMESTAMPTZ DEFAULT now()
updated_at          TIMESTAMPTZ DEFAULT now()
```

### 5.13 export_jobs
```
id                  UUID PK
camera_ids          UUID[]
from_dt             TIMESTAMPTZ NOT NULL
to_dt               TIMESTAMPTZ NOT NULL
status              export_status_enum
                    -- ENUM: queued, processing, completed, failed, expired
progress_pct        SMALLINT DEFAULT 0
file_path           TEXT
file_size_bytes     BIGINT
checksum_sha256     VARCHAR(64)
password_protected  BOOLEAN DEFAULT FALSE
watermark           BOOLEAN DEFAULT TRUE
watermark_text      VARCHAR(200)
error_message       TEXT
requested_by        UUID FK → users(id)
created_at          TIMESTAMPTZ DEFAULT now()
completed_at        TIMESTAMPTZ
expires_at          TIMESTAMPTZ     -- export file deleted after this
```

### 5.14 audit_log
```
id                  BIGSERIAL PK      -- use BIGSERIAL not UUID for volume
user_id             UUID NULLABLE     -- NULL for system-generated events
user_email          VARCHAR(254)      -- denormalised snapshot at log time
action              VARCHAR(100) NOT NULL
resource_type       VARCHAR(100)
resource_id         VARCHAR(200)      -- UUID or other ID as string
detail              JSONB             -- structured context
ip_address          INET
user_agent          TEXT
request_id          VARCHAR(36)       -- X-Request-ID for log correlation
severity            VARCHAR(20) DEFAULT 'info'  -- info, warning, security
created_at          TIMESTAMPTZ DEFAULT now()

-- ROW LEVEL SECURITY:
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
-- Only audit_writer role can INSERT; only audit_reader can SELECT.
-- App DB user has neither -- goes through a function with SECURITY DEFINER.
```

### 5.15 system_events
```
id                  BIGSERIAL PK
event_type          VARCHAR(100)       -- storage_warning, stream_error, etc.
severity            VARCHAR(20)
message             TEXT
detail              JSONB
resolved            BOOLEAN DEFAULT FALSE
resolved_at         TIMESTAMPTZ
created_at          TIMESTAMPTZ DEFAULT now()
```

### 5.16 notification_channels
```
id                  UUID PK
name                VARCHAR(200)
channel_type        VARCHAR(50)        -- email, webhook, telegram, slack, pushover
config              JSONB              -- type-specific config (encrypted)
enabled             BOOLEAN DEFAULT TRUE
created_at          TIMESTAMPTZ DEFAULT now()
```

---

## 6. API Design — Complete Route Manifest

Base: `/api/v1/`
Auth header: `Authorization: Bearer <access_token>` on all protected routes.
API key: `X-API-Key: nvr_<key>` as alternative on all routes.

### Authentication
```
POST   /auth/login              { email, password, mfa_code? }
POST   /auth/refresh            { } (refresh token in HttpOnly cookie)
POST   /auth/logout             { } (revokes current session)
POST   /auth/logout-all         { } (revokes all sessions for user)
GET    /auth/me                 current user profile + permissions
GET    /auth/sessions           list active sessions
DELETE /auth/sessions/{id}      revoke specific session
POST   /auth/mfa/setup          returns QR code URI
POST   /auth/mfa/verify         { code } — activates MFA
DELETE /auth/mfa                { code } — disables MFA
GET    /auth/mfa/backup-codes   download backup codes
POST   /auth/mfa/backup-codes/regenerate
POST   /auth/change-password    { current_password, new_password }
POST   /auth/check-password     { password } — HaveIBeenPwned check
```

### Cameras
```
GET    /cameras                 ?group_id=&status=&tags=&search=&page=&page_size=
POST   /cameras                 register camera manually
POST   /cameras/discover        { subnet } — WS-Discovery scan, returns candidates
POST   /cameras/discover/onvif  { ip, port, username, password } — probe single IP
GET    /cameras/{id}
PATCH  /cameras/{id}
DELETE /cameras/{id}
POST   /cameras/{id}/test-connection   verify ONVIF + RTSP reachability
POST   /cameras/{id}/sync-time         push NTP via ONVIF
GET    /cameras/{id}/capabilities      ONVIF profiles, PTZ support, events
GET    /cameras/{id}/snapshot          returns JPEG keyframe
PATCH  /cameras/{id}/recording-mode    { mode }
GET    /cameras/{id}/stream-url        returns { hls_url, sub_hls_url }
POST   /cameras/{id}/ptz/move          { pan, tilt, zoom, speed }
POST   /cameras/{id}/ptz/stop
GET    /cameras/{id}/ptz/presets
POST   /cameras/{id}/ptz/presets       { name }
POST   /cameras/{id}/ptz/presets/{token}/goto
DELETE /cameras/{id}/ptz/presets/{token}
GET    /cameras/{id}/schedules
POST   /cameras/{id}/schedules
PATCH  /cameras/{id}/schedules/{sched_id}
DELETE /cameras/{id}/schedules/{sched_id}
GET    /cameras/{id}/zones             detection zones
POST   /cameras/{id}/zones
PATCH  /cameras/{id}/zones/{zone_id}
DELETE /cameras/{id}/zones/{zone_id}
GET    /cameras/{id}/permissions       per-user permissions for this camera
PATCH  /cameras/{id}/permissions       bulk update user permissions
GET    /cameras/{id}/stats             recording hours, storage used, alert count
```

### Camera Groups
```
GET    /camera-groups
POST   /camera-groups
GET    /camera-groups/{id}
PATCH  /camera-groups/{id}
DELETE /camera-groups/{id}
POST   /camera-groups/{id}/cameras/{camera_id}   add camera to group
DELETE /camera-groups/{id}/cameras/{camera_id}
```

### Live Streaming
```
GET    /live/{camera_id}/stream-url    start HLS if not running, return URL
DELETE /live/{camera_id}/stream        stop HLS stream for camera
GET    /live/active                    list cameras currently streaming HLS
GET    /live/{camera_id}/snapshot      real-time JPEG snapshot
```

### Recordings
```
GET    /recordings              ?camera_id=&from=&to=&type=&has_alert=&page=
GET    /recordings/{id}
DELETE /recordings/{id}         requires recordings:delete permission
GET    /recordings/timeline     ?camera_id=&date=  (hourly buckets for UI)
GET    /recordings/calendar     ?camera_id=&month= (daily coverage summary)
GET    /recordings/{camera_id}/{date}/continuous   returns full-day coverage map
```

### Export
```
POST   /export                  { camera_ids, from_dt, to_dt, watermark, password }
GET    /export/{job_id}         { status, progress_pct, download_url }
GET    /export/{job_id}/download   streams the file
DELETE /export/{job_id}         cancel or delete export
GET    /export                  list export jobs for current user
```

### Alerts
```
GET    /alerts                  ?camera_id=&severity=&from=&to=&acknowledged=&page=
GET    /alerts/{id}
PATCH  /alerts/{id}/acknowledge { notes }
PATCH  /alerts/{id}/false-positive { notes }
PATCH  /alerts/{id}/legal-hold  { hold: bool }
GET    /alerts/stats            ?hours=24  (counts by severity, camera, rule)
GET    /alerts/{id}/clip        stream the auto-saved clip
GET    /alerts/{id}/frame       returns the still frame JPEG
```

### Alert Rules
```
GET    /alert-rules
POST   /alert-rules
GET    /alert-rules/{id}
PATCH  /alert-rules/{id}
DELETE /alert-rules/{id}
```

### Detection
```
GET    /detection/status        per-camera enabled status, last event, fps
PATCH  /detection/{camera_id}   { enabled, confidence, sample_fps }
GET    /detection/stats         ?hours=24
POST   /detection/{camera_id}/test-frame   run inference on a snapshot, return annotated image
```

### Users
```
GET    /users                   requires users:manage
POST   /users
GET    /users/{id}
PATCH  /users/{id}
DELETE /users/{id}              soft-delete (anonymise for GDPR)
POST   /users/{id}/deactivate
POST   /users/{id}/activate
POST   /users/{id}/unlock       clear login lockout
GET    /users/{id}/sessions     see all sessions for a user
DELETE /users/{id}/sessions     revoke all sessions for a user
GET    /users/{id}/audit-log    user-specific audit history
PATCH  /users/{id}/permissions  bulk set camera permissions
```

### Roles
```
GET    /roles
POST   /roles
GET    /roles/{id}
PATCH  /roles/{id}
DELETE /roles/{id}             cannot delete system roles
GET    /roles/permissions      list all valid permission strings
```

### API Keys
```
GET    /api-keys
POST   /api-keys               returns key once (never stored plaintext)
GET    /api-keys/{id}
PATCH  /api-keys/{id}
DELETE /api-keys/{id}
```

### Notifications
```
GET    /notifications/channels
POST   /notifications/channels
PATCH  /notifications/channels/{id}
DELETE /notifications/channels/{id}
POST   /notifications/channels/{id}/test   send test notification
```

### System
```
GET    /system/health           DB, Redis, Celery, detection service status
GET    /system/storage          total, used, free, per-camera breakdown
GET    /system/events           ?resolved=&severity=&page=
PATCH  /system/events/{id}/resolve
GET    /system/info             version, uptime, camera count, recording count
GET    /system/audit-log        ?user_id=&action=&from=&to=&page=  (admin only)
POST   /system/backup           trigger DB backup
GET    /system/metrics          Prometheus-format metrics (internal only)
```

### WebSocket
```
WS     /ws                      authenticated WebSocket hub
```
WebSocket message types (server → client):
```json
{ "type": "camera_status", "camera_id": "...", "status": "online" }
{ "type": "recording_started", "camera_id": "...", "segment_id": "..." }
{ "type": "alert", "alert_id": "...", "severity": "high", "camera_id": "..." }
{ "type": "storage_warning", "used_pct": 85 }
{ "type": "export_progress", "job_id": "...", "progress_pct": 45 }
{ "type": "system_event", "event_type": "...", "message": "..." }
{ "type": "detection_event", "camera_id": "...", "zone": "...", "type": "person" }
```

---

## 7. Recording Engine — Detailed Design

### 7.1 Recording modes

**Continuous**: FFmpeg records RTSP indefinitely, segmented every 10 minutes.
On segment completion: close file, compute checksum, write RecordingSegment row,
generate thumbnail (first keyframe), start next segment. No gaps.

**Motion-triggered**: 
- Server-side: FFmpeg continuously receives stream; Python motion detection 
  (frame difference score) triggers clip start. Pre-event buffer (ring buffer of 
  last N seconds always in memory). On motion: flush buffer + continue recording.
  On motion end + post-event period: close segment.
- Camera-side (preferred when camera supports it): subscribe to ONVIF motion events.
  Use event as trigger, still record via FFmpeg. More reliable than server-side diff.

**Scheduled**: Celery Beat starts/stops recording tasks per schedule rows.
Multiple schedules per camera. Overlap handled: if recording already running,
no-op. Gap between schedules: recording stops.

**Manual**: Operator triggers via API. Runs until explicitly stopped or max 4 hours.

### 7.2 FFmpeg command architecture

Main stream recording (continuous):
```
ffmpeg -rtsp_transport tcp -i <rtsp_url>
       -c:v copy -an
       -f segment -segment_time 600 -segment_format mp4
       -segment_atclocktime 1 -strftime 1
       -segment_list <index.m3u8_path>
       -reset_timestamps 1
       <output_path>/%Y%m%d_%H%M%S.mp4
```

HLS sub-stream (live view):
```
ffmpeg -rtsp_transport tcp -i <rtsp_sub_url>
       -c:v libx264 -preset ultrafast -tune zerolatency -crf 28
       -c:a aac -b:a 64k
       -f hls -hls_time 2 -hls_list_size 10 -hls_flags delete_segments
       -hls_segment_filename <hls_path>/%03d.ts
       <hls_path>/index.m3u8
```

Export clip:
```
ffmpeg -i "concat:<segment1.mp4>|<segment2.mp4>|..."
       -vf "drawtext=text='<watermark>':fontcolor=white:fontsize=18:
            x=10:y=10:box=1:boxcolor=black@0.4"
       -c:v libx264 -crf 18 -c:a copy
       -movflags +faststart
       <output.mp4>
```

### 7.3 Process supervision

Each recording task owns its FFmpeg process. Celery task holds the PID.
Health check polls every 30s: if process dead and recording_mode != off, restart.
Exponential backoff on repeated failures. After 10 failures: mark camera status 
= error, write SystemEvent, send notification.

All FFmpeg stderr piped to structlog. Parse for error patterns:
- "Connection refused" → camera offline
- "Invalid data found" → corrupt stream
- "Immediate exit requested" → clean shutdown

### 7.4 Storage management

Storage path layout:
```
/data/recordings/
  {camera_id}/
    {YYYY-MM-DD}/
      {HH-MM-SS}_{segment_type}.mp4
      {HH-MM-SS}_{segment_type}.jpg  (thumbnail)

/data/hls/
  {camera_id}/
    index.m3u8
    001.ts … (rolling window)

/data/exports/
  {export_job_id}/
    export_{from}_{to}.mp4  (or .zip if password protected)

/data/alerts/
  {alert_event_id}/
    frame.jpg
    clip.mp4
```

Purge task (runs daily at 03:00):
- Query segments where ended_at < now() - retention_days AND is_on_legal_hold = FALSE
- For each: delete file, delete thumbnail, delete DB row
- Delete export files where expires_at < now()
- Write storage stats to SystemEvent

Storage warnings:
- 80% full → SystemEvent severity=warning + notification
- 90% full → SystemEvent severity=critical + notification + reduce retention by 20%
- 95% full → emergency purge oldest segments regardless of retention

---

## 8. Live View Architecture

### 8.1 HLS streaming pipeline

```
Camera RTSP → FFmpeg (sub stream) → HLS segments → Nginx static serve → HLS.js
```

- HLS.js in browser fetches index.m3u8, then .ts segments directly from Nginx.
- No video bytes pass through FastAPI (Nginx serves /hls/* directly).
- FFmpeg uses sub stream (lower resolution) for live view to reduce bandwidth.
- HLS segment duration: 2 seconds. List size: 10 (20-second sliding window).
- Latency: ~6–10 seconds (3 segments buffering in HLS.js).
- For ultra-low latency (future): consider RTSP → WebRTC via mediamtx.

### 8.2 Live view UI

- Grid layouts: 1×1, 2×2, 3×3, 4×4 (configurable, saved to user preferences)
- Camera picker with search and group filter
- Each cell shows: video feed, camera name overlay, recording mode indicator dot,
  alert badge if unacknowledged alert in last 5 minutes
- Full-screen mode per camera (double-click)
- PTZ controls overlay (shown only if camera.ptz_enabled)
- Snapshot button per cell (downloads JPEG)
- Connection status indicator: buffering spinner, offline placeholder, error state
- Auto-reconnect on stream failure (3 retries, then show error with manual retry button)
- Bandwidth indicator: show if stream is degraded

---

## 9. Detection Service — Detailed Design

### 9.1 Architecture

Completely isolated Python process. No shared memory with the backend.
Communication: Redis pub/sub only (receives config reload events, publishes alerts).

```
main.py
  ├── Reads CAMERAS env var (JSON)
  ├── Loads zones from Redis key "nvr:zones:{camera_id}" (hot-reloadable)
  ├── Spawns DetectionWorker thread per camera
  ├── Spawns ConfigWatcher thread (subscribes to "nvr:config:reload:*")
  ├── Spawns HealthServer (HTTP /health on port 8001)
  └── Handles SIGTERM: graceful shutdown of all workers (max 10s)
```

### 9.2 DetectionWorker (per camera)

```python
class DetectionWorker(threading.Thread):
    SAMPLE_INTERVAL = 1.0 / SAMPLE_FPS   # e.g. 0.5s at 2fps
    
    Lifecycle:
    1. Open RTSP with OpenCV (cv2.VideoCapture, tcp transport)
    2. Skip frames to match SAMPLE_FPS (read + discard)
    3. Run YOLO inference on sampled frame
    4. Pass detections through ZoneFilter
    5. Pass through RulesEngine
    6. If event: append to FrameBuffer, publish to Redis
    7. On RTSP failure: wait 10s, reconnect. Max 20 retries. Then log + sleep 5min.
```

### 9.3 Multi-object tracking (ByteTrack)

Integrate `supervision` library (Roboflow) for ByteTrack.
Assigns stable track_id to each detected object across frames.
Enables: dwell time calculation, trajectory analysis, "same person" correlation.
Track state maintained per camera in DetectionWorker memory.
Tracks expire after 5 seconds of no detection.

### 9.4 Frame buffer (pre-event recording)

Ring buffer of last 30 seconds of raw frames per camera (configurable).
On alert trigger: save buffer frames + 10 subsequent frames as alert context.
This gives security staff visual context for what happened before the trigger.

### 9.5 Rules engine

```python
Rules evaluated in priority order. First match wins per frame.

1. TAMPERING
   Detect if camera has been covered, moved, or defocused.
   Method: compare current frame histogram to baseline. Deviation > threshold → alert.
   Severity: critical

2. RESTRICTED_ZONE_ANY_TIME
   Any detection (person or vehicle) in a zone with restricted=True.
   Severity: high. Always active regardless of working hours.

3. AFTER_HOURS_PERSON
   Person detected outside working_hours. Zone restricted=False.
   Severity: high.

4. AFTER_HOURS_VEHICLE
   Vehicle (car, truck, motorcycle) detected outside working hours.
   Severity: medium.

5. DWELL_TIME
   Object track_id present in zone for > dwell_threshold_s seconds.
   Severity: medium.

6. OBJECT_REMOVAL (future)
   Background subtraction detects persistent object disappearance from inventory area.
   Severity: high. Requires calibration period (first 24h = learning mode).

Alert cooldown: same rule + same zone + same track_id → suppress for 60 seconds.
Prevents alert storms from a single person standing in a zone.
```

### 9.6 Confidence and filtering

- Minimum confidence threshold: configurable per camera (default 0.5)
- Classes detected: person (0), bicycle (1), car (2), motorcycle (3), 
  bus (5), truck (7). All others ignored.
- Non-maximum suppression: IoU threshold 0.45 (YOLO default)
- Zone filter: centroid of bbox must be inside zone polygon (Shapely point-in-polygon)
- Privacy mask: if camera.privacy_mask is set, black out those regions before inference

---

## 10. Frontend — Page-by-Page Specification

### 10.1 Login
- Email + password fields. Show/hide password toggle.
- "Remember this device" checkbox (extends session).
- MFA code field appears after valid credentials (conditional render).
- Login error: generic "Invalid credentials" (never distinguish email vs password).
- Lockout state: show countdown timer to unlock.
- Redirect to originally requested URL after login.

### 10.2 Dashboard (home)
- System health bar: DB, Redis, Celery workers, detection service — green/amber/red.
- Storage widget: donut chart, total / used / free, per-camera top consumers.
- Camera status grid: compact cards, green dot = online + recording, counts.
- Alert summary: unacknowledged alerts by severity (critical, high, medium, low).
- Recent alerts feed (last 10, real-time via WebSocket).
- Recording activity chart: cameras × hours for today (coverage heatmap).
- Quick actions: "Add camera", "View live", "Export clip".

### 10.3 Live View
- Grid selector toolbar: 1, 4, 9, 16 layouts.
- Camera picker sidebar (collapsible): searchable list with group tree.
  Drag camera to grid cell. Or click to auto-fill next empty cell.
- Each grid cell:
  - HLS.js video player (16:9 aspect ratio enforced)
  - Bottom overlay: camera name, location, recording mode dot (●=continuous, ○=motion)
  - Top-right: alert badge (red, count of unacknowledged alerts)
  - Hover: PTZ controls (if enabled), snapshot button, fullscreen button
  - Offline: grey placeholder with camera name and "Last seen: X min ago"
  - Error: red border, error message, retry button
- Preset view layouts: save and restore current grid configuration.
- Screen division presets: "All loading dock cameras", "All floor 2" etc.

### 10.4 Recordings
- Left panel: camera selector (tree), date picker (calendar), filter bar.
- Timeline area (main):
  - 24-hour horizontal axis.
  - Colour bands: blue=continuous, amber=motion, red=event/alert, grey=gap.
  - Click and drag to select time range (min 10s, max 4 hours).
  - Hover: tooltip showing segment type, size, duration.
  - Zoom: scroll to zoom in/out. 24h → 1h → 15min granularity.
- Player area (appears on time range selection or segment click):
  - Video player with custom controls (play/pause, speed: 0.5×, 1×, 2×, 4×, 8×).
  - Frame-by-frame advance (arrow keys).
  - Alert markers on playback scrubber (red triangles).
  - "Add to export" button.
- Multi-camera comparison:
  - Select up to 4 cameras + same time range → sync playback side-by-side.
  - Single scrubber controls all players.
- Export panel:
  - Selected ranges and cameras listed.
  - Options: watermark on/off, watermark text, password protect (optional).
  - Submit → shows progress bar via polling.
  - Download button when complete, with SHA256 checksum displayed.
- Calendar view: month overview, days with recordings shown, click day → switch timeline to that day.

### 10.5 Camera Management
- Camera list: table with columns: name, location, group, status, recording mode,
  resolution, retention, last seen, actions.
- Sortable, filterable, searchable.
- "Discover cameras" button → opens scan panel (subnet input, scan progress, candidate list with one-click add).
- Add camera dialog: manual form with connection test button (verifies ONVIF + RTSP before save).
- Camera detail page (tabbed):
  
  **Overview tab**: status card, stream info, last event, today's storage, uptime counter.
  
  **Settings tab**:
  - General: name, description, location, group, tags, notes
  - Connection: IP, port, credentials, VPN flag
  - Recording: mode, resolution, fps, bitrate, codec, retention days, pre/post event buffer
  - Advanced: ONVIF profiles, sub stream config
  - Save button disabled until changes made; confirms before leaving with unsaved changes.
  
  **Schedule tab**: weekly grid (days × hours), click to add schedule slot, drag to resize.
  
  **Detection tab**: enable toggle, confidence slider, sample rate, zone list.
  Zone editor: camera snapshot as background, draw polygon zones with click,
  name each zone, set restricted flag, working hours, dwell threshold.
  
  **PTZ tab** (only if ptz_enabled): live mini-player + directional D-pad,
  zoom slider, preset list (save current position, go to preset).
  
  **Permissions tab**: per-user permission matrix for this camera.
  
  **Stats tab**: charts — recording hours per day (last 30 days), storage used trend,
  alert frequency by hour, stream health history.

### 10.6 Alerts
- Table: time, camera, zone, rule, severity badge, thumbnail, acknowledged badge.
- Filters: camera, severity, rule, date range, acknowledged/open, false positive.
- Bulk actions: acknowledge selected, mark as false positive, set legal hold.
- Alert detail panel (slide-over):
  - Still frame with bbox overlay drawn on top.
  - Detection metadata: confidence, zone, track_id, rule triggered.
  - Clip player (auto-saved ±30s clip).
  - Timeline context: where this alert falls in the recording timeline.
  - Acknowledge form: notes field, submit.
  - Legal hold toggle.
  - Link to full recording at this timestamp.
- Alert stats chart: alerts over time by severity (last 24h, 7d, 30d selectable).
- Export alerts report: CSV of filtered results.

### 10.7 Users & Roles
- User list: table, sortable. Shows name, email, role, last login, status, MFA enabled.
- Invite user: email + role. System sends invite email with one-time setup link.
- User detail: edit profile, change role, reset password, view sessions, deactivate/activate.
- Camera permissions matrix: rows=cameras, columns=permission types, checkbox grid.
- Role management: list roles, view permissions breakdown, create custom role (permission picker checklist), cannot modify system roles.

### 10.8 Audit Log
- Filterable table: user, action, resource, IP, date range.
- Non-deletable, admin-only.
- Export to CSV.
- Visual diff for config change entries (before/after JSON diff).

### 10.9 Storage
- Donut chart: used / free.
- Per-camera table: camera name, recording mode, storage used, days of recordings, estimated days until full.
- Retention settings shortcut: quick edit retention days per camera.
- Pending exports list with sizes.
- Purge preview: "If you reduce retention to X days, Y GB will be freed."

### 10.10 Settings (System)
- General: facility name, timezone, language.
- Storage: base path display, storage warning thresholds.
- Notifications: manage channels (email, webhook, Telegram, Slack).
- Network: VPN camera subnet config, Nginx upstream config display.
- Security: session timeout, password policy display, MFA enforcement toggle.
- Backup: manual backup trigger, backup schedule, last backup status.
- API Keys: list, create, revoke.
- About: version, uptime, build info, license.

---

## 11. Notification Channels

Support all of the following. Config stored encrypted in `notification_channels.config`.

| Channel   | Config fields                            | Library          |
|-----------|------------------------------------------|------------------|
| Email     | smtp_host, smtp_port, user, pass, to[]   | smtplib          |
| Webhook   | url, method, headers, body_template      | httpx            |
| Telegram  | bot_token, chat_id                       | httpx (Bot API)  |
| Slack     | webhook_url                              | httpx            |
| Pushover  | app_token, user_key                      | httpx            |

Notification payload for alerts:
- Camera name + location
- Alert severity + rule triggered
- Timestamp
- Thumbnail image (where channel supports attachments)
- Direct link to alert in UI

Retry logic: failed notifications → retry 3×  with exponential backoff.
Dead letter: log failure to SystemEvent after 3 retries.

---

## 12. ONVIF Integration — Implementation Notes

python-onvif-zeep quirks to handle:
- Many cameras return malformed WSDL. Use zeep's `Settings(strict=False)`.
- WS-Discovery timeout: 5 seconds, catch all socket exceptions.
- Time sync: always send UTC. Camera may store local time internally — we use NTP.
- RTSP URL from ONVIF: may contain placeholder host `0.0.0.0` — replace with camera IP.
- Profile S: all cameras must support. Profile G (on-camera storage) and T (H.265) are optional.
- Authentication: Digest auth for ONVIF SOAP. WS-UsernameToken as fallback.
- Re-authentication: ONVIF sessions expire. Reconnect on auth error, don't crash.
- Camera capabilities differ widely: always probe and store, never assume.

ONVIF operations to implement:
```
DeviceService:
  GetDeviceInformation → manufacturer, model, firmware, serial, mac
  GetSystemDateAndTime → verify clock drift
  SetSystemDateAndTime → NTP push
  GetCapabilities → what the camera supports
  GetNetworkInterfaces → verify MAC, IP

MediaService:
  GetProfiles → list stream profiles
  GetStreamUri → get RTSP URL per profile
  GetVideoEncoderConfigurations → resolution, fps, bitrate, codec
  SetVideoEncoderConfiguration → push settings
  GetSnapshotUri → JPEG snapshot URL

PTZService (if supported):
  GetConfigurations, GetPresets, GotoPreset, SetPreset, RemovePreset
  ContinuousMove, RelativeMove, Stop

EventService (if supported):
  Subscribe → WS-BaseNotification for motion events
  GetEventProperties → what events this camera can emit
```

---

## 13. Code Quality Standards — Enforced in Every Session

1. **Type hints everywhere**: all function signatures, all class attributes. No `Any` without a comment explaining why.
2. **Async purity**: all FastAPI route functions `async def`. All DB calls awaited. No synchronous I/O in async context (no `open()`, `os.path.*`, `time.sleep()` — use `anyio.Path`, `asyncio.sleep()`).
3. **No raw SQL**: SQLAlchemy ORM or `text()` with explicit params only. Never f-string SQL.
4. **Error handling**: all exceptions caught at service layer, re-raised as domain exceptions. Routers catch domain exceptions and raise `HTTPException` with appropriate status codes and `code` field.
5. **Secrets**: never in logs, never in error messages, never in API responses. Camera passwords decrypted in memory, never returned via API (only `"***"` placeholder).
6. **Logging**: `structlog` everywhere. Include `request_id`, `user_id`, `camera_id` in log context. No `print()`.
7. **Tests required**: every new service function gets a unit test. Every new route gets an integration test. Minimum 80% coverage enforced in CI.
8. **Migrations**: every model change gets an Alembic migration. Never `Base.metadata.create_all()` in production code.
9. **Idempotency**: all Celery tasks must be safe to retry. Use DB state to detect already-completed work.
10. **Pagination**: all list endpoints paginated. Max `page_size` = 100. Default = 50.
11. **Validation**: Pydantic validators on all inputs. Reject unknown fields (`model_config = ConfigDict(extra='forbid')`).
12. **CORS**: only allow configured origins. Never `*` in production.
13. **Dependency injection**: use FastAPI `Depends()` for all shared state. No module-level singletons except the Celery app and settings.
14. **Database constraints**: all FK constraints defined in the model. Unique constraints at DB level, not just application level.
15. **Soft deletes**: User model uses anonymisation. Camera uses `is_deleted` flag + `deleted_at`. Hard deletes only on cascade (segments when camera deleted, permissions when user deleted).

---

## 14. Environment Variables — Complete

```bash
# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://nvr:PASSWORD@postgres:5432/nvr
DATABASE_URL_SYNC=postgresql+psycopg2://nvr:PASSWORD@postgres:5432/nvr  # alembic
POSTGRES_PASSWORD=

# ── Redis ────────────────────────────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1   # separate DB for Celery
CELERY_RESULT_BACKEND=redis://redis:6379/2

# ── Security ─────────────────────────────────────────────────────────────────
RSA_PRIVATE_KEY_PATH=/run/secrets/rsa_private.pem   # RS256 JWT signing
RSA_PUBLIC_KEY_PATH=/run/secrets/rsa_public.pem
FERNET_KEY=                              # camera credential encryption
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
COOKIE_SECURE=true                       # set false only in local dev
COOKIE_DOMAIN=                           # set in production

# ── Storage ──────────────────────────────────────────────────────────────────
STORAGE_PATH=/data/recordings
HLS_PATH=/data/hls
EXPORT_PATH=/data/exports
ALERT_CLIPS_PATH=/data/alerts
STORAGE_WARNING_PCT=80
STORAGE_CRITICAL_PCT=90
EXPORT_EXPIRY_HOURS=48

# ── CORS + Network ───────────────────────────────────────────────────────────
CORS_ORIGINS=https://nvr.yourdomain.com
ALLOWED_HOSTS=nvr.yourdomain.com

# ── Email ─────────────────────────────────────────────────────────────────────
SMTP_HOST=
SMTP_PORT=587
SMTP_STARTTLS=true
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@yourdomain.com

# ── HaveIBeenPwned ───────────────────────────────────────────────────────────
HIBP_API_KEY=                            # optional, increases rate limit

# ── Detection service ────────────────────────────────────────────────────────
DETECTION_CONFIDENCE=0.5
DETECTION_SAMPLE_FPS=2
DETECTION_MODEL_PATH=/models/yolov8n.pt
DETECTION_ALERT_COOLDOWN_S=60

# ── Application ──────────────────────────────────────────────────────────────
APP_ENV=production                       # development | staging | production
APP_VERSION=1.0.0
LOG_LEVEL=INFO
FACILITY_NAME=My Facility
DEFAULT_TIMEZONE=UTC
DEFAULT_LANGUAGE=en
```

---

## 15. Out of Scope (Do Not Implement Without a DECISION_LOG Entry)

- Cloud storage / S3 sync
- Mobile native app (iOS/Android)
- Multi-server federation / clustering
- Face recognition or face identification
- License plate recognition (ANPR)
- Audio recording or two-way audio
- Custom YOLO model training pipeline (use pretrained initially)
- ONVIF Profile A (access control integration)
- Fisheye lens dewarping
- Video analytics SaaS integrations
