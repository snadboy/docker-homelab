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
| Nodes | 23 (7 APT SSH + 4 Docker SSH + 5 Health SSH + 1 Dockhand SSH + 1 Code API + Merge + Format + Discord + Globals) |
| Replaced | Pending Updates Monitor (`mc4XV3qJ1FWNKVJO`, deactivated) |

### What It Checks
- **Docker containers** (10): sonarr, radarr, prowlarr, overseerr, sabnzbd, tautulli, plex, traefik, zigbee2mqtt, n8n
- **Running vs latest**: Compares `org.opencontainers.image.version` label against GitHub releases API
- **Zigbee2mqtt**: Uses `docker exec` to read `/app/package.json` (no OCI labels)
- **PVE version**: From `/api2/json/version` (PVEAuditor token)
- **Technitium DNS version**: From `/api/settings/get` API
- **APT updates**: 7 SSH hosts (plex, arr, cadre, ns, utilities, iot, ha)
- **Container health**: 5 Docker hosts (arr, plex, cadre, utilities, iot) — unhealthy, restarting, restart loops (>3)
- **Dockhand stacks**: SQLite query for sync status + failed deployments (7d)

### Discord Output
Three embeds per message:
1. **Software Versions** (green/yellow) — Docker container versions + PVE + Technitium
2. **System Updates** (green/yellow) — APT pending counts per host
3. **Container & Stack Health** (green/red) — unhealthy containers, restart loops, Dockhand stack sync, failed deployments

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

### Changes
- **Arr Stack Health Check**: Full rewrite — single Code node replaced with 5 HTTP Request nodes using credential auth + Merge
- **Gotify nodes in 7 workflows**: Replaced manual `X-Gotify-Key` header with Gotify API credential

### Commit
- `aa8895f` — Refactor n8n workflows to use credential-based auth

---

## Discord Node Refactor (2026-02-11)

**Status:** ✅ Complete

Switched all 5 Discord-posting workflows from HTTP Request webhook posts to native `n8n-nodes-base.discord` v2 node.

### Changes Applied to All 5 Workflows
1. **env→globals**: Renamed misleading `const env = $input.first().json` to use `$('Globals').first().json` directly
2. **fields→description**: Converted Code node output from `fields[]` arrays to markdown `description` text
3. **HTTP Request→Discord v2**: Replaced manual webhook POST with native Discord node using `discordWebhookApi` credential (ID: `410BCHcgoAHtBHHk`) and `json` inputMethod for embeds

### Workflows Updated

| Workflow | ID | Pattern |
|----------|-----|---------|
| Daily Network Summary | `ppH7nKbAfGkObNAk` | Single embed (title/description/footer) |
| Daily Proxmox Summary | `Fc1CXcJUU3LZ46G2` | Single embed (title/description/footer) |
| Network Health Monitor | `tFQDbJFTrwwYVJKu` | Alert embed (alertTitle/description/alertColor) |
| Proxmox Health Monitor | `Cs4Vu1hmLj82uBCQ` | Alert embed (alertTitle/description/alertColor) |
| Weekly Version Audit | `BXBsZXozpqxLZyoa` | Triple embed ($json.embeds[0..2]) |

### Verification
- Both health monitors confirmed running successfully every 15 minutes after deployment
- Merge inputs verified correct in all workflows (no fix needed)

### Commit
- `ebd9a22` — Switch Discord workflows to native Discord v2 node

---

## Gotify → Discord Migration (2026-02-11)

**Status:** ✅ Complete

Switched all 8 remaining Gotify notification workflows to Discord, unifying all n8n notifications on Discord.

### Workflows Converted

| # | Workflow | ID | Discord Node |
|---|----------|-----|-------------|
| 1 | Arr Stack Health Check | `qOZ6kS7MSlF9hOKb` | Discord Alert |
| 2 | Gmail Cleanup | `YvL90Tr5LhpyBV1D` | Discord Notify |
| 3 | Gmail Labels & Contacts | `bf54qHDO8Gt82e0u` | Discord Notify |
| 4 | Trash Pickup Scheduler | `D5R6GlhUDJTUGS8P` | Discord Notify |
| 5 | n8n Backup | `dVt3Th1wvWvutg0a` | Discord Notify |
| 6 | Plex Recently Added | `NYdQlvUoz1x14bIZ` | Discord Notify |
| 7 | Overseerr Request Notifier | `1bdxTCXlpam5yUco` | Discord Notify |
| 8 | Daily Media Digest | `puI2Gdj35nijpEey` | Discord Digest |

