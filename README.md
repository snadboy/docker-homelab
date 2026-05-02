# docker-homelab

Docker Compose stacks for the homelab, deployed via [Dockhand](https://github.com/finsys/dockhand) + Hawser agents.

## Hosts

| Host | Stacks |
|------|--------|
| **utilities** | actual-budget, dockhand, firefly-iii, gotify, homepage, semaphore, status-dashboard, termix, unifi-toolkit, uptime-kuma |
| **arr** | agregarr, autopulse, overseerr, prowlarr, radarr, slabels, sonarr, tautulli, tracearr |
| **fetch** | sabnzbd |
| **bedrock** | pulse |
| **cadre** | cloudflared-gotify, cloudflare-overseerr, cloudflare-plex, traefik-http-provider (includes traefik) |
| **plex** | plex |

## Stacks

### Media (arr + fetch)

| Stack | Host | Description |
|-------|------|-------------|
| `agregarr/` | arr | Plex collection manager |
| `autopulse/` | arr | Media automation trigger |
| `overseerr/` | arr | Media request management |
| `prowlarr/` | arr | Indexer manager |
| `radarr/` | arr | Movie management |
| `sabnzbd/` | fetch | Usenet downloader |
| `slabels/` | arr | Label generation |
| `sonarr/` | arr | TV series management |
| `tautulli/` | arr | Plex statistics and monitoring |
| `tracearr/` | arr | Media tracking |

### Infrastructure

| Stack | Host | Description |
|-------|------|-------------|
| `dockhand/` | utilities | Deployment manager |
| `homepage/` | utilities | Dashboard |
| `semaphore/` | utilities | Ansible UI, port 3002 |
| `status-dashboard/` | utilities | Nginx status page |
| `traefik-http-provider/` | cadre | Traefik reverse proxy + config provider via container discovery |
| `uptime-kuma/` | utilities | Uptime monitoring |

### Media Server

| Stack | Host | Description |
|-------|------|-------------|
| `plex/` | plex | Plex Media Server, 12GB mem limit, CPU-only transcoding |

### IoT / Home Automation

| Stack | Host | Description |
|-------|------|-------------|
| `zigbee2mqtt/` | cadre, utilities | Zigbee bridge (template — set Z2M_NAME/Z2M_PORT in .env) |

### Cloudflare Tunnels

| Stack | Host | Description |
|-------|------|-------------|
| `cloudflared-gotify/` | cadre | Tunnel for Gotify |
| `cloudflare-dockhand/` | utilities | Tunnel for Dockhand |
| `cloudflare-overseerr/` | cadre | Tunnel for Overseerr |
| `cloudflare-plex/` | cadre | Tunnel for Plex |

### Notifications

| Stack | Host | Description |
|-------|------|-------------|
| `gotify/` | utilities | Push notification server |

### Utilities / Tools

| Stack | Host | Description |
|-------|------|-------------|
| `actual-budget/` | utilities | Budgeting tool |
| `firefly-iii/` | utilities | Financial management |
| `pulse/` | bedrock | Proxmox cluster monitoring (requires agents on PVE/PBS nodes) |
| `termix/` | utilities | Web terminal |
| `unifi-toolkit/` | utilities | UniFi network tools |

## Other Directories

| Path | Description |
|------|-------------|
| `ansible/` | Ansible inventory and playbooks (biweekly apt updates via Semaphore) |
| `home-assistant/` | HA blueprints (Blackshome + custom) |
