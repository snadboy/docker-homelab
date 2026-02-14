# Ansible Controller + Semaphore - Session Notes

## Overview

Rebuilt ansible-controller VM (ID 200) on guardian from scratch and deployed Semaphore UI for Ansible automation. Created apt-update playbook with biweekly schedule covering all homelab hosts. Full playbook run verified — 14/14 hosts successful.

**Status:** ✅ Complete - 2026-02-10

---

## ansible-controller VM

| Property | Value |
|----------|-------|
| VMID | 200 |
| Node | guardian |
| Profile | small (2 cores, 2GB RAM, 20GB disk) |
| OS | Ubuntu 24.04.4 LTS (kernel 6.8.0-100) |
| LAN IP | 192.168.86.203 |
| Tailscale IP | 100.114.25.16 |
| Tailscale Tags | tag:ansible, tag:docker |
| SSH | snadboy@192.168.86.203 |
| Mounts | /mnt/shareables (CIFS) |

### Installed Software
- qemu-guest-agent
- Docker (with docker compose)
- Tailscale (SSH enabled)

---

## Semaphore UI

| Property | Value |
|----------|-------|
| URL | https://semaphore.isnadboy.com |
| Direct | http://192.168.86.203:3000 |
| Container | semaphore (semaphoreui/semaphore:latest) |
| DB | BoltDB (/var/lib/semaphore/database.boltdb) |
| Volume | semaphore-data (external) |
| Login | admin / changeme123 |
| Version | v2.16.51 |

### Semaphore Configuration
- **Project:** homelab (ID: 1)
- **SSH Key:** snadboy-ssh (ID: 2) — snadboy@devs ed25519 key
- **Repository:** docker-homelab (ID: 1) — https://github.com/snadboy/docker-homelab.git (main)
- **Inventory:** homelab-hosts (ID: 1) — ansible/inventory/hosts.yml (file type)
- **Template:** apt-update (ID: 2) — ansible/playbooks/apt-update.yml
- **Schedule:** Biweekly apt update (ID: 1) — `0 4 */14 * *` (active)

---

## Ansible Inventory

### Host Groups
| Group | Hosts | SSH User |
|-------|-------|----------|
| pve_nodes | pve-colossus, pve-guardian, pve-multivac (Tailscale FQDNs) | root |
| pbs_servers | host-svalbard, host-alexandria | root |
| ubuntu_vms | arr, cadre, plex, iot, utilities | snadboy |
| managed_locally | ansible-controller (excluded from apt_hosts) | snadboy |
| debian_containers | host-ns | root |
| lxc_containers | ns-secundus (CT 108), ns-tertius (CT 112), pve-scripts-local (CT 104) | via pct exec |
| apt_hosts | pve_nodes + pbs_servers + ubuntu_vms + debian_containers | (varies) |

### apt-update Playbook
- SSH hosts: `apt update && apt dist-upgrade` with autoremove/autoclean, 50% serial
- LXC containers: delegated to parent PVE node via `pct exec`, serial 1
- Reports reboot-required status
- **Verified:** 14/14 hosts pass (11 SSH + 3 LXC)

---

## Traefik Routing

Added `ansible-controller` to sb-traefik-http-provider SSH hosts:
- SSH host key: `ansible-controller` (Tailscale SSH)
- Backend hostname: `host-ansible-controller.isnadboy.com` (A record in Technitium → 192.168.86.203)
- Route: `semaphore-3000: https://semaphore.isnadboy.com -> http://192.168.86.203:3000/`

---

## Issues Fixed During Testing

### cadre SSH drops during apt upgrade
- **Problem:** SSH connections dropped during long-running apt dist-upgrade on cadre
- **Root cause:** cadre had no openssh-server — all SSH was via Tailscale SSH, which dropped during long operations
- **Fix:** Installed openssh-server on cadre, authorized snadboy@devs key in `~/.ssh/authorized_keys`. Ansible now connects via regular sshd on LAN IP (192.168.86.22) with `ServerAliveInterval=30` keepalive from ansible.cfg.

### ns-tertius DNS resolution failure
- **Problem:** `pct exec` apt update failed with "Temporary failure resolving 'archive.ubuntu.com'" inside CT 112
- **Root cause:** Tailscale inside ns-tertius had `--accept-dns=false` (`CorpDNS: false`). The container's resolv.conf pointed to 100.100.100.100 (MagicDNS, inherited from PVE host), but the container's tailscaled wasn't handling DNS queries — returning SERVFAIL.
- **Fix:** `tailscale set --accept-dns` inside ns-tertius. Now MagicDNS properly forwards public DNS queries via split DNS. (ns-secundus already had accept-dns enabled, which is why it worked.)

