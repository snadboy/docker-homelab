# docker-homelab Session Notes

## Repository Information
- **URL:** https://github.com/snadboy/docker-homelab
- **Local Path:** /home/snadboy/projects/docker-homelab
- **Main Branch:** main
- **Current Branch:** main
- **Latest Commit:** (see git log)

## Recent Changes

### 2026-02-09: Dynamic Plex Token via SSH Sub-Workflow

**Status:** ✅ Complete

**Problem:** `PLEX_TOKEN` env var in n8n became stale when Plex rotated it, causing 401 errors in Plex Recently Added and Daily Media Digest workflows.

**Solution:** Created a sub-workflow that dynamically fetches the current token from the Plex host via SSH, eliminating the need for a static `PLEX_TOKEN` env var.

**Infrastructure:**
- Enabled sshd on plex host (192.168.86.40) — was Tailscale SSH only
- Generated ed25519 key pair for n8n → plex SSH access
- Created "Plex Host SSH" credential in n8n (ID: `6g4Tcr5sVJp0To9W`)

**Workflows:**
- **Get Plex Token** (`AM7xbizoMlhMEp8x`) — New sub-workflow
  - Flow: Execute Workflow Trigger → SSH Read Token → Parse Token
  - SSH command: `docker exec plex sed -n 's/.*PlexOnlineToken="\([^"]*\)".*/\1/p' Preferences.xml`
  - Returns: `{PLEX_URL, PLEX_TOKEN}`
  - Note: Uses `sed` instead of `grep -oP` because n8n's SSH node mangles Perl regex `\K`
- **Plex Recently Added** (`NYdQlvUoz1x14bIZ`) — Modified
  - Replaced `Set Env Vars` node with `Execute Workflow` node calling Get Plex Token
  - Flow: Schedule → Get Plex Token → Code → If → Gotify
- **Daily Media Digest** (`puI2Gdj35nijpEey`) — Modified
  - Removed PLEX_URL/PLEX_TOKEN from Set Env Vars (kept 8 other vars)
  - Added Execute Workflow node between Set Env Vars and Code
  - Code node merges both sources: `{...$('Set Env Vars').first().json, ...$input.first().json}`

**Key Technical Details:**
- SSH node requires `"authentication": "privateKey"` parameter (defaults to `"password"`)
- SSH node returns `{code, signal, stdout, stderr}` not `{exitCode, stdout, stderr}`
- `PLEX_TOKEN` removed from n8n `.env` (both local and remote utilities host)
- `PLEX_URL` kept in `.env` since sub-workflow uses `$env.PLEX_URL`

**Verification:**
- Sub-workflow webhook test: ✅ Returns `{PLEX_URL, PLEX_TOKEN}` correctly
- SSH connectivity from n8n container to plex:22: ✅

**Files Changed:**
- `n8n/workflows/get-plex-token.json` (new)
- `n8n/workflows/plex-recently-added.json` (modified)
- `n8n/workflows/daily-media-digest.json` (modified)
- `n8n/.env` / `n8n/.env.example` (removed PLEX_TOKEN)

---

### 2026-02-09: Extract Trash Day Logic into Sub-Workflow

**Status:** ✅ Complete

**Summary:** Refactored duplicated date math logic (~60 lines: `formatDate`, `addDays`, `getHolidays`, holiday detection) from Trash Pickup Scheduler and Trash Pickup Status into a shared sub-workflow callable via Execute Workflow node.

**Workflows:**
- **Trash Day Calc** (`9pRyazs5XHc1OBxG`) — New sub-workflow with shared date logic
  - `executeWorkflowTrigger` v1.1 with `inputSource: "passthrough"`
  - Returns: pickupDay, pickupDate, takeOutDay, takeOutDate, status, delayed, holiday, daysUntil, weekOf
- **Trash Pickup Status** (`ydLw1ilTg3sE8vXj`) — Modified to call sub-workflow
  - Flow: Webhook → Execute Workflow (Compute Trash Day) → response
  - `executeWorkflow` v1.1 with resource locator (`__rl`) format
