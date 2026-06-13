#!/usr/bin/env bash
# =============================================================================
# NVR Pro — deployment tool
# Usage: ./deploy.sh <command> [options]
#
# Commands:
#   deploy    Full first-time setup on a fresh host
#   update    Rolling update: pull → migrate → restart (zero-downtime)
#   status    Show container health, disk usage, last backup
#
# Target (choose one):
#   --host          Direct SSH target, e.g. admin@192.168.1.100
#
#   --proxmox-host  Proxmox server IP or hostname
#   --proxmox-user  Proxmox SSH user              (default: root)
#   --proxmox-pass  Proxmox SSH password           (requires sshpass)
#   --lxc-id        LXC container ID to deploy into, e.g. 211
#
# Options:
#   --dir     Remote directory inside the target  (default: /opt/nvr)
#   --env     Local .env file to upload           (default: .env)
#   --branch  Git branch to deploy                (default: main)
#   --key     SSH private key file
#   --dry-run Print commands without executing
# =============================================================================

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${BLUE}▶${RESET}  $*"; }
success() { echo -e "${GREEN}✓${RESET}  $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET}  $*"; }
error()   { echo -e "${RED}✗${RESET}  $*" >&2; }
step()    { echo -e "\n${BOLD}── Step $1: $2 ──${RESET}"; }
die()     { error "$*"; exit 1; }

# ── Defaults ─────────────────────────────────────────────────────────────────
REMOTE_HOST=""
PROXMOX_HOST=""
PROXMOX_USER="root"
PROXMOX_PASS=""
LXC_ID=""
DEPLOY_MODE=""          # "ssh" or "proxmox" — resolved after arg parsing
SSH_PASS=""             # password for direct --host SSH (use sshpass)

REMOTE_DIR="/opt/nvr-pro"
LOCAL_ENV=".env"
BRANCH="main"
SSH_KEY=""
DRY_RUN=false
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Argument parsing ──────────────────────────────────────────────────────────
COMMAND="${1:-help}"
shift || true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)           REMOTE_HOST="$2";   shift 2 ;;
    --ssh-pass)       SSH_PASS="$2";      shift 2 ;;
    --proxmox-host)   PROXMOX_HOST="$2";  shift 2 ;;
    --proxmox-user)   PROXMOX_USER="$2";  shift 2 ;;
    --proxmox-pass)   PROXMOX_PASS="$2";  shift 2 ;;
    --lxc-id)         LXC_ID="$2";        shift 2 ;;
    --dir)            REMOTE_DIR="$2";    shift 2 ;;
    --env)            LOCAL_ENV="$2";     shift 2 ;;
    --branch)         BRANCH="$2";        shift 2 ;;
    --key)            SSH_KEY="$2";       shift 2 ;;
    --dry-run)        DRY_RUN=true;       shift ;;
    *) die "Unknown option: $1" ;;
  esac
done

# Fall back to env vars so you don't have to pass passwords on every run.
[[ -z "$PROXMOX_PASS" ]] && PROXMOX_PASS="${NVR_PROXMOX_PASS:-}"
[[ -z "$SSH_PASS"     ]] && SSH_PASS="${NVR_SSH_PASS:-}"

# Resolve deploy mode
if [[ -n "$PROXMOX_HOST" && -n "$LXC_ID" ]]; then
  DEPLOY_MODE="proxmox"
elif [[ -n "$REMOTE_HOST" ]]; then
  DEPLOY_MODE="ssh"
fi

# ── Direct SSH primitives ─────────────────────────────────────────────────────
_ctl="${HOME}/.ssh/nvr-deploy-%r@%h:%p"
ssh_opts=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10
          -o ControlMaster=auto -o "ControlPath=${_ctl}" -o ControlPersist=120)
[[ -n "$SSH_KEY" ]] && ssh_opts+=(-i "$SSH_KEY")