### Other fixes applied during earlier testing
- PVE node hostnames changed to Tailscale FQDNs (`pve-X.tail65635.ts.net`)
- ansible-controller moved to `managed_locally` group (no sudo in Semaphore container)
- Added NOPASSWD sudoers for snadboy on cadre
- Authorized snadboy@devs SSH key on host-ns (CT 103) via `pct exec`
- Added SSH keepalive (`ServerAliveInterval=30`, `ServerAliveCountMax=10`) and pipelining to ansible.cfg

---

## Files Created/Modified

- `docker-homelab/semaphore/docker-compose.yml` (new)
- `docker-homelab/semaphore/.env.example` (new)
- `docker-homelab/hawser-ansible/docker-compose.yml` (new)
- `docker-homelab/ansible/inventory/hosts.yml` (new)
- `docker-homelab/ansible/playbooks/apt-update.yml` (new)
- `docker-homelab/ansible/ansible.cfg` (new)

## Commits
- `f6e54cd` — Add Semaphore, hawser-ansible, and Ansible playbooks for ansible-controller
- `7aee190` — Fix PVE node hostnames to use Tailscale FQDNs in Ansible inventory
- `b4dca26` — Add SSH keepalive and pipelining to ansible.cfg
- `06588f5` — Move ansible-controller to managed_locally group, exclude from apt_hosts

---

## Dockhand Integration

| Property | Value |
|----------|-------|
| Environment | ansible-controller (ID: 9) |
| Hawser Agent | ghcr.io/finsys/hawser:latest v0.2.27 |
| Git Stacks | semaphore (ID: 11), hawser-ansible (ID: 12) |
| Auto-update | Daily @ 03:00, webhook enabled |
| Sync Status | Synced (commit 06588f5) |

## Unattended Upgrades

Configured with auto-reboot at 04:00 (`/etc/apt/apt.conf.d/52unattended-upgrades-local`), matching other Ubuntu hosts.

---

## Homelab Version Audit & Updates (2026-02-10)

**Status:** ✅ Complete

Audited all key services across the homelab for version currency and updated what was out of date.

### Updates Performed

| Service | Host(s) | Old Version | New Version | Method |
|---------|---------|-------------|-------------|--------|
| **Traefik** | cadre | v3.2.5 | v3.6.7 | Updated image tag in compose, pushed to git, redeployed |
| **Technitium DNS** | ns | v14.0 (Nov 22) | v14.3 (Dec 20) | `install.sh` update script |
| **Technitium DNS** | ns-secundus | v14.0 (Nov 22) | v14.3 (Dec 20) | `install.sh` update script |

### Already Current

| Service | Version | Hosts |
|---------|---------|-------|
| Proxmox VE | 9.1.5 | colossus, guardian, multivac |
| Tailscale | 1.94.1 | All 12 hosts (auto-update) |
| Sonarr | 4.0.16.2944 | arr |
| Radarr | 6.0.4.10291 | arr |
| Prowlarr | 2.3.0.5236 | arr |
| Overseerr | v1.34.0 | arr |
| SABnzbd | 4.5.5 | arr |
| Tautulli | v2.16.0 | arr |
| Zigbee2MQTT | 2.8.0 | cadre |
| Plex | 1.42.2 (latest stable) | plex |

### Notes
- **Technitium ns-tertius** (CT 112) was already on v14.3 — no update needed
- **Plex 1.43.0** exists but was pulled back by linuxserver due to package signing issues; 1.42.2 remains the latest stable `latest` tag
- **Traefik v3.6.7** includes CVE-2025-66490 fix; no breaking changes for our HTTP provider + ACME/Cloudflare config
- **devs** VM no longer in use — disabled in HTTP provider `ssh-hosts.yaml` to eliminate 30s SSH timeout on every config generation

### Files Changed
- `docker-homelab/traefik-http-provider/docker-compose.yml` — Traefik image tag `v3.2` → `v3.6`
- HTTP provider `ssh-hosts.yaml` (volume config on cadre) — `devs` set to `enabled: false`

### Commits
- `eb057b4` — Update Traefik from v3.2 to v3.6
- `a50ca7a` — Update session notes: disable devs in HTTP provider

---

## Weekly Version Audit Workflow (2026-02-10)

**Status:** ✅ Complete

Automated weekly version audit replaces manual checks and the old Pending Updates Monitor.

| Property | Value |
|----------|-------|
| Workflow ID | BXBsZXozpqxLZyoa |
| Schedule | Sunday 9 AM (`0 9 * * 0`) |
| Nodes | 17 (7 APT SSH + 4 Docker SSH + 1 Code API + Merge + Format + Discord) |
| Replaced | Pending Updates Monitor (`mc4XV3qJ1FWNKVJO`, deactivated) |