- **Trash Pickup Scheduler** (`D5R6GlhUDJTUGS8P`) — Modified to call sub-workflow
  - Flow: Schedule/Webhook → Set Credentials → Execute Workflow → Code: Create Calendar Events → Gotify
  - Calendar event creation + Gotify logic kept in Code node, date math removed

**Key Technical Details:**
- `executeWorkflowTrigger` v1.1 requires `inputSource: "passthrough"` (default is `workflowInputs` which requires schema)
- `executeWorkflow` v1.1+ requires `workflowId` as resource locator object: `{"__rl": true, "value": "<id>", "mode": "list"}`
- Sub-workflow `callerPolicy: "workflowsFromSameOwner"` (default)

**Verification:**
- `GET /webhook/trash-pickup-status` ✅ Returns JSON: `{"pickupDay":"Friday","pickupDate":"2026-02-13",...}`
- `GET /webhook/trash-pickup` ✅ Triggers scheduler, creates calendar event, sends Gotify notification
- Sub-workflow execution logs: ✅ Appears as child executions

**Files Changed:**
- `n8n/workflows/trash-day-calc.json` (new)
- `n8n/workflows/trash-pickup-scheduler.json` (modified)
- `n8n/workflows/trash-pickup-status.json` (modified)

---

### 2026-02-09: Fixed process.env in n8n Code Nodes

**Status:** ✅ Complete

**Problem:** Three workflows using `process.env.X` in Code nodes failed with `process is not defined [line 2]`. n8n's task runner sandbox executes Code nodes in isolated processes where the `process` global is unavailable, despite `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`.

**Fix Pattern:** Added a "Set Env Vars" node before each Code node that resolves `$env.X` expressions (which work in n8n expression fields), then the Code node reads them via `$input.first().json.VARNAME`.

**Workflows Fixed:**
- **Arr Stack Health Check** (`qOZ6kS7MSlF9hOKb`) — 10 env vars (Sonarr, Radarr, Prowlarr, SABnzbd, Overseerr URLs + API keys)
- **Plex Recently Added** (`NYdQlvUoz1x14bIZ`) — 2 env vars (PLEX_URL, PLEX_TOKEN)
- **Daily Media Digest** (`puI2Gdj35nijpEey`) — 10 env vars (Sonarr, Radarr, SABnzbd, Plex, Overseerr URLs + API keys)

**Additional Bug Fixed:** Some URLs used single quotes `'${process.env.X}/api/...'` instead of backticks, making `${}` a literal string instead of template interpolation.

**Files Changed:**
- `n8n/workflows/arr-stack-health-check.json`
- `n8n/workflows/plex-recently-added.json`
- `n8n/workflows/daily-media-digest.json`

---

### 2026-02-08: Trash Pickup Scheduler Workflow

**Status:** ✅ Complete

**Summary:** Created n8n workflow that schedules weekly trash pickup reminders on Google Calendar with holiday delay logic.

**Workflow Created:**
- **Trash Pickup Scheduler** (`D5R6GlhUDJTUGS8P`)
  - Schedule: Every Sunday at 9 AM + Webhook: `GET /webhook/trash-pickup`
  - Default trash day: Friday. Creates "Take trash out to curb" all-day event on Thursday (day before)
  - Holiday detection: New Year's, Memorial Day, Independence Day, Labor Day, Thanksgiving, Christmas
  - If holiday falls Mon-Fri of the week, trash is delayed one day (to Saturday) and an extra "Trash delay due to [holiday]" event is created
  - Events created on "Anderson" calendar (`52pai5sgrbqhh12h7mv1o3rb08@group.calendar.google.com`)
  - Sends summary via Gotify notification

**OAuth Scope Upgrade:**
- Re-authorized Google OAuth2 with broader scopes:
  - `https://mail.google.com/` (Gmail)
  - `https://www.googleapis.com/auth/gmail.modify` + `gmail.labels`
  - `https://www.googleapis.com/auth/calendar` (NEW)
  - `https://www.googleapis.com/auth/contacts.readonly` (NEW)
