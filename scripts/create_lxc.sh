#!/usr/bin/env bash
# Run this on the Proxmox HOST (not inside a container).
# Creates an Ubuntu 22.04 LXC with Docker-compatible settings.
#
# Usage: bash scripts/create_lxc.sh
# Adjust the variables below to match your Proxmox setup.

set -euo pipefail

CTID=200                   # Container ID — change if 200 is taken
HOSTNAME="nvr-pro"
STORAGE="local-lvm"        # Storage pool for the container rootfs
BRIDGE="vmbr0"             # Network bridge
IP="192.168.1.200/24"      # Static IP for the container
GATEWAY="192.168.1.1"
DISK_GB=40                 # Rootfs size (recordings will be on a bind mount)
RAM_MB=4096                # 4 GB minimum (YOLOv8 needs headroom)
CORES=4
TEMPLATE="local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst"

# Download template if not already present
pveam update
pveam download local ubuntu-22.04-standard_22.04-1_amd64.tar.zst 2>/dev/null || true

pct create "$CTID" "$TEMPLATE" \
  --hostname "$HOSTNAME" \
  --storage "$STORAGE" \
  --rootfs "${STORAGE}:${DISK_GB}" \
  --memory "$RAM_MB" \
  --cores "$CORES" \
  --net0 "name=eth0,bridge=${BRIDGE},ip=${IP},gw=${GATEWAY}" \
  --unprivileged 0 \
  --features "nesting=1,keyctl=1" \
  --onboot 1

# Allow TUN (needed for VPN camera access later)
echo "lxc.cgroup2.devices.allow = c 10:200 rwm" >> /etc/pve/lxc/${CTID}.conf
echo "lxc.mount.entry = /dev/net dev/net none bind,create=dir"  >> /etc/pve/lxc/${CTID}.conf

pct start "$CTID"
sleep 5

echo ""
echo "LXC $CTID ($HOSTNAME) started at $IP"
echo "Next: pct exec $CTID -- bash -c 'curl -fsSL https://raw.githubusercontent.com/... | bash'"
echo "Or:   copy bootstrap_lxc.sh into the container and run it."
echo ""
echo "Quick copy:"
echo "  pct push $CTID scripts/bootstrap_lxc.sh /root/bootstrap_lxc.sh"
echo "  pct exec $CTID -- bash /root/bootstrap_lxc.sh"