### Discord Embed Pattern

All nodes use `n8n-nodes-base.discord` v2 with webhook auth:
- Credential: Discord Webhook (`410BCHcgoAHtBHHk`)
- Embed input method: `json` (dynamic `JSON.stringify`)
- Priority → Color mapping: >=7 red (`15158332`), >=5 yellow (`16776960`), <5 green (`3066993`)

### Gotify Cleanup (optional follow-up)

- Remove `GOTIFY_URL` from Global Constants (no longer referenced by any workflow)
- Delete Gotify API credential (`hZM2wpBkhJwPJf32`)
- Consider decommissioning the Gotify container on utilities

### Files Changed
- 8 workflow JSON files in `n8n/workflows/`

### Commit
- `4cd3dd6` — Switch 8 n8n workflows from Gotify to Discord notifications

---

## Discord Notification Organization (2026-02-12)

**Status:** ✅ Complete

Reorganized all n8n Discord notifications into two channels and consolidated daily reports.

### Discord Channels

| Channel | Webhook Credential | Purpose |
|---------|-------------------|---------|
| #homelab-alerts | `ChjLJM1kqQJWWMx7` (Discord Alerts Webhook) | Health monitors, backup failures |
| #homelab-reports | `2sFNFWT1cJPmliyb` (Discord Reports Webhook) | Daily reports, weekly audits, event notifications |

### Workflow Routing

**Alerts channel (3 workflows):**
- Proxmox Health Monitor (`Cs4Vu1hmLj82uBCQ`)
- Network Health Monitor (`tFQDbJFTrwwYVJKu`)
- Arr Stack Health Check (`qOZ6kS7MSlF9hOKb`)

**Reports channel (10 workflows):**
- Daily Homelab Report (`5fUpCHbIrTCOdZ6F`) — NEW consolidated report
- Gmail Cleanup, Gmail Labels & Contacts, Trash Pickup Scheduler
- n8n Backup (failure-only alerts go to #homelab-alerts)
- Plex Recently Added, Weekly Version Audit

### Consolidated Daily Homelab Report

| Property | Value |
|----------|-------|
| Workflow ID | `5fUpCHbIrTCOdZ6F` |
| Schedule | Daily 8:15 AM |
| Nodes | 12 (Trigger + Globals + 5 data gatherers + Merge + Format + Discord) |
| Replaces | Daily Network Summary, Daily Proxmox Summary, Daily Media Digest |

**3 embeds in single message:**
1. Network — WAN health, gateway, speedtest, devices, WiFi clients, Cloudflare tunnels
2. Proxmox — Node stats (CPU/mem/disk/uptime), VM/CT counts
3. Media — Sonarr calendar, Radarr queue, SABnzbd status, Plex libraries, Overseerr requests

### n8n Backup — Failure Only

Added If node (`hasErrors` check) between Export and Discord. Only sends alert (red embed, #homelab-alerts) when backup has errors. Silent on success.

### Deactivated Workflows

| Workflow | ID | Reason |
|----------|-----|--------|
| Daily Network Summary | `ppH7nKbAfGkObNAk` | Replaced by Daily Homelab Report |
| Daily Proxmox Summary | `Fc1CXcJUU3LZ46G2` | Replaced by Daily Homelab Report |
| Daily Media Digest | `puI2Gdj35nijpEey` | Replaced by Daily Homelab Report |
| Overseerr Request Notifier | `1bdxTCXlpam5yUco` | Redundant with Plex Recently Added |

### Files Changed
- 13 workflow JSON files updated (webhook credential routing)
- `n8n/workflows/daily-homelab-report.json` (new)
- `n8n/workflows/n8n-backup.json` (added If node for failure-only)

### Commit
- `48b5add` — Organize Discord notifications: channels, consolidated report, backup alerts

---

## Outstanding Items

- **Gotify decommission**: No workflows reference Gotify anymore. Consider removing the Gotify container from utilities and cleaning up Global Constants / credentials.

---

**Last Updated:** 2026-02-12