### What It Checks
- **Docker containers** (10): sonarr, radarr, prowlarr, overseerr, sabnzbd, tautulli, plex, traefik, zigbee2mqtt, n8n
- **Running vs latest**: Compares `org.opencontainers.image.version` label against GitHub releases API
- **Zigbee2mqtt**: Uses `docker exec` to read `/app/package.json` (no OCI labels)
- **PVE version**: From `/api2/json/version` (PVEAuditor token)
- **Technitium DNS version**: From `/api/settings/get` API
- **APT updates**: 7 SSH hosts (plex, arr, cadre, ns, utilities, iot, ha)

### Discord Output
Two embeds per message:
1. **Software Versions** (green/yellow) — Docker container versions + PVE + Technitium
2. **System Updates** (green/yellow) — APT pending counts per host

### New n8n Environment Variables
- `TECHNITIUM_URL=http://192.168.86.76:5380`
- `TECHNITIUM_TOKEN=<api-token>`

### Notes
- PVE APT updates not checked (requires `Sys.Modify`, token only has `PVEAuditor`)
- PVE nodes managed by biweekly Ansible apt-update playbook instead
- Container names on cadre: `zigbee2mqtt-office`, `zigbee2mqtt-laundry` (not `zigbee2mqtt`)
- Version normalization strips `-ls\d+` suffix, `v` prefix, Plex build hashes

### Files Changed
- `n8n/workflows/weekly-version-audit.json` (new)
- `n8n/.env.example` (added Technitium placeholders)

### Commit
- `88b8eb9` — Add Weekly Version Audit workflow, replace Pending Updates Monitor

---

## n8n Backup Workflow (2026-02-11)

**Status:** ✅ Complete

Automated daily backup of n8n workflow definitions to GitHub and credential data to shareables.

| Property | Value |
|----------|-------|
| Workflow ID | dVt3Th1wvWvutg0a |
| Schedule | Daily at 3 AM (`0 3 * * *`) |
| Nodes | 5 (Schedule + Globals + SSH + Code + Gotify) |
| GitHub Repo | snadboy/n8n-workflows (private) |
| Credential Backup | /mnt/shareables/BAK/n8n/credentials-YYYY-MM-DD.json |
| Retention | 7 days |

### What It Does
1. **Credential export**: SSH into utilities, queries SQLite on host, decrypts via `docker exec n8n node` using CryptoJS AES (EVP_BytesToKey KDF), writes to shareables mount
2. **Workflow export**: Code node fetches all workflows via n8n API (localhost:5678), pushes each as JSON to GitHub via Contents API
3. **Notification**: Gotify summary with credential count and workflow count

### Globals Credential Updated
Added 2 new constants to "Homelab Constants" (ID: `kt9rQnvdyaBeZlR2`):
- `GITHUB_TOKEN` — GitHub PAT for repo access
- `N8N_API_KEY` — n8n public API key
- Total constants: 30 (was 28)

### Technical Details
- Workflow filenames include workflow ID to prevent name collisions: `{name}--{id}.json`
- SSH credential export uses `cat <<'DECRYPTJS'` heredoc to write Node.js decryption script to temp file, `docker cp` into container, then pipes sqlite3 output through it
- `grep -c '"id"'` counts credentials instead of python3 (avoids nested quoting issues in SSH command)
- n8n API not accessible through Traefik (404), use `http://localhost:5678` from Code node or `http://host-utilities.isnadboy.com:5678` externally
- Gotify URL hardcoded to `http://host-utilities.isnadboy.com:8084` (HTTPS via Traefik returns 404 — pre-existing issue)

### Verification
- Execution 1449: ✅ All 5 nodes passed
  - 14 credentials exported to shareables
  - 28 workflows pushed to GitHub (28 unique files with ID suffixes)
  - Gotify notification received

### Files Changed
- `n8n/workflows/n8n-backup.json` (new)
- Globals credential updated via SQLite (GITHUB_TOKEN, N8N_API_KEY)

---

## Traefik HTTP Provider DNS Fix (2026-02-11)

**Status:** ✅ Complete

Fixed both `homepage.isnadboy.com` returning 404 and unreliable detection of Docker container restarts on remote hosts.

### Root Cause

Docker containers on user-defined networks (`traefik`) don't inherit the host's Tailscale DNS search domain. The `sb-traefik-http-provider` container's `resolv.conf` had `search localdomain` instead of `search tail65635.ts.net`. The `snadboy-ssh-docker` library uses the dict keys from `ssh-hosts.yaml` (e.g., `arr`, `utilities`) directly as SSH hostnames. On the host, these resolve via the Tailscale search domain (`arr` → `arr.tail65635.ts.net`). Inside the container, they couldn't resolve at all.

### Impact Before Fix

- **Container discovery broken** for all remote hosts — only 15 services (4 local + 11 static) instead of 35
- **All event listeners failing** — SSH to remote Docker event streams failed with "Could not resolve hostname"
- **homepage.isnadboy.com 404** — homepage runs on utilities, which wasn't being discovered

### Fix Applied