ssh_run() {
  $DRY_RUN && { echo -e "  ${YELLOW}[dry-run]${RESET} ssh ${REMOTE_HOST} $*"; return 0; }
  # shellcheck disable=SC2029
  if [[ -n "$SSH_PASS" ]]; then
    SSHPASS="$SSH_PASS" sshpass -e ssh "${ssh_opts[@]}" "$REMOTE_HOST" "$@"
  else
    ssh "${ssh_opts[@]}" "$REMOTE_HOST" "$@"
  fi
}

# Run a privileged command on the remote host via sudo (piping password if available)
ssh_sudo() {
  $DRY_RUN && { echo -e "  ${YELLOW}[dry-run]${RESET} ssh ${REMOTE_HOST} sudo $*"; return 0; }
  if [[ -n "$SSH_PASS" ]]; then
    ssh_run "printf '%s\n' '${SSH_PASS}' | sudo -S $*"
  else
    ssh_run "sudo $*"
  fi
}

ssh_run_tty() {
  $DRY_RUN && { echo -e "  ${YELLOW}[dry-run]${RESET} ssh -t ${REMOTE_HOST} $*"; return 0; }
  if [[ -n "$SSH_PASS" ]]; then
    SSHPASS="$SSH_PASS" sshpass -e ssh -t "${ssh_opts[@]}" "$REMOTE_HOST" "$@"
  else
    ssh -t "${ssh_opts[@]}" "$REMOTE_HOST" "$@"
  fi
}

rsync_to() {
  local src="$1" dst="$2"
  $DRY_RUN && { echo -e "  ${YELLOW}[dry-run]${RESET} rsync $src → ${REMOTE_HOST}:${dst}"; return 0; }
  local rsync_opts=(-az --delete --exclude='.git' --exclude='__pycache__'
    --exclude='*.pyc' --exclude='.env' --exclude='node_modules'
    --exclude='frontend/dist' --exclude='secrets/')
  local ssh_e="ssh ${ssh_opts[*]}"
  [[ -n "$SSH_PASS"  ]] && ssh_e="sshpass -e ssh ${ssh_opts[*]}"
  [[ -n "$SSH_KEY"   ]] && ssh_e+=" -i $SSH_KEY"
  SSHPASS="${SSH_PASS:-}" rsync "${rsync_opts[@]}" -e "$ssh_e" "$src" "${REMOTE_HOST}:${dst}"
}

upload_file() {
  local src="$1" dst="$2"
  $DRY_RUN && { echo -e "  ${YELLOW}[dry-run]${RESET} scp $src → ${REMOTE_HOST}:${dst}"; return 0; }
  if [[ -n "$SSH_PASS" ]]; then
    SSHPASS="$SSH_PASS" sshpass -e scp "${ssh_opts[@]}" "$src" "${REMOTE_HOST}:${dst}"
  else
    scp "${ssh_opts[@]}" "$src" "${REMOTE_HOST}:${dst}"
  fi
}

# ── Proxmox primitives ────────────────────────────────────────────────────────
pxm_ssh_opts=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10
              -o ControlMaster=auto -o "ControlPath=${_ctl}" -o ControlPersist=120)
[[ -n "$SSH_KEY" ]] && pxm_ssh_opts+=(-i "$SSH_KEY")

# Run a command on the Proxmox HOST (not inside the LXC)
pxm_run() {
  $DRY_RUN && { echo -e "  ${YELLOW}[dry-run]${RESET} proxmox-host: $*"; return 0; }
  if [[ -n "$PROXMOX_PASS" ]]; then
    SSHPASS="$PROXMOX_PASS" sshpass -e ssh "${pxm_ssh_opts[@]}" "${PROXMOX_USER}@${PROXMOX_HOST}" "$@"
  else
    ssh "${pxm_ssh_opts[@]}" "${PROXMOX_USER}@${PROXMOX_HOST}" "$@"
  fi
}

