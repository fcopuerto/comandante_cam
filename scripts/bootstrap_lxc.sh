#!/usr/bin/env bash
# Run inside the LXC container as root.
# Installs Docker, clones the project, and starts all services.
#
# Usage (from Proxmox host):
#   pct push <CTID> scripts/bootstrap_lxc.sh /root/bootstrap_lxc.sh
#   pct exec <CTID> -- bash /root/bootstrap_lxc.sh

set -euo pipefail

PROJECT_DIR="/opt/nvr-pro"
DATA_DIR="/data"

echo "==> Updating system"
apt-get update -qq
apt-get upgrade -y -qq

echo "==> Installing dependencies"
apt-get install -y -qq \
  ca-certificates curl gnupg git python3 python3-pip \
  ffmpeg libgl1 lsb-release

echo "==> Installing Docker"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable --now docker

echo "==> Creating data directories"
mkdir -p \
  "$DATA_DIR/recordings" \
  "$DATA_DIR/hls" \
  "$DATA_DIR/exports" \
  "$DATA_DIR/alerts" \
  "$DATA_DIR/models"

echo "==> Copying project files"
# If you have the project on your local machine, rsync it:
#   rsync -avz --exclude '.git' --exclude '__pycache__' \
#     /path/to/comandante_cam/ root@<LXC_IP>:/opt/nvr-pro/
# For now we assume files are already in /opt/nvr-pro (see note below)
mkdir -p "$PROJECT_DIR"

echo ""
echo "================================================================"
echo "Bootstrap complete. Next steps:"
echo ""
echo "1. Copy project files to the LXC if not already there:"
echo "   rsync -avz /path/to/comandante_cam/ root@<LXC_IP>:${PROJECT_DIR}/"
echo ""
echo "2. SSH into the LXC:"
echo "   ssh root@<LXC_IP>"
echo ""
echo "3. Generate secrets:"
echo "   cd ${PROJECT_DIR}"
echo "   pip3 install cryptography"
echo "   python3 scripts/generate_keys.py"
echo ""
echo "4. Configure environment:"
echo "   cp .env.example .env"
echo "   nano .env   # fill in FERNET_KEY, SECRET_KEY (from step 3)"
echo "               # set COOKIE_SECURE=false for local dev"
echo "               # set CORS_ORIGINS=http://<LXC_IP>"
echo "               # set ALLOWED_HOSTS=<LXC_IP>,localhost"
echo ""
echo "5. Start services:"
echo "   docker compose up -d"
echo "   docker compose logs -f"
echo ""
echo "6. Run migrations + seed:"
echo "   docker compose exec backend alembic upgrade head"
echo "   docker compose exec backend python scripts/seed_roles.py"
echo ""
echo "7. Run tests:"
echo "   docker compose exec backend pytest tests/ -v"
echo "================================================================"