Added `dns_search: ["tail65635.ts.net"]` to the `sb-traefik-http-provider` service in `docker-compose.yml`. This ensures short Tailscale hostnames resolve inside the container.

### Results After Fix

- 35 services discovered (was 15)
- All 5 event listeners connected (arr, cadre, utilities, iot, ansible-controller)
- homepage.isnadboy.com → HTTP 200
- Zero errors in logs

### Files Changed
- `docker-homelab/traefik-http-provider/docker-compose.yml` — Added `dns_search: ["tail65635.ts.net"]`

### Commit
- `e01ffca` — Add Tailscale DNS search domain to HTTP provider container

---

## Weekly Version Audit — Container & Stack Health Enhancement (2026-02-11)

**Status:** ✅ Complete

Enhanced the Weekly Version Audit workflow to check Docker container health and Dockhand stack sync status across all hosts.

### What Was Added

**Container Health Checks (5 new SSH nodes):**
- SSH into arr, plex, cadre, utilities, iot
- Detects unhealthy containers (`docker ps --format json` + jq filter for `unhealthy` status)
- Detects restarting containers (state == `restarting`)
- Reports containers with >3 restart count (`docker inspect` + jq filter on RestartCount)

**Dockhand Stack Status (1 new SSH node):**
- Queries Dockhand SQLite database via `docker exec dockhand sqlite3`
- Reports stack sync status (synced/deployed/success = OK, anything else = alert)
- Reports failed deployments from `schedule_executions` table (last 7 days)