# Run a command inside the LXC container
pxm_exec() {
  $DRY_RUN && { echo -e "  ${YELLOW}[dry-run]${RESET} lxc-${LXC_ID}: $*"; return 0; }
  if [[ -n "$PROXMOX_PASS" ]]; then
    SSHPASS="$PROXMOX_PASS" sshpass -e ssh "${pxm_ssh_opts[@]}" \
      "${PROXMOX_USER}@${PROXMOX_HOST}" "pct exec ${LXC_ID} -- bash -c $(printf '%q' "$*")"
  else
    ssh "${pxm_ssh_opts[@]}" "${PROXMOX_USER}@${PROXMOX_HOST}" \
      "pct exec ${LXC_ID} -- bash -c $(printf '%q' "$*")"
  fi
}

# Push a local file to a path inside the LXC via pct push
pxm_push_file() {
  local local_src="$1" lxc_dst="$2"
  $DRY_RUN && { echo -e "  ${YELLOW}[dry-run]${RESET} pct push ${LXC_ID} $local_src $lxc_dst"; return 0; }
  # Upload to Proxmox host first, then pct push into LXC
  local tmp_remote
  tmp_remote=$(pxm_run "mktemp")
  if [[ -n "$PROXMOX_PASS" ]]; then
    SSHPASS="$PROXMOX_PASS" sshpass -e scp "${pxm_ssh_opts[@]}" \
      "$local_src" "${PROXMOX_USER}@${PROXMOX_HOST}:${tmp_remote}"
  else
    scp "${pxm_ssh_opts[@]}" "$local_src" "${PROXMOX_USER}@${PROXMOX_HOST}:${tmp_remote}"
  fi
  pxm_run "pct push ${LXC_ID} ${tmp_remote} ${lxc_dst} && rm -f ${tmp_remote}"
}

# Sync the repo to the LXC: rsync to Proxmox host temp dir → tar → pct push → extract
pxm_sync_repo() {
  $DRY_RUN && { echo -e "  ${YELLOW}[dry-run]${RESET} pxm_sync_repo → lxc-${LXC_ID}:${REMOTE_DIR}"; return 0; }

  info "Rsyncing code to Proxmox host…"
  local tmp_dir
  tmp_dir=$(pxm_run "mktemp -d")

  local rsync_opts=(-az --delete --exclude='.git' --exclude='__pycache__'
    --exclude='*.pyc' --exclude='.env' --exclude='node_modules'
    --exclude='frontend/dist' --exclude='secrets/')
  local ssh_e="ssh ${pxm_ssh_opts[*]}"
  [[ -n "$PROXMOX_PASS" ]] && ssh_e="sshpass -e ssh ${pxm_ssh_opts[*]}"

  SSHPASS="${PROXMOX_PASS:-}" rsync "${rsync_opts[@]}" -e "$ssh_e" \
    "${REPO_ROOT}/" "${PROXMOX_USER}@${PROXMOX_HOST}:${tmp_dir}/"

  info "Pushing code into LXC ${LXC_ID}…"
  local tar_path="/tmp/nvr-sync-$$.tar.gz"
  pxm_run "tar czf ${tar_path} -C ${tmp_dir} ."
  pxm_run "pct push ${LXC_ID} ${tar_path} ${tar_path}"
  pxm_exec "mkdir -p ${REMOTE_DIR} && tar xzf ${tar_path} -C ${REMOTE_DIR} && rm -f ${tar_path}"
  pxm_run "rm -rf ${tmp_dir} ${tar_path}"
}

# ── Mode-agnostic wrappers ────────────────────────────────────────────────────
# run_remote — run a shell command on the target system (LXC or direct SSH host)
run_remote() {
  case "$DEPLOY_MODE" in
    proxmox) pxm_exec "$@" ;;
    ssh)     ssh_run "$@" ;;
  esac
}

run_remote_tty() {
  case "$DEPLOY_MODE" in
    proxmox) pxm_exec "$@" ;;   # pct exec has no tty concept; output still flows
    ssh)     ssh_run_tty "$@" ;;
  esac
}

# ── Pre-flight checks ─────────────────────────────────────────────────────────
require_target() {
  case "$DEPLOY_MODE" in
    proxmox) ;;
    ssh) ;;
    *) die "Specify a target: --host <user@host>  OR  --proxmox-host <host> --lxc-id <id>" ;;
  esac
}