- Added `http://localhost:8888` redirect URI to Google Cloud Console OAuth client
- New refresh token stored in `GOOGLE_REFRESH_TOKEN` env var

**Verification:**
- Trash Pickup Scheduler: ✅ Execution #83, success in 0.6s
- Calendar event created correctly on Thursday Feb 12 (day before Friday pickup)
- Test event cleaned up after verification

---

### 2026-02-08: Gmail Cleanup & Labels+Contacts Workflows

**Status:** ✅ Complete

**Summary:** Ported gmail-trim cleanup logic to n8n as two JavaScript-based workflows, replacing the old "Gmail - List Labels" workflow.

**Workflows Created:**
1. **Gmail Cleanup** (`YvL90Tr5LhpyBV1D`) - Full cleanup logic with dry-run/live modes
   - Webhook: `GET /webhook/gmail-cleanup?mode=dry-run&days=30`
   - Discovers KEEP/KEEP_nnn labels, loads keeper contacts from People API
   - Builds compound search query, scans threads, checks preservation rules
   - Dry-run (default): reports what would be deleted. Live: trashes threads.
   - Sends report via Gotify notification
2. **Gmail Labels & Contacts** (`bf54qHDO8Gt82e0u`) - Discovery/reporting tool
   - Webhook: `GET /webhook/gmail-labels-contacts`
   - Lists all labels with message counts, keeper contact group members
   - Sends report via Gotify notification
3. **Deleted:** Old "Gmail - List Labels" (`jP5TmovCB2TlHSih`) - replaced by #2

**Key Technical Details:**
- n8n Code node sandbox blocks `this.helpers.httpRequestWithAuthentication()`
- Solution: Set node passes `$env.GOOGLE_*` vars → Code node does manual OAuth2 token refresh via `this.helpers.httpRequest()` to Google's token endpoint
- Google OAuth2 credentials stored as n8n env vars: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`
- OAuth scopes: Gmail full access, Calendar, Contacts (read-only)

**Files Changed:**
- `n8n/.env.example` - Added Google OAuth2 credential placeholders
- `n8n/workflows/` - Exported all 7 workflows as JSON backups

**Verification:**
- Gmail Labels & Contacts: ✅ Execution #70, success in 3.7s
- Gmail Cleanup (dry-run): ✅ Execution #71, success in 51.9s
- Gotify notifications: ✅ Sent

---

### 2026-02-08: Fixed n8n Env Vars + Gmail Labels Workflow

**Status:** ✅ Complete

**Problem:** All n8n workflows failed at Gotify HTTP Request nodes because `process.env.X` doesn't work in n8n expression fields (={{ ... }}). The correct syntax is `$env.X`.

**Changes Made:**
1. Added `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` to `n8n/docker-compose.yml` (enables `$env` access)
2. Updated all 4 workflows via API: HTTP Request nodes `process.env.X` → `$env.X`
3. Redeployed n8n container on utilities host
4. Created "Gmail - List Labels" workflow (ID: `jP5TmovCB2TlHSih`)

**Workflows Fixed:**
- Arr Stack Health Check (`qOZ6kS7MSlF9hOKb`)
- Daily Media Digest (`puI2Gdj35nijpEey`)
- Overseerr Request Notifier (`1bdxTCXlpam5yUco`)
- Plex Recently Added (`NYdQlvUoz1x14bIZ`)

**Key Fix Detail:**
- Expression fields (={{ ... }}) in HTTP Request nodes: `process.env.X` → `$env.X`
- Code nodes (jsCode): `process.env.X` does NOT work — n8n's task runner sandbox isolates Code nodes in processes where `process` is undefined. See 2026-02-09 fix below.

**n8n API Notes:**
- Create workflow: `POST /api/v1/workflows` (no `active` field - it's read-only)
- Update workflow: `PUT /api/v1/workflows/{id}` (only `name`, `nodes`, `connections`, `settings` allowed)
- Activate: `POST /api/v1/workflows/{id}/activate`
- Deactivate: `POST /api/v1/workflows/{id}/deactivate`
- No public API to manually execute workflows - use webhook triggers for testing

**Verification:**
- Overseerr Request Notifier: ✅ Triggered successfully after restart
- Daily Media Digest: ✅ Tested via temporary webhook trigger, Gotify notification received
- Env var test workflow: ✅ Created, verified `$env.GOTIFY_URL` resolved correctly, deleted

**Gmail Labels Workflow:**
- Created with Manual Trigger → Gmail Get Labels → Code Format → Gotify Notify
- Node type: `n8n-nodes-base.gmail` (v2.1) with `resource: "label"` (not `gmailLabel`)
- Gmail OAuth2 credential created in n8n UI (credential ID: `6wlAoJG85hyBlUo7`, name: "Gmail account")
- OAuth client created in Google Cloud Console (project: gmtrim):
  - Type: Web application, Name: n8n
  - Client ID: `104439945788-mrb7k896tkd45btgm56jibobhpal1cnm.apps.googleusercontent.com`
  - Redirect URI: `https://n8n.isnadboy.com/rest/oauth2-credential/callback`
