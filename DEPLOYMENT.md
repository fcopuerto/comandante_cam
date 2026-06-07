# DEPLOYMENT.md

Deployment guide for NVR Pro on a Linux host (tested on Proxmox LXC with Ubuntu 22.04).

## Prerequisites

- Docker Engine 24+ and Docker Compose v2
- Nginx (for TLS termination — runs outside Docker)
- SSL certificate for your domain (Let's Encrypt recommended)
- Minimum 4 vCPU, 8 GB RAM, 500 GB storage for the recording volume

---

## Step 1 — Generate secrets

Run this once on the host machine. It creates the RSA key pair and Fernet key:

```bash
docker compose run --rm backend python scripts/generate_keys.py
```

The script writes files to `./secrets/`. Keep these files safe — loss means all encrypted camera passwords are permanently unrecoverable.

---

## Step 2 — Configure `.env`

Copy the example and fill in every value:

```bash
cp .env.example .env
```

Required values:

```env
# Database
DATABASE_URL=postgresql+asyncpg://nvr:CHANGE_ME@postgres:5432/nvr
DATABASE_URL_SYNC=postgresql+psycopg2://nvr:CHANGE_ME@postgres:5432/nvr
POSTGRES_PASSWORD=CHANGE_ME

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# Security — output of scripts/generate_keys.py
RSA_PRIVATE_KEY_PATH=/run/secrets/rsa_private.pem
RSA_PUBLIC_KEY_PATH=/run/secrets/rsa_public.pem
FERNET_KEY=<output from generate_keys.py>

# Storage paths (bind-mounted volumes)
STORAGE_PATH=/data/recordings
HLS_PATH=/data/hls
EXPORT_PATH=/data/exports
ALERT_CLIPS_PATH=/data/alerts

# Networking
CORS_ORIGINS=https://nvr.yourdomain.com
ALLOWED_HOSTS=nvr.yourdomain.com,localhost

# Application
APP_ENV=production
FACILITY_NAME=Your Facility Name
```

Optional (email notifications):
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_STARTTLS=true
SMTP_USER=your@gmail.com
SMTP_PASSWORD=app-specific-password
SMTP_FROM=nvr@yourdomain.com
```

---

## Step 3 — Start services

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

This starts: `postgres`, `redis`, `backend`, `worker`, `detection`, `frontend`.

Check all containers came up:

```bash
docker compose ps
docker compose logs -f backend
```

The backend performs startup checks (DB, Redis, RSA keys, Fernet) and will exit with an error if any check fails. Fix the reported issue and restart.

---

## Step 4 — Run database migrations

```bash
docker compose exec backend alembic upgrade head
```

This is safe to run on a running system — Alembic locks the migration table.

---

## Step 5 — Seed roles and create first admin

```bash
docker compose exec backend python scripts/seed_roles.py
```

If no users exist, this creates a `superadmin` user with a randomly generated password printed to stdout. **Copy this password immediately** — it is never stored or logged again.

```
✓ Seeded 6 default roles
✓ Created initial superadmin user: admin@nvr.local
  One-time password: <shown here>
  Change this password on first login.
```

---

## Step 6 — Configure Nginx (TLS termination)

Example `/etc/nginx/sites-available/nvr`:

```nginx
server {
    listen 443 ssl http2;
    server_name nvr.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/nvr.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/nvr.yourdomain.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;

    # Frontend
    location / {
        proxy_pass http://localhost:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # API
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
    }

    # WebSocket
    location /ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }

    # HLS segments (served directly by Nginx for performance)
    location /hls/ {
        alias /data/hls/;
        add_header Cache-Control "no-cache";
        add_header Access-Control-Allow-Origin *;
        types { application/vnd.apple.mpegurl m3u8; video/mp2t ts; }
    }
}

server {
    listen 80;
    server_name nvr.yourdomain.com;
    return 301 https://$host$request_uri;
}
```

```bash
ln -s /etc/nginx/sites-available/nvr /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

---

## Step 7 — First login

Open `https://nvr.yourdomain.com` in a browser. Log in with:
- Email: `admin@nvr.local`
- Password: the one-time password from Step 5

You will be prompted to change the password on first login.

---

## Step 8 — Add cameras and configure detection

1. Go to **Cameras → Discover** to scan your network for ONVIF cameras
2. Or click **Add camera** and enter IP/credentials manually
3. Use **Test connection** to verify ONVIF and RTSP connectivity
4. Go to **Settings → General** to configure storage thresholds and defaults
5. Open each camera's **Detection** tab to draw zones and set alert rules

---

## Backup strategy

Daily backups run automatically via Celery Beat at 03:00 UTC:

```bash
# Manual backup
docker compose exec backend bash scripts/backup_db.sh
```

Backups are written to `BACKUP_PATH` (default `/data/backups`). The last 7 daily backups are kept. **Back up the `/data/backups` directory and the `./secrets/` directory to off-site storage.**

---

## Update procedure

```bash
# Pull latest images
docker compose pull

# Apply migrations before starting new containers
docker compose run --rm backend alembic upgrade head

# Rolling restart (zero downtime if using multiple replicas)
docker compose up -d --no-deps backend worker detection frontend
```

---

## Rollback procedure

```bash
# Roll back one migration
docker compose exec backend alembic downgrade -1

# Restart with the previous image tag
docker compose up -d --no-deps backend worker
```

---

## Monitoring

The system exposes health and metrics endpoints:

| Endpoint | Access | Purpose |
|---|---|---|
| `GET /health` | Public | Liveness probe for load balancer |
| `GET /api/v1/system/health` | Authenticated | Service status (DB, Redis, Workers, Detection) |
| `GET /api/v1/system/metrics` | Localhost only | Prometheus metrics scrape |

Prometheus scrape config (`prometheus.yml`):

```yaml
scrape_configs:
  - job_name: nvr
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: /api/v1/system/metrics
```

Key metrics to alert on:
- `nvr_cameras_online` dropping unexpectedly
- Storage disk usage > 80% (`node_filesystem_avail_bytes` on `/data`)
- Backend container restarts (`container_restarts_total`)
- `nvr_login_failures_total` rate spike (possible brute force)

---

## Security notes

- JWT access tokens expire in 15 minutes. Refresh tokens rotate on every use with double-spend detection.
- Camera passwords are encrypted with Fernet (AES-128-CBC) at rest. Decrypted only in memory for ONVIF calls.
- RTSP stream URLs are never sent to the browser — only HLS playlist URLs.
- The `/api/v1/system/metrics` endpoint is protected by localhost-only IP check. Do not expose it externally.
- MFA (TOTP) is mandatory for the superadmin role.