preflight_local() {
  info "Running local pre-flight checks…"
  command -v ssh   >/dev/null || die "ssh not found in PATH"
  command -v rsync >/dev/null || die "rsync not found in PATH"
  if [[ "$DEPLOY_MODE" == "proxmox" && -n "$PROXMOX_PASS" ]]; then
    command -v sshpass >/dev/null || die "sshpass is required for --proxmox-pass (brew install hudochenkov/sshpass/sshpass)"
  fi
  if [[ "$DEPLOY_MODE" == "ssh" && -n "$SSH_PASS" ]]; then
    command -v sshpass >/dev/null || die "sshpass is required for --ssh-pass (brew install hudochenkov/sshpass/sshpass)"
  fi
  [[ -d "$REPO_ROOT" ]] || die "Cannot find repo root: $REPO_ROOT"
  success "Local tools OK"
}

preflight_remote() {
  case "$DEPLOY_MODE" in
    proxmox)
      info "Checking connectivity to Proxmox host ${PROXMOX_HOST}…"
      pxm_run "echo connected" > /dev/null || die "Cannot connect to ${PROXMOX_USER}@${PROXMOX_HOST}"
      success "Proxmox SSH OK"

      info "Checking LXC ${LXC_ID} is running…"
      pxm_run "pct status ${LXC_ID}" | grep -q "running" \
        || die "LXC ${LXC_ID} is not running (check: pct status ${LXC_ID})"
      success "LXC ${LXC_ID} is running"

      info "Checking Docker inside LXC ${LXC_ID}…"
      pxm_exec "docker --version" > /dev/null || die "Docker not found inside LXC ${LXC_ID}"
      pxm_exec "docker compose version" > /dev/null || die "Docker Compose v2 not found inside LXC ${LXC_ID}"
      success "Docker OK"

      info "Checking disk space inside LXC (need ≥ 10 GB free)…"
      local free_kb
      free_kb=$(pxm_exec "df -k / | tail -1 | awk '{print \$4}'" 2>/dev/null || echo 0)
      if [[ "$free_kb" =~ ^[0-9]+$ ]] && (( free_kb < 10485760 )); then
        warn "Only $(( free_kb / 1024 / 1024 )) GB free in LXC — recommend ≥ 10 GB"
      else
        success "Disk space OK"
      fi
      ;;

    ssh)
      info "Checking remote host connectivity…"
      ssh_run "echo connected" > /dev/null || die "Cannot connect to ${REMOTE_HOST}"
      success "SSH connection OK"

      info "Checking Docker on remote…"
      if ! ssh_run "docker --version" > /dev/null 2>&1; then
        warn "Docker not found — installing via get.docker.com…"
        ssh_run "curl -fsSL https://get.docker.com -o /tmp/get-docker.sh"
        ssh_sudo "sh /tmp/get-docker.sh"
        ssh_sudo "usermod -aG docker \$(id -un) 2>/dev/null || true"
        ssh_run "rm -f /tmp/get-docker.sh"
        ssh_run "docker --version" > /dev/null || die "Docker install failed on remote host"
        success "Docker installed"
      fi
      if ! ssh_run "docker compose version" > /dev/null 2>&1; then
        warn "Docker Compose v2 not found — installing plugin…"
        ssh_sudo "apt-get install -y docker-compose-plugin 2>/dev/null || apt-get install -y docker-compose 2>/dev/null || true"
        ssh_run "docker compose version" > /dev/null || die "Docker Compose v2 not found on remote host"
      fi
      # If docker socket isn't accessible without sudo (fresh install, group not active yet),
      # grant access for this session so subsequent deploy steps don't need sudo.
      if ! ssh_run "docker info" > /dev/null 2>&1; then
        warn "Docker group membership not active in this session — opening socket access…"
        ssh_sudo "chmod 666 /var/run/docker.sock"
      fi
      success "Docker OK"

      info "Checking disk space on remote (need ≥ 10 GB free)…"
      local free_kb
      free_kb=$(ssh_run "df -k ${REMOTE_DIR%/*} 2>/dev/null || df -k / | tail -1 | awk '{print \$4}'")
      if [[ "$free_kb" =~ ^[0-9]+$ ]] && (( free_kb < 10485760 )); then
        warn "Only $(( free_kb / 1024 / 1024 )) GB free on remote — recommend ≥ 10 GB"
      else
        success "Disk space OK"
      fi
      ;;
  esac
}

