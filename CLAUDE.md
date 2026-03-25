# docker-homelab

**Repo:** https://github.com/snadboy/docker-homelab (main)
**Local:** `/home/snadboy/projects/docker-homelab`
**Last Updated:** 2026-03-24

---

## Deployment

Stacks are managed by **Dockhand** (hawser agents on each host). Push to git → Dockhand detects → deploys automatically.

| Host | Dockhand Env ID | Key Stacks |
|------|-----------------|------------|
| utilities | 9 (was ansible-controller before migration) | semaphore, uptime-kuma, dockhand, gotify, homepage |
| arr | — | sonarr, radarr, prowlarr, overseerr, tautulli, agregarr, tracearr |
| fetch | — | sabnzbd |
| bedrock | — | pulse, pwa-appserver, windmill |
| cadre | — | traefik + traefik-http-provider, zigbee2mqtt (×3) |
| plex | — | plex |

---

## Key Stack Notes

**semaphore** (`semaphore/docker-compose.yml`)
- Port 3002 on utilities (3000 taken by Dockhand)
- `SEMAPHORE_ADMIN_PASSWORD` and `SEMAPHORE_ENCRYPTION_KEY` in `.env`
- Traefik label: `snadboy.revp.3002.domain=semaphore.isnadboy.com`

**traefik-http-provider** (`traefik-http-provider/docker-compose.yml`)
- `dns_search: ["tail65635.ts.net"]` required — container can't resolve Tailscale short hostnames without it
- Volume: `/var/lib/docker/volumes/traefik-http-provider-config/_data/` on cadre
- `devs` disabled in `ssh-hosts.yaml`

**plex** (`plex/docker-compose.yml`)
- `mem_limit: 12g` — prevents multivac OOM freezes
- No GPU passthrough (removed — caused hard host lockups)
- CPU-only transcoding, 10 cores

---

## Ansible

Located in `ansible/` subdirectory, used by Semaphore.

- **Inventory:** `ansible/inventory/hosts.yml`
- **Playbooks:** `ansible/playbooks/apt-update.yml`
- **Config:** `ansible/ansible.cfg` (ServerAliveInterval=30, pipelining on)
- **Schedule:** Biweekly `0 4 */14 * *` (Semaphore project "homelab")

- `iot` removed from inventory (VM 113 destroyed)
- `fetch` added to `ubuntu_vms` group
- `bedrock` added to `ubuntu_vms` group

---

## Last Updated: 2026-03-24