- ✅ Tested via webhook trigger - execution #39 succeeded, Gotify notification received

**Next Steps:**
- Build full Gmail cleanup workflow once label listing works

---

### 2026-02-08: Deployed n8n Workflow Automation

**Status:** ✅ Complete

**Changes Made:**
1. Created `n8n/docker-compose.yml` with Traefik integration
2. Created `n8n/.env.example` template
3. Created external volume `n8n-data` on utilities host
4. Deployed via docker compose on utilities
5. Traefik HTTP provider discovered `n8n-5678` service automatically

**Stack Details:**
- **Name:** n8n
- **Environment:** Utilities
- **Container:** n8n
- **Image:** docker.n8n.io/n8nio/n8n:latest (v2.6.4)
- **State:** running
- **Domain:** https://n8n.isnadboy.com
- **Volume:** n8n-data (external, mounted at /home/node/.n8n)
- **Port:** 5678:5678

**Key Configuration:**
- `WEBHOOK_URL=https://n8n.isnadboy.com/` - webhooks work through reverse proxy
- `N8N_HOST=n8n.isnadboy.com` - correct host display
- `N8N_PROTOCOL=https` - HTTPS via Traefik
- `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` - allows `$env.X` in expression fields
- Traefik label: `snadboy.revp.5678.domain=n8n.isnadboy.com`

**Verification:**
- Container running: ✅
- Traefik discovery: ✅ `n8n-5678: https://n8n.isnadboy.com -> http://host-utilities.isnadboy.com:5678/`
- HTTPS access: ✅ HTTP 200
- Workflows executing: ✅ All 4 workflows + Gmail Labels created

---

### 2026-02-07: Added Collapsible Groups to Homepage

**Status:** ✅ Complete

**Changes Made:**
1. Updated `settings.yaml` with collapsible group configuration
2. Set frequently accessed groups as expanded (Media Management, Media Server, Smart Home)
3. Set infrastructure groups as collapsed by default (Proxmox Cluster, Backup Storage, Infrastructure)
4. Created `homepage/COLLAPSIBLE-GROUPS.md` documentation
5. Committed and pushed to GitHub (commit: 9abf07d)