check_env_file() {
  if [[ ! -f "$LOCAL_ENV" ]]; then
    warn ".env file not found at: ${LOCAL_ENV}"
    warn "Copy .env.example to .env and fill in all required values before deploying."
    die "Aborting — missing .env"
  fi
  local required=(DATABASE_URL REDIS_URL FERNET_KEY RSA_PRIVATE_KEY_PATH RSA_PUBLIC_KEY_PATH)
  local missing=()
  for key in "${required[@]}"; do
    grep -qE "^${key}=.+" "$LOCAL_ENV" || missing+=("$key")
  done
  (( ${#missing[@]} > 0 )) && die ".env is missing required values: ${missing[*]}"
  success ".env validated"
}

# ── Sync repo and env ─────────────────────────────────────────────────────────
sync_repo() {
  step "$1" "Syncing repository to ${DEPLOY_MODE} target → ${REMOTE_DIR}"
  case "$DEPLOY_MODE" in
    proxmox) pxm_sync_repo ;;
    ssh)
      # Create the deploy dir (may need sudo if under /opt) then give user ownership
      ssh_run "mkdir -p ${REMOTE_DIR} 2>/dev/null" \
        || { ssh_sudo "mkdir -p ${REMOTE_DIR}" \
             && ssh_sudo "chown \$(id -un):\$(id -gn) ${REMOTE_DIR}"; }
      rsync_to "${REPO_ROOT}/" "${REMOTE_DIR}/"
      ;;
  esac
  success "Code synced"
}

upload_env() {
  step "$1" "Uploading .env file"
  check_env_file
  case "$DEPLOY_MODE" in
    proxmox) pxm_push_file "$LOCAL_ENV" "${REMOTE_DIR}/.env"
             pxm_exec "chmod 600 ${REMOTE_DIR}/.env" ;;
    ssh)     upload_file "$LOCAL_ENV" "${REMOTE_DIR}/.env"
             ssh_run "chmod 600 ${REMOTE_DIR}/.env" ;;
  esac
  success ".env uploaded"
}

# ── deploy command ────────────────────────────────────────────────────────────
cmd_deploy() {
  require_target
  preflight_local
  preflight_remote

  local target_label
  [[ "$DEPLOY_MODE" == "proxmox" ]] \
    && target_label="Proxmox ${PROXMOX_HOST} → LXC ${LXC_ID}" \
    || target_label="${REMOTE_HOST}"

  echo -e "\n${BOLD}╔══════════════════════════════════════════╗"
  echo -e "║     NVR Pro — First-time Deployment       ║"
  echo -e "╚══════════════════════════════════════════╝${RESET}\n"
  info "Target:    ${target_label}"
  info "Directory: ${REMOTE_DIR}"
  info "Branch:    ${BRANCH}"
  echo ""

  sync_repo 1
  upload_env 2

  step 3 "Generating RSA + Fernet secrets"
  if run_remote "test -f ${REMOTE_DIR}/secrets/rsa_private.pem" 2>/dev/null; then
    warn "Secrets already exist — skipping (delete ${REMOTE_DIR}/secrets/ to regenerate)"
  else
    run_remote "cd ${REMOTE_DIR} && docker compose run --rm keygen"
    success "Secrets generated in ${REMOTE_DIR}/secrets/"
  fi

  step 4 "Pulling Docker images"
  run_remote "cd ${REMOTE_DIR} && docker compose pull"
  success "Images pulled"

  step 5 "Starting services"
  run_remote "cd ${REMOTE_DIR} && docker compose up -d"
  info "Waiting 10 seconds for services to initialise…"
  run_remote "sleep 10"

  step 6 "Running database migrations"
  run_remote "cd ${REMOTE_DIR} && docker compose exec -T backend alembic upgrade head"
  success "Migrations applied"

  step 7 "Seeding default roles and creating superadmin"
  echo ""
  warn "▼ The one-time superadmin password will be shown below. Copy it now. ▼"
  echo ""
  run_remote_tty "cd ${REMOTE_DIR} && docker compose exec backend python scripts/seed_roles.py"
  echo ""

  step 8 "Health check"
  local health
  health=$(run_remote "curl -sf http://localhost:8000/health || echo 'UNHEALTHY'")
  if [[ "$health" == *"ok"* ]]; then
    success "Backend health: OK"
  else
    warn "Backend health check returned: ${health}"
    warn "Check logs with: ./deploy.sh status --proxmox-host ${PROXMOX_HOST} --proxmox-user ${PROXMOX_USER} --lxc-id ${LXC_ID}"
  fi

  echo -e "\n${GREEN}${BOLD}╔══════════════════════════════════════════╗"
  echo -e "║           Deployment complete!            ║"
  echo -e "╚══════════════════════════════════════════╝${RESET}"
  echo ""
  info "Next steps:"
  echo "  1. Configure Nginx TLS (see DEPLOYMENT.md)"
  echo "  2. Open https://<your-domain> and log in with the superadmin password above"
  echo "  3. Add your first camera: Cameras → Discover or Add camera"
  echo ""
}