**New Discord Embed:**
- Third embed: "Container & Stack Health" with whale emoji
- Green when all healthy, red (#E74C3C) when issues detected
- Footer: `N containers | N hosts | N PVE nodes | N stacks`

### Workflow Changes
- Nodes: 17 → 23 (6 new SSH nodes)
- Merge inputs: 12 → 18
- Globals fan-out: 12 → 18 targets
- Discord embeds: 2 → 3

### Verification
- Execution 1535: ✅ All 23 nodes succeeded (~8s)
- Container health: All 5 hosts report healthy
- Dockhand: All 11 stacks synced, 0 failed deployments
- Discord: 3 embeds posted correctly

### Dockhand Status Values
- `synced`, `deployed`, `success` = healthy (green)
- Anything else (e.g., `failed`) = alert (red)

### Files Changed
- `n8n/workflows/weekly-version-audit.json` — 6 new nodes, updated Format Report code

### n8n API Access Note
- n8n API is NOT accessible through Traefik (returns `X-N8N-API-KEY header required`)
- Must use `http://localhost:5678` from utilities host directly (SSH + curl)

---

## n8n Credential-Based Auth Refactor (2026-02-11)

**Status:** ✅ Complete

Refactored n8n workflows to use Header Auth / Query Auth credentials instead of manually injecting API keys from Global Constants.

### Credentials Created (6 new)

| Credential | ID | Type | Header/Param |
|---|---|---|---|
| Sonarr API | `rAV3sUfzg27ok6NT` | httpHeaderAuth | `X-Api-Key` |
| Radarr API | `KYvcjxCLkVwCXJJY` | httpHeaderAuth | `X-Api-Key` |
| Prowlarr API | `tkjLc4mJKRK9mIYd` | httpHeaderAuth | `X-Api-Key` |
| Overseerr API | `O8ka5F82xj3jN41r` | httpHeaderAuth | `X-Api-Key` |
| SABnzbd API | `WUMwDzFtC53aazjW` | httpQueryAuth | `apikey` |
| Gotify API | `hZM2wpBkhJwPJf32` | httpHeaderAuth | `X-Gotify-Key` |

### Arr Stack Health Check — Full Refactor

Replaced single Code node (5 `httpRequest()` calls with manual API keys) with 5 individual HTTP Request nodes using credential-based auth.

**New flow:** Schedule → Globals → 5 HTTP Request nodes (parallel) → Merge (5 inputs, append) → Evaluate Results Code → If → Gotify Alert / All Healthy

- Nodes: 6 → 12
- Each service check independently testable in n8n editor
- API keys stored as encrypted n8n credentials

### Gotify Nodes — 7 Workflows Updated

Replaced manual `X-Gotify-Key` header (from Globals expression) with Gotify API Header Auth credential:
1. daily-media-digest
2. overseerr-request-notifier
3. plex-recently-added
4. n8n-backup
5. trash-pickup-scheduler
6. gmail-labels-and-contacts
7. gmail-cleanup

### Not Refactored (complex Code node patterns)

These workflows use Code nodes with multi-service API orchestration — not practical to replace:
- daily-media-digest (Sonarr/Radarr/SABnzbd/Plex/Overseerr data gathering)
- weekly-version-audit (PVE/Technitium/GitHub APIs)
- n8n-backup (n8n API + GitHub API)
- network-health-monitor (UniFi cookie auth)
- proxmox-health-monitor/daily-summary (PVE composite token)
- Gmail workflows (OAuth token refresh)

### Verification

- Execution 1578: ✅ All 12 nodes passed (~330ms)
  - 5/5 services healthy via credential auth
  - Merge collected all 5 inputs
  - Routed to "All Healthy" (no failures)

### Files Changed
- `n8n/workflows/arr-stack-health-check.json` — Full rewrite (credential-based HTTP Request nodes + Merge)
- `n8n/workflows/daily-media-digest.json` — Gotify credential
- `n8n/workflows/overseerr-request-notifier.json` — Gotify credential
- `n8n/workflows/plex-recently-added.json` — Gotify credential
- `n8n/workflows/n8n-backup.json` — Gotify credential
- `n8n/workflows/trash-pickup-scheduler.json` — Gotify credential
- `n8n/workflows/gmail-labels-and-contacts.json` — Gotify credential
- `n8n/workflows/gmail-cleanup.json` — Gotify credential

---

## Script Server Teardown (2026-02-11)

**Status:** ✅ Complete

Decommissioned the script-server fork — its purpose was eclipsed by n8n (workflow automation) and Semaphore (Ansible automation).

### What Was Removed

| Item | Location | Action |
|------|----------|--------|
| Docker container | utilities | Stopped, removed |
| Named volumes (4) | utilities | `script-server-config`, `-scripts`, `-logs`, `-runners` removed |
| Bind mount data | utilities | `/opt/script-server/` removed |
| Compose definition | utilities | `~/docker-homelab/script-server/` removed |
| Traefik route | cadre (auto) | Auto-removed when container deleted (label-based discovery) |
| HTTP provider desc | cadre | Updated `ssh-hosts.yaml` — removed "script-server" from utilities description |
| GHCR images | ghcr.io | `ghcr.io/snadboy/script-server` deleted (219 versions) |
| GitHub repo | github.com | `snadboy/script-server` deleted (public fork of bugy/script-server) |
| Local project | devs | `/home/snadboy/projects/script-server` removed |
| Claude memory | devs | `~/.claude/projects/-home-snadboy-projects-script-server/` removed |
| DNS | — | No record existed (used wildcard) |

### Not Affected

- **Weekly version audit** — script-server was never in the container version checks; health checks are generic (`docker ps`) and auto-exclude removed containers
- **Dockhand** — stack/container no longer exists, drops out of SQLite queries automatically

---

## Traefik HTTP Provider Skill Enhancement (2026-02-12)

**Status:** ✅ Complete

Enhanced the `traefik-http-provider` Claude Code skill with streamlined config update operations.

### What Changed

Replaced the cumbersome docker-cp round-trip workflow in the Configuration File Management section with direct volume path commands:

- **Quick Reference callout** added near top of skill with restart requirements and volume path
- **Add Static Route** — one-liner heredoc append + auto-restart
- **Add SSH Host** — one-liner heredoc append + auto-restart
- **Disable/Remove Entry** — sed commands for toggling or removing entries
- **Update Description** — sed in-place replacement
- **Restart & Verify** — restart + log check + route verification
- **Full File Replacement** — pull/edit/push for complex edits

Volume path: `/var/lib/docker/volumes/traefik-http-provider-config/_data/` on cadre.

### Files Changed
- `/mnt/shareables/.claude/skills/traefik-http-provider/skill.md` — Expanded config management section (429 → 481 lines)

### Commit
- `525822c` — Enhance traefik-http-provider skill with streamlined config update operations

---

## Status Dashboard Enhancements (2026-02-12/13)

**Status:** ✅ Mostly Complete (NAS stats pending)

Implemented comprehensive status dashboard improvements — frontend redesign and backend data collection enhancements.

### Plan Items Completed

1. **HTTPS cert fix** — Cert was valid (Let's Encrypt R13) but user's browser had cached a stale cert. Resolved after Chrome restart.
2. **WAN section** — Merged speedtest inline, fixed WAN2 display with public IP via `active_geo_info.WAN2.address` (T-Mobile CGNAT)
3. **Devices & WiFi** — Separated AP and Switch dropdown tables with error badges
4. **Cloudflare tunnel uptime** — Backend now parses `status` field from SSH output; frontend shows duration on chips
5. **Services** — Removed chip-grid, kept detail tables only
6. **Overseerr pending requests** — Verified working
7. **cloud-pbs** — Added as PBS server via REST API; fixed `ds.store` vs `ds.name` field mapping
8. **PBS backup times** — Created API tokens on svalbard/alexandria; SSH commands use local REST API with curl
9. **Dropdown error badges** — Red/yellow badges on collapsed dropdowns when errors exist inside

### Not Yet Done
- **NAS storage stats** — UniFi NAS needs SSH enabled; Synology needs SSH key authorized
- **Traefik skill cert verification** — Plan item 11

### Backend Changes (n8n workflow)
- Workflow ID: `FQGdFuIA1sVcR19b`
- Added cloud-pbs Code node (PBS REST API)
- PBS SSH commands rewritten to use local REST API with `PBSAPIToken` auth
- Tunnel SSH parsing includes `status` field
- WAN2 IP uses `gateway.active_geo_info.WAN2.address` (CGNAT fix)
- Merge node bumped to 14 inputs
- Globals updated: `CLOUD_PBS_URL`, `CLOUD_PBS_TOKEN`

### PBS API Tokens Created
- svalbard: `root@pam!status-dashboard` → `/etc/proxmox-backup/status-dashboard-token.txt`
- alexandria: `root@pam!status-dashboard` → `/etc/proxmox-backup/status-dashboard-token.txt`
- ACL: `acl:1:/:root@pam!status-dashboard:Admin` in `/etc/proxmox-backup/acl.cfg`

### Commits
- `9cbdd93` — Status dashboard enhancements (main changes)
- `d7bd311` — Fix WAN2 public IP for CGNAT connections

---

## Chrome Extension Fix (2026-02-13)

**Status:** ✅ Infrastructure Fixed (needs session restart)

### Problem
Chrome browser automation tools (`mcp__claude-in-chrome__*`) not connecting on sdevs.

### Root Cause
1. Extension service worker went dormant and stopped spawning native host
2. After extension reinstall, native host works but MCP server (running 14+ hours) had stale state
3. MCP server (`--claude-in-chrome-mcp`) died after SIGHUP attempt

### What Was Fixed
- Removed duplicate npm global installation (`/usr/bin/claude` → removed via `sudo npm -g uninstall @anthropic-ai/claude-code`)
- User reinstalled Chrome extension (same ID `fcoeoabgfenejglbffodgkkbkcdhcgfn`, v1.0.49)
- Native host running, bridge socket active
- **Need to restart Claude Code session** for fresh MCP server to pick up the socket

### Verified Working
- Native messaging manifest: `~/.config/google-chrome/NativeMessagingHosts/com.anthropic.claude_code_browser_extension.json`
- Native host script: `~/.claude/chrome/chrome-native-host` → `versions/2.1.39 --chrome-native-host`
- Bridge socket: `/tmp/claude-mcp-browser-bridge-snadboy/{pid}.sock`
- Extension ID: `fcoeoabgfenejglbffodgkkbkcdhcgfn`

---

## n8n Coding Standards & Workflow Audit (2026-02-14)

**Status:** ✅ Complete

Documented n8n workflow coding standards in the shared skill and applied them across all 20 workflows.

### Coding Standards Added to n8n Skill

Added a "Coding Standards" section to `/mnt/shareables/.claude/skills/n8n/skill.md` covering:
- **Architecture** — standard flow pattern, sequential Globals, prefer credentials, one Code node per concern, webhook Respond Immediately
- **Notifications** — Discord for reports, Gotify for alerts, always notify on completion with context
- **Error Handling** — SSH `onError`, Code node try/catch, Merge node input indexing
- **Shell Commands** — Go template escaping, `!=` vs `<>`, nested quoting
- **File & Deployment** — workflow JSON location, API deploy, test before commit
- **Naming Conventions** — workflow names, node names, Globals constants

### Audit Findings & Fixes (11 workflows modified)

| Fix | Workflows | Count |
|-----|-----------|-------|
| Removed `description` field | arr-stack-health-check, daily-media-digest, discord-claude-bridge, get-plex-token, gmail-cleanup, gmail-labels-and-contacts, overseerr-request-notifier, plex-recently-added, trash-day-calc, trash-pickup-scheduler, trash-pickup-status | 11 |
| Webhook → Respond Immediately | gmail-cleanup (3 webhooks), trash-pickup-scheduler (1) | 2 |
| Removed orphaned Respond to Webhook nodes | gmail-cleanup (3), trash-pickup-scheduler (1) | 2 |
| Globals node repositioned (L→R flow) | gmail-cleanup, plex-recently-added | 2 |
| Added SSH `onError: continueRegularOutput` | get-plex-token | 1 |

### Workflows Not Changed (already compliant)
- daily-homelab-report, homelab-status-api, n8n-backup, network-daily-summary, network-health-monitor, pending-updates-monitor, proxmox-daily-summary, proxmox-health-monitor, weekly-version-audit

### Intentional `responseNode` Usage (returns data to caller)
- gmail-labels-and-contacts — returns JSON with label counts and contacts
- homelab-status-api — returns full status JSON

### Commits
- `97fdb6f` — Add webhook respond-immediately coding standard to n8n skill (skills repo)
- `0409887` — Add coding standards section to n8n skill (skills repo)
- `b137615` — Apply n8n coding standards across all workflows

---

## Consolidated Health Alert (2026-02-14)

**Status:** ✅ Complete

Replaced 7 separate monitoring/reporting workflows with a single Homelab Health Alert that reads cached data from the Status API.

### New Workflow: Homelab Health Alert

| Property | Value |
|----------|-------|
| Workflow ID | YP0wUZQB8DOfJgTA |
| File | homelab-health-alert.json |
| Schedule | Every 15 min at offset (`2/15 * * * *` → :02, :17, :32, :47) |
| Nodes | 8 (Schedule + Globals + HTTP Request + Evaluate + Format + If + Discord + NoOp) |
| Notification | Discord (on alert/recovery only) |

**How it works:**
1. Fetches cached status data from Status API webhook (`http://localhost:5678/webhook/homelab-status`)
2. Evaluates all health thresholds (network, proxmox, services, containers, infra)
3. 1-hour cooldown per alert key (no spam)
4. Recovery notifications when previously alerted issues clear
5. Single Discord embed: red for alerts, green for recovery

### Health Thresholds

| Category | Check | Threshold |
|----------|-------|-----------|
| Network | WAN status | != 'ok' |
| Network | Gateway CPU/Memory | > 80% |
| Network | Device offline | state != 1 |
| Network | WiFi poor satisfaction | > 3 clients below 50% |
| Network | Tunnel down | state != 'running' |
| Proxmox | Node offline | status != 'online' |
| Proxmox | Node memory | > 85% |
| Proxmox | Node root disk | > 80% |
| Proxmox | Node CPU | > 90% |
| Proxmox | Expected guest stopped | VMIDs 103-114, 200 |
| Proxmox | Guest memory | > 90% |
| Services | Media API error | .error field present |
| Containers | Unhealthy | status contains 'unhealthy' |
| Containers | Restarting | state = 'restarting' |
| Infra | Status API unavailable | no data returned |
| Infra | Data staleness | cache > 20 min old |
| Infra | Collection errors | collectionErrors array non-empty |

### Status API Enhancement

Added `collectionErrors` array to cached data in the Cache Results node. Tracks which data sources (unifi, pve, media-*) failed during collection, enabling the Health Alert to detect upstream failures.

### Deactivated Workflows (7)

| Workflow | ID | Reason |
|----------|-----|--------|
| Network Health Monitor | tFQDbJFTrwwYVJKu | Replaced by Health Alert (network thresholds) |
| Network Daily Summary | ppH7nKbAfGkObNAk | Webpage is the summary |
| Proxmox Health Monitor | Cs4Vu1hmLj82uBCQ | Replaced by Health Alert (PVE thresholds) |
| Proxmox Daily Summary | Fc1CXcJUU3LZ46G2 | Webpage is the summary |
| Arr Stack Health Check | qOZ6kS7MSlF9hOKb | Replaced by Health Alert (service error detection) |
| Daily Homelab Report | 5fUpCHbIrTCOdZ6F | Webpage is the summary |
| Daily Media Digest | puI2Gdj35nijpEey | Redundant with Daily Homelab Report |

### Unchanged

- **Weekly Version Audit** — runs weekly, collects unique data (GitHub releases, APT updates, Dockhand stacks)
- **Status API** — continues as the single data collector + webpage backend

### Files Changed
- `n8n/workflows/homelab-health-alert.json` (new)
- `n8n/workflows/homelab-status-api.json` (added collectionErrors to Cache Results)
- `/mnt/shareables/.claude/skills/n8n/skill.md` (updated workflow table + WORKFLOW_MAP)

### Commits
- `204c588` — Add Homelab Health Alert, consolidate monitoring workflows
- `a40685e` — Update n8n skill (workflow table + WORKFLOW_MAP)

---

## Discord sendLegacy Node Fix (2026-02-14)

**Status:** ✅ Complete

Replaced all Discord v2 `sendLegacy` webhook nodes across 15 workflow files with HTTP Request nodes. The `sendLegacy` operation worked functionally but displayed "undefined" in the n8n editor UI.

### What Changed

Replaced `n8n-nodes-base.discord` typeVersion 2 nodes with `n8n-nodes-base.httpRequest` typeVersion 4.2 nodes that POST directly to Discord webhook URLs via Globals constants.

### Globals Constants Added (2 new)

| Constant | Channel |
|----------|---------|
| `DISCORD_ALERTS_WEBHOOK_URL` | Alerts channel (5 workflows) |
| `DISCORD_REPORTS_WEBHOOK_URL` | Reports channel (10 workflows) |

Total Globals constants: 36 (was 34)

### Workflows Updated (15)

**Alerts (DISCORD_ALERTS_WEBHOOK_URL):**
- homelab-health-alert (also added Globals node to flow)
- arr-stack-health-check
- n8n-backup
- proxmox-health-monitor
- network-health-monitor

**Reports (DISCORD_REPORTS_WEBHOOK_URL):**
- gmail-cleanup (also changed from generic `DISCORD_WEBHOOK_URL`)
- weekly-version-audit (3 embeds)
- daily-homelab-report (3 embeds)
- plex-recently-added
- trash-pickup-scheduler
- overseerr-request-notifier
- gmail-labels-and-contacts
- daily-media-digest
- proxmox-daily-summary
- network-daily-summary

### Discord Webhook Credentials (reference)

| Credential | ID | Webhook ID |
|---|---|---|
| Discord Webhook (generic) | — | 1470549509527441501 |
| Discord Alerts Webhook | ChjLJM1kqQJWWMx7 | 1471359292211724499 |
| Discord Reports Webhook | 2sFNFWT1cJPmliyb | 1471359836959674486 |

### Verification
- All 15 workflows deployed via API (PUT)
- Health Alert execution 5795 at :32 — success with new Globals node
- Zero `sendLegacy` references remaining in any workflow
- Only Discord node type remaining: `discordTrigger` in discord-claude-bridge (unrelated)

### Commit
- `5c18ec3` — Replace Discord v2 sendLegacy nodes with HTTP Request nodes

---

## Gmail Cleanup — Scan Efficiency & CLEANUP_KEPT Label (2026-02-14)

**Status:** ✅ Complete

Overhauled Gmail Cleanup scanning logic to prevent preserved threads from blocking progress on deletable threads, and added a labeling system to avoid re-scanning already-evaluated threads.

### Problem

1. `maxThreads` (500) capped **scans**, not **deletions** — preserved threads (KEEP label, keeper contacts) consumed scan slots, potentially blocking all deletable threads from being reached
2. Keeper contacts were only checked in Phase 5 (metadata fetch) — every old email from a keeper contact matched the query, wasting API calls
3. Threads preserved on one run would match again on the next run, re-fetching metadata only to preserve them again

### Fixes Applied (4 commits)

**1. Match estimate visibility** (`55dea1f`)
- Capture `resultSizeEstimate` from Gmail API on first page fetch
- Report shows "Threads scanned: 500 of ~2,340 matching (limit: 500)" when capped

**2. Cap deletions, not scans** (`c9f0e26`)
- `maxThreads` now limits actual deletions (Phase 6), not thread fetching (Phase 4)
- All matching threads are fetched and evaluated; only trashinng is capped at 500 per run
- Report distinguishes eligible vs actually deleted: "Threads TRASHED: 500 (capped at 500, 1,203 eligible)"

**3. Keeper contact query exclusion** (`4f1b6db`)
- After loading keeper emails (Phase 2), injects `-from:(email1 OR email2 ...)` into the Gmail search query
- Prevents most keeper-contact threads from matching at all (FROM only; TO/CC caught by Phase 5)
- Capped at 60 addresses to stay within Gmail query length limits

**4. CLEANUP_KEPT label system** (`a73761f`)
- Hidden `CLEANUP_KEPT` Gmail label (auto-created, `labelHide`/`hide`)
- In live mode, preserved threads get `CLEANUP_KEPT` applied via `threads.modify`
- Search query includes `-label:CLEANUP_KEPT` — already-evaluated threads are excluded entirely
- Eliminates redundant metadata API calls on subsequent runs

### Verify Mode

New `verify` mode re-evaluates all CLEANUP_KEPT threads against current state:
- Checks each thread against current keeper contacts, KEEP label, KEEP_nnn retention
- Removes `CLEANUP_KEPT` from threads that no longer qualify for preservation
- Released threads re-enter the cleanup pipeline on the next run

**Triggers:**
| Endpoint | Mode |
|----------|------|
| `/webhook/gmail-cleanup-dry` | Dry run (no changes) |
| `/webhook/gmail-cleanup-live` | Live (deletes + labels) |
| `/webhook/gmail-cleanup-verify` | Verify CLEANUP_KEPT threads |
| Daily 4 AM | Live |
| Form trigger | Dropdown: dry-run / live / verify |

**Discord embed colors:** Yellow = live, Green = dry-run, Blue = verify

### Workflow Changes
- Nodes: 10 → 12 (added Verify webhook trigger + Set Verify Config)
- Code node: CLEANUP_KEPT label create/apply, verify phase (Phase 6b), updated report
- Discord embed: handles verify mode stats

### Commits
- `55dea1f` — Add match estimate and limit warning to Gmail Cleanup report
- `c9f0e26` — Cap deletions not scans in Gmail Cleanup
- `4f1b6db` — Exclude keeper contacts from Gmail search query
- `a73761f` — Add CLEANUP_KEPT label system and verify mode to Gmail Cleanup

---

## Outstanding Items

- NAS storage stats for status dashboard (need SSH access to UniFi NAS and Synology)

---

**Last Updated:** 2026-02-14
