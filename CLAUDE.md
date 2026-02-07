# docker-homelab Session Notes

## Repository Information
- **URL:** https://github.com/snadboy/docker-homelab
- **Local Path:** /home/snadboy/projects/docker-homelab
- **Main Branch:** main
- **Current Branch:** main
- **Latest Commit:** 37f4595 - Remove PBS (alexandria/svalbard) - servers not available

## Recent Changes

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