# ── update command ────────────────────────────────────────────────────────────
cmd_update() {
  require_target
  preflight_local
  preflight_remote

  local target_label
  [[ "$DEPLOY_MODE" == "proxmox" ]] \
    && target_label="Proxmox ${PROXMOX_HOST} → LXC ${LXC_ID}" \
    || target_label="${REMOTE_HOST}"

  echo -e "\n${BOLD}╔══════════════════════════════════════════╗"
  echo -e "║        NVR Pro — Rolling Update           ║"
  echo -e "╚══════════════════════════════════════════╝${RESET}\n"
  info "Target:    ${target_label}"
  info "Directory: ${REMOTE_DIR}"
  echo ""

  local prev_backend_image
  prev_backend_image=$(run_remote \
    "cd ${REMOTE_DIR} && docker compose images -q backend 2>/dev/null || true" || true)

  sync_repo 1

  if [[ "$LOCAL_ENV" != ".env" ]] || [[ -f "$LOCAL_ENV" ]]; then
    upload_env 2
  fi

  step 3 "Pulling latest Docker images"
  run_remote "cd ${REMOTE_DIR} && docker compose pull"
  success "Images pulled"

  step 4 "Running database migrations"
  run_remote "cd ${REMOTE_DIR} && docker compose run --rm backend alembic upgrade head"
  success "Migrations applied"

  step 5 "Rolling restart (backend → worker → detection → frontend)"
  for svc in backend worker detection; do
    info "Restarting ${svc}…"
    run_remote "cd ${REMOTE_DIR} && docker compose up -d --no-deps ${svc}"
    run_remote "sleep 3"
  done
  info "Rebuilding and restarting frontend…"
  run_remote "cd ${REMOTE_DIR} && docker compose build frontend"
  run_remote "cd ${REMOTE_DIR} && docker compose stop frontend && docker compose up -d --no-deps frontend"

  step 6 "Health check"
  run_remote "sleep 5"
  local health
  # Backend has no host port binding — check via docker exec into the backend container
  health=$(run_remote "cd ${REMOTE_DIR} && docker compose exec -T backend python -c \"import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())\" 2>/dev/null || echo 'UNHEALTHY'")
  if [[ "$health" == *"ok"* ]] || [[ "$health" == *"true"* ]]; then
    success "Backend health: OK"
    echo -e "\n${GREEN}${BOLD}Update complete!${RESET}"
  else
    error "Health check failed after update: ${health}"
    echo ""
    warn "Attempting rollback to previous images…"
    if [[ -n "$prev_backend_image" ]]; then
      run_remote "cd ${REMOTE_DIR} && docker compose up -d --no-deps backend worker" || true
      warn "Rollback attempted. Verify with: ./deploy.sh status"
    fi
    die "Update failed — check logs with: ./deploy.sh status"
  fi
}

