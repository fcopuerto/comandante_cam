---
name: Equipment Inventory Addon
description: New addon/plugin for NVR Pro — inventory of cameras + Raspberry Pi display nodes with in-browser SSH terminal
type: project
---

Addon to add to NVR Pro for inventorying all equipment in an NVR installation.

**Why:** The NVR serves TVs via Raspberry Pi display nodes. User needs to manage all these devices (cameras + Pis) in one place and SSH into them directly from the browser.

**Design decisions:**
- Addon system: enabled/disabled via settings; when enabled appears as top-level nav item "Inventory"
- Device types: camera (linked to existing camera records), raspberry_pi, display, other
- SSH terminal: xterm.js frontend + asyncssh backend WebSocket proxy at `/ws/terminal/{equipment_id}`
- SSH auth: SSH key path (configured per device or global default) + optional Fernet-encrypted password fallback
- Equipment stored in its own `equipment` table (separate from NVR cameras table)

**How to apply:** When implementing, follow the locked tech stack in CLAUDE.md. Use asyncssh for SSH proxy. Use Fernet for storing SSH passwords.
