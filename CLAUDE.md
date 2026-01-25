# docker-homelab Session Notes

## Repository Information
- **URL:** https://github.com/snadboy/docker-homelab
- **Local Path:** /home/snadboy/projects/docker-homelab
- **Main Branch:** main
- **Current Branch:** main
- **Latest Commit:** 34374ee - Add dockhand Docker management UI

## Recent Changes

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