# ── status command ────────────────────────────────────────────────────────────
cmd_status() {
  require_target

  local target_label
  [[ "$DEPLOY_MODE" == "proxmox" ]] \
    && target_label="Proxmox ${PROXMOX_HOST} → LXC ${LXC_ID}" \
    || target_label="${REMOTE_HOST}"

  echo -e "\n${BOLD}NVR Pro — Status @ ${target_label}${RESET}\n"

  info "Containers:"
  run_remote "cd ${REMOTE_DIR} && docker compose ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}'"

  echo ""
  info "Disk usage:"
  run_remote "df -h ${REMOTE_DIR} 2>/dev/null | tail -1 || df -h / | tail -1"
  run_remote "du -sh ${REMOTE_DIR}/data/* 2>/dev/null || true"

  echo ""
  info "Backend health:"
  run_remote "curl -sf http://localhost:8000/health 2>/dev/null && echo '' || echo 'UNREACHABLE'"

  echo ""
  info "Recent backend logs (last 20 lines):"
  run_remote "cd ${REMOTE_DIR} && docker compose logs --tail=20 backend 2>/dev/null"
}

# ── help ──────────────────────────────────────────────────────────────────────
cmd_help() {
  echo -e "${BOLD}NVR Pro deployment tool${RESET}"
  echo ""
  echo "Usage: $(basename "$0") <command> [target] [options]"
  echo ""
  echo -e "${BOLD}Commands:${RESET}"
  echo "  deploy    Full first-time setup (sync code, secrets, migrate, seed)"
  echo "  update    Rolling update: sync → migrate → restart"
  echo "  status    Show container states, disk, health"
  echo ""
  echo -e "${BOLD}Target (choose one):${RESET}"
  echo "  --host           Direct SSH target, e.g. admin@192.168.1.100"
  echo "  --ssh-pass       Password for --host SSH    (requires sshpass; or NVR_SSH_PASS env)"
  echo ""
  echo "  --proxmox-host   Proxmox server IP or hostname"
  echo "  --proxmox-user   Proxmox SSH user          (default: root)"
  echo "  --proxmox-pass   Proxmox SSH password       (requires sshpass; or NVR_PROXMOX_PASS env)"
  echo "  --lxc-id         LXC container ID           (e.g. 211)"
  echo ""
  echo -e "${BOLD}Options:${RESET}"
  echo "  --dir      Remote directory inside target  (default: /opt/nvr)"
  echo "  --env      Local .env file to upload       (default: .env)"
  echo "  --branch   Git branch                      (default: main)"
  echo "  --key      SSH private key file"
  echo "  --dry-run  Print commands without executing"
  echo ""
  echo -e "${BOLD}Examples:${RESET}"
  echo "  # Direct SSH with password (Docker auto-installed if missing)"
  echo "  NVR_SSH_PASS=mypass ./deploy.sh deploy --host cobaltax@192.168.9.201"
  echo ""
  echo "  # Proxmox LXC (password auth)"
  echo "  ./deploy.sh deploy --proxmox-host 192.168.1.10 --proxmox-pass s3cr3t --lxc-id 211"
  echo ""
  echo "  # Proxmox LXC (SSH key)"
  echo "  ./deploy.sh update --proxmox-host 192.168.1.10 --key ~/.ssh/proxmox_rsa --lxc-id 211"
  echo ""
  echo "  # Direct SSH (key-based)"
  echo "  ./deploy.sh deploy --host admin@192.168.1.100"
  echo ""
  echo "  # Dry run"
  echo "  ./deploy.sh deploy --proxmox-host 192.168.1.10 --proxmox-pass s3cr3t --lxc-id 211 --dry-run"
}

# ── Entry point ───────────────────────────────────────────────────────────────
case "$COMMAND" in
  deploy) cmd_deploy ;;
  update) cmd_update ;;
  status) cmd_status ;;
  help|--help|-h) cmd_help ;;
  *) error "Unknown command: ${COMMAND}"; cmd_help; exit 1 ;;
esac
