# docker-homelab

**Repo:** https://github.com/snadboy/docker-homelab (main)
**Local:** `/home/snadboy/projects/docker-homelab`
**Last Updated:** 2026-05-02

---

## Deployment

Stacks are managed by **Dockhand** (hawser agents on each host). Push to git → Dockhand detects → deploys automatically.

| Host | Dockhand Env ID | Connection | Key Stacks |
|------|-----------------|------------|------------|
| utilities | 1 ("Utilities") | local socket — Dockhand runs on utilities itself, no agent needed | semaphore, uptime-kuma, dockhand, gotify, homepage, beszel hub, container-watchdog |
| arr | 3 | hawser-edge agent | sonarr, radarr, prowlarr, overseerr, tautulli, agregarr, tracearr |
| cadre | 7 | hawser-edge agent | traefik + traefik-http-provider, zigbee2mqtt (×3) |
| plex | 8 | hawser-edge agent | plex |
| bedrock | 11 | hawser-edge agent | pulse, pwa-appserver, windmill |
| fetch | 12 | hawser-edge agent | sabnzbd |

(Env 9 "ansible-controller" was deleted 2026-05-02 — it was a leftover from the
pre-migration ansible-controller VM. semaphore was reattached to env 1.)

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
- Container port 8090; host-side mapped to 8091 on utilities. Traefik label uses container port: `snadboy.revp.8090.domain=beszel.isnadboy.com`
- External named volume `beszel-data` (SQLite/PocketBase — pre-create with `docker volume create beszel-data` before first deploy)
- `APP_URL=https://beszel.isnadboy.com` baked into compose; admin user is created via web UI on first launch
- Agents installed by `ansible/playbooks/beszel-agent-install.yml` using the `beszel-agent` role; auth via universal token (hub Settings → Tokens) + hub SSH public key, set as `BESZEL_AGENT_KEY` / `BESZEL_AGENT_TOKEN` in `semaphore/.env` (matches the `BULLETIN_API_KEY` pattern; role reads via `lookup('env', ...)`)

---

## Ansible

Located in `ansible/` subdirectory, used by Semaphore.

- **Inventory:** `ansible/inventory/hosts.yml`
- **Playbooks:** `ansible/playbooks/apt-update.yml`, `ansible/playbooks/beszel-agent-install.yml`, `ansible/playbooks/technitium-update.yml`
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
- `pve-multivac` was dormant; restored 2026-05-01. ns-tertius (CT 112) DHCP IP drifted from .51→.53, fixed via UniFi reservation.

---

## Last Updated: 2026-05-02