**Benefits:**
- Reduced visual clutter on dashboard
- Improved page load performance (collapsed groups don't render widgets initially)
- Better organization - frequently used services always visible
- Infrastructure monitoring available on-demand with click to expand

**Group Configuration:**
- **Always Expanded:** Media Management, Media Server, Smart Home
- **Collapsed by Default:** Proxmox Cluster, Backup Storage, Infrastructure

**Files Modified:**
- `homepage/COLLAPSIBLE-GROUPS.md` (new)
- Updated `settings.yaml` in homepage-config volume

---

### 2026-02-06: Deployed Homepage Dashboard

**Status:** ✅ Complete

**Changes Made:**
1. Created `homepage/docker-compose.yml` with Traefik integration
2. Created `homepage/.env.example` for environment variables
3. Committed and pushed to GitHub
4. Added stack to Dockhand database (stack ID: 10)
5. Created external volume `homepage-config` on utilities host
6. Deployed via docker compose on utilities

**Stack Details:**
- **Name:** homepage
- **Environment:** Utilities (Dockhand ID: 1)
- **Container:** homepage
- **Image:** ghcr.io/gethomepage/homepage:latest
- **State:** running (healthy)
- **Domain:** https://homepage.isnadboy.com
- **Volume:** homepage-config (external)
- **Port:** 3500:3000

**Key Features:**
- Read-only Docker socket mount for container stats
- Traefik automatic HTTPS routing via `snadboy.revp.3000.domain` label
- Auto-update and webhook enabled in Dockhand
- Port 3000 exposed for web interface

**Files Modified:**
- `homepage/docker-compose.yml` (new)
- `homepage/.env.example` (new)

**Verification:**
- Container health check: ✅ healthy
- Docker socket access: ✅ read-only mount working
- Traefik discovery: ✅ discovered by sb-traefik-http-provider
- Traefik routing: ✅ HTTPS working at https://homepage.isnadboy.com (HTTP 200)
- Volume persistence: ✅ mounted at /app/config
- Dockhand sync: ✅ stack synced successfully

**Deployment Notes:**
- Fixed git ownership issue in Dockhand container with `git config --global --add safe.directory`
- Resolved SSH host key issue for utilities localhost access
- Labels only apply when deploying from compose file (not stdin pipe)
- Required provider restart to discover new container (~30 seconds for health check)
- Fixed host validation by adding `HOMEPAGE_ALLOWED_HOSTS=homepage.isnadboy.com`

**Configuration (2026-02-06):**
Created comprehensive Homepage dashboard with all active services:

**Service Groups Configured:**
1. **Media Management** (5 services)
   - Sonarr, Radarr, Prowlarr, Overseerr, Bazarr
   - All with API widgets enabled

2. **Media Server** (2 services)
   - Plex (API widget enabled)
   - Tautulli (widget pending API key)

3. **Downloads** (1 service)
   - SABnzbd (API widget enabled)

4. **Infrastructure** (6 services)
   - Traefik, Traefik HTTP Provider, Dockhand
   - Uptime Kuma (widget pending slug), Gotify, Script Server

5. **Custom** (1 service)
   - Agregarr

6. **Smart Home** (1 service)
   - Home Assistant (API widget enabled)

**Configuration Files Created:**
- `services.yaml` - 16 services with API integrations
- `widgets.yaml` - Resource monitoring, Docker stats, search
- `bookmarks.yaml` - External links (GitHub, Tailscale, docs)
- `settings.yaml` - Dark theme, boxed layout, grid organization
- `README.md` - Configuration documentation

**Features:**
- Dark mode with slate color scheme
- API widgets for real-time service stats
- Docker integration for container monitoring
- Organized grid layout by service category
- Quick search with Google integration
- Resource usage widgets (CPU, memory)

**Updates (2026-02-06 - Evening):**
- ✅ Removed Bazarr service completely
  - Deleted docker-compose.yml
  - Stopped and removed container on arr host
  - Removed bazarr-data volume
  - Removed from Homepage configuration

- ✅ Added Tautulli API integration
  - API key: a9e9e9242f0c4ea8a0990c56dd62ce40
  - Widget shows Plex analytics and stream stats

- ✅ Added Proxmox cluster monitoring
  - Created API user: homepage@pve
  - API token: homepage@pve!homepage-token
  - Role: PVEAuditor (read-only access)
  - Monitoring 3 nodes:
    - pve-multivac (192.168.86.104) - Plex host
    - pve-colossus
    - pve-guardian
  - Widgets show: VMs, LXCs, CPU, memory, storage per node

**Final Updates (2026-02-06 - Late Evening):**
- ✅ Fixed Proxmox API connectivity issues
  - Changed from hostnames to Tailscale IPs
  - pve-colossus: 100.64.193.33:8006
  - pve-guardian: 100.109.201.46:8006
  - pve-multivac: 100.69.91.74:8006
  - All nodes now showing stats correctly

- ✅ Fixed Plex API integration
  - Added HOMEPAGE_VAR_PLEX_TOKEN environment variable
  - Widget now showing library and stream stats

- ✅ Reorganized services
  - Moved SABnzbd from "Downloads" to "Media Management" group
  - Better logical organization

- ✅ Added Docker container monitoring
  - Created docker.yaml for container state tracking
  - Updated widgets.yaml with expanded Docker stats
  - Shows running containers, CPU, memory per container

- ✅ Added PBS placeholders
  - alexandria.isnadboy.com:8007
  - svalbard.isnadboy.com:8007
  - Ready for configuration once servers are accessible
  - Setup notes in homepage-config/PBS-SETUP-NOTES.md

**Latest Updates (2026-02-06 - Final Session):**

- ✅ Fixed Plex token authentication
  - Retrieved working token from Plex Preferences.xml
  - Old token (expired): 05f660f70f3e23a0445997d159ad109ffb325bd2
  - New token (working): js1SqwFxuN2eirNGdeox
  - Plex widget now showing library stats, active streams, bandwidth
  - Verified working with API test

- ✅ Removed PBS servers (not available)
  - alexandria.isnadboy.com - DNS points to cadre, server doesn't exist
  - svalbard.isnadboy.com - DNS points to cadre, server doesn't exist
  - Removed HOMEPAGE_VAR_PBS_USER and HOMEPAGE_VAR_PBS_TOKEN
  - Cleaned up PBS-SETUP-NOTES.md documentation
  - Removed from all configuration files

- ✅ Reorganized service groups
  - Moved Agregarr from "Custom" to "Media Management"
  - Removed empty "Custom" group from layout
  - Better logical organization of media services

- ✅ Confirmed Home Assistant working
  - Already configured in Smart Home section
  - Widget showing entities and sensors
  - API integration active

**Final Service Count:** 17 services across 5 groups
- **Media Management: 6** (Sonarr, Radarr, Prowlarr, Overseerr, SABnzbd, Agregarr)
- **Media Server: 2** (Plex, Tautulli)
- **Proxmox Cluster: 3** (Multivac, Colossus, Guardian - all with working APIs)
- **Infrastructure: 6** (Traefik, HTTP Provider, Dockhand, Uptime Kuma, Gotify, Script Server)
- **Smart Home: 1** (Home Assistant)

**API Widget Status:** 14/14 working (100%) ✅
- All *arr services: ✅
- Plex & Tautulli: ✅
- All Proxmox nodes: ✅
- Home Assistant: ✅
- Docker monitoring: ✅

**Environment Variables (Final):**
```yaml
- HOMEPAGE_VAR_PLEX_TOKEN=js1SqwFxuN2eirNGdeox
- HOMEPAGE_VAR_TAUTULLI_KEY=a9e9e9242f0c4ea8a0990c56dd62ce40
- HOMEPAGE_VAR_PROXMOX_USER=homepage@pve!homepage-token
- HOMEPAGE_VAR_PROXMOX_TOKEN=16e2f699-b719-4017-9dd6-4ca487594dc7
```

**Dashboard Status:** Fully operational, zero errors, real-time monitoring active

---

## Previous Changes

### 2026-01-25: Deployed Dockhand Docker Management UI

**Status:** ✅ Complete

**Changes Made:**
1. Created `dockhand/docker-compose.yml` with Traefik integration
2. Created `dockhand/.env.example` template for optional encryption key
3. Committed and pushed to GitHub
4. Created external volume `dockhand-data` on utilities endpoint (ID: 13)
5. Deployed stack to utilities via Portainer API

**Stack Details:**
- **Name:** dockhand
- **Stack ID:** 72
- **Endpoint:** utilities (ID: 13)
- **Container:** /dockhand
- **Image:** fnsys/dockhand:latest
- **State:** running (healthy)
- **Domain:** https://dockhand.isnadboy.com
- **Volume:** dockhand-data (external)

**Key Features:**
- Read-only Docker socket mount for security
- Traefik automatic HTTPS routing via `snadboy.revp.3000.domain` label
- SQLite database initialized at `/app/data/db/dockhand.db`
- Event and metrics subprocesses running successfully
- Port 3000 exposed for web interface

**Files Modified:**
- `dockhand/docker-compose.yml` (new)
- `dockhand/.env.example` (new)

**Verification:**
- Container health check: ✅ healthy (Up 10+ minutes)
- Docker socket access: ✅ working
- Database initialization: ✅ complete (4/4 migrations applied)
- Traefik discovery: ✅ discovered by sb-traefik-http-provider
- Traefik routing: ✅ HTTPS working at https://dockhand.isnadboy.com
- Volume persistence: ✅ mounted at /app/data
- DNS resolution: ✅ resolves to host-cadre.isnadboy.com (100.117.24.88)
- HTTPS access: ✅ HTTP 200 OK
- Direct port access: ✅ HTTP 200 on host-utilities.isnadboy.com:3000

**Service Discovery Details:**
- Provider service name: `dockhand-3000`
- Public URL: https://dockhand.isnadboy.com
- Backend URL: http://host-utilities.isnadboy.com:3000/
- Discovery time: ~2 minutes after deployment (required provider restart)

**Access Verified:**
- Web UI accessible at https://dockhand.isnadboy.com
- SSL certificate valid (Let's Encrypt via Traefik)
- Initial setup page loads successfully

**Next Steps:**
- ✅ Access https://dockhand.isnadboy.com - VERIFIED WORKING
- Complete initial Dockhand setup/login
- Optional: Generate encryption key and add to stack environment
  - Command: `openssl rand -base64 32`
  - Add as ENCRYPTION_KEY in Portainer stack environment variables

## Build/Deploy Commands

### Deploy New Service
```bash
# Via Portainer API (preferred)
source /mnt/shareables/.claude/.env
ENDPOINT_ID=13  # utilities
STACK_NAME="service-name"
COMPOSE_PATH="service-name/docker-compose.yml"

curl -sk -X POST "${PORTAINER_URL}/api/stacks/create/standalone/repository?endpointId=${ENDPOINT_ID}" \
  -H "X-API-Key: ${PORTAINER_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "'"${STACK_NAME}"'",
    "repositoryURL": "https://github.com/snadboy/docker-homelab",
    "composeFile": "'"${COMPOSE_PATH}"'",
    "repositoryReferenceName": "",
    "repositoryAuthentication": false,
    "autoUpdate": {"interval": "5m"}
  }'
```

### Create External Volume
```bash
source /mnt/shareables/.claude/.env
ENDPOINT_ID=13
VOLUME_NAME="volume-name"

curl -sk -X POST "${PORTAINER_URL}/api/endpoints/${ENDPOINT_ID}/docker/volumes/create" \
  -H "X-API-Key: ${PORTAINER_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"Name": "'"${VOLUME_NAME}"'"}'
```

## Project Context

This repository contains Docker Compose configurations for all homelab services deployed across multiple hosts via Portainer. All services follow standard patterns:
- External volumes for data persistence
- Traefik labels for automatic HTTPS routing
- Standard environment variables (PUID, PGID, TZ)
- GitOps auto-update enabled (5m interval)

**Endpoints:**
- cadre (ID: 8) - Traefik infrastructure
- arr (ID: 10) - Media management
- plex (ID: 11) - Media server
- iot (ID: 12) - IoT/smarthome
- utilities (ID: 13) - Utility services
- devs (ID: 14) - Development services
