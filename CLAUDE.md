# docker-homelab

**Repo:** https://github.com/snadboy/docker-homelab (main)
**Local:** `/home/snadboy/projects/docker-homelab`
**Last Updated:** 2026-04-30

---

## Deployment

Stacks are managed by **Dockhand** (hawser agents on each host). Push to git → Dockhand detects → deploys automatically.

| Host | Dockhand Env ID | Key Stacks |
|------|-----------------|------------|
| utilities | 9 (was ansible-controller before migration) | semaphore, uptime-kuma, dockhand, gotify, homepage, beszel |
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
- Migrated from multivac VM 110 to colossus LXC 107 on 2026-04-10 (multivac was crash-looping due to suspected Intel Raptor Lake Vmin Shift Instability)
- `mem_limit: 12g`
- Hardware transcoding via `/dev/dri` bind-mount (LXC, not VM-level VFIO). Uses colossus's Meteor Lake Intel Arc iGPU. Verified 8 simultaneous transcodes.
- Earlier GPU-passthrough attempt on multivac VM was reverted because VFIO caused hard host lockups; the LXC bind-mount path is fundamentally different and stable.

**beszel** (`beszel/docker-compose.yml`) — system-metrics monitoring (complements Uptime Kuma)
- Port 8090 on utilities. Traefik label: `snadboy.revp.8090.domain=beszel.isnadboy.com`
- External named volume `beszel-data` (SQLite/PocketBase — pre-create with `docker volume create beszel-data` before first deploy)
- `APP_URL=https://beszel.isnadboy.com` baked into compose; admin user is created via web UI on first launch
- Agents installed by `ansible/playbooks/beszel-agent-install.yml` using the `beszel-agent` role; auth via universal token (hub Settings → Tokens) + hub SSH public key, stored as `beszel_agent_key` / `beszel_agent_token` (Vault or Semaphore env)

---

## Ansible

Located in `ansible/` subdirectory, used by Semaphore.

- **Inventory:** `ansible/inventory/hosts.yml`
- **Playbooks:** `ansible/playbooks/apt-update.yml`, `ansible/playbooks/beszel-agent-install.yml`
- **Roles:** `ansible/roles/beszel-agent/` (Linux SSH + LXC pct-exec install paths in one role)
- **Config:** `ansible/ansible.cfg` (ServerAliveInterval=30, pipelining on)
- **Schedule:** Biweekly `0 4 */14 * *` (Semaphore project "homelab")
- **Bulletin summary:** `apt-update.yml` final play POSTs a single summary to `ansible/apt-update` on the bulletin board (requires `BULLETIN_API_KEY` in Semaphore env — see `semaphore/.env.example`). Per-host rows use `status=error|warn|ok` to colour-accent errors red and reboot-required orange. `beszel-agent-install.yml` posts to topic `ansible/beszel-agent` with the same shape.

- `iot` removed from inventory (VM 113 destroyed)
- `fetch` added to `ubuntu_vms` group
- `bedrock` added to `ubuntu_vms` group
- `host-plex` removed from `ubuntu_vms` (VM retired 2026-04-10)
- `plex-lxc` (CT 107 on colossus) added to `lxc_containers`
- `sdevs` added to `managed_locally` (unattended-upgrades; excluded from apt_hosts)
- `pve-multivac` dormant indefinitely — playbook fails on multivac and ns-tertius (CT 112) until restored

---

## Last Updated: 2026-04-30
