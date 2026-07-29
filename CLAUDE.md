# docker-homelab

**Repo:** https://github.com/snadboy/docker-homelab (main)
**Local:** `/home/snadboy/projects/docker-homelab`
**Last Updated:** 2026-07-28

---

## Deployment

Stacks are managed by **Dockhand** (hawser agents on each host). Push to git → Dockhand detects → deploys automatically.

| Host | Dockhand Env ID | Connection | Key Stacks |
|------|-----------------|------------|------------|
| utilities | 1 ("Utilities") | local socket — Dockhand runs on utilities itself, no agent needed | semaphore, uptime-kuma, dockhand, gotify, homepage, beszel hub, container-watchdog |
| arr | 3 | hawser-edge agent | sonarr, radarr, prowlarr, overseerr, tautulli, agregarr, tracearr, bazarr, maintainerr, arr-dashboard |
| edge | — | hawser-edge agent | zigbee2mqtt-laundry, zigbee2mqtt-office |
| plex | 8 | hawser-edge agent | plex |
| bedrock | 11 | hawser-edge agent | pulse, pwa-appserver, windmill |
| fetch | 12 | hawser-edge agent | sabnzbd |

> **Retired 2026-07:** Traefik and the **cadre** VM (106, pve-maxwell, stopped, onboot=0).
> All ingress is Tailscale VIP services (`*.swallow-spectrum.ts.net`, managed by DockTail
> labels / ts-static-serves). The `*.isnadboy.com` wildcard DNS record is intentionally
> gone — do not re-add it. `snadboy.revp.*` compose labels are inert leftovers.
> zigbee2mqtt moved off cadre: house → utilities, laundry + office → edge.

(Env 9 "ansible-controller" was deleted 2026-05-02 — it was a leftover from the
pre-migration ansible-controller VM. semaphore was reattached to env 1.)

---

## Key Stack Notes

**semaphore** (`semaphore/docker-compose.yml`)
- Port 3002 on utilities (3000 taken by Dockhand)
- `SEMAPHORE_ADMIN_PASSWORD` and `SEMAPHORE_ENCRYPTION_KEY` in `.env`

**traefik-http-provider** — RETIRED with Traefik (compose dir kept for history)
- `dns_search: ["tail65635.ts.net"]` required — container can't resolve Tailscale short hostnames without it
- Volume: `/var/lib/docker/volumes/traefik-http-provider-config/_data/` on cadre
- `devs` disabled in `ssh-hosts.yaml`

**plex** (`plex/docker-compose.yml`)
- Migrated from multivac VM 110 to colossus LXC 107 on 2026-04-10 (multivac was crash-looping due to suspected Intel Raptor Lake Vmin Shift Instability)
- `mem_limit: 12g`
- Hardware transcoding via `/dev/dri` bind-mount (LXC, not VM-level VFIO). Uses colossus's Meteor Lake Intel Arc iGPU. Verified 8 simultaneous transcodes.
- Earlier GPU-passthrough attempt on multivac VM was reverted because VFIO caused hard host lockups; the LXC bind-mount path is fundamentally different and stable.

**beszel** (`beszel/docker-compose.yml`) — system-metrics monitoring (complements Uptime Kuma)
- Container port 8090; host-side mapped to 8091 on utilities.
- External named volume `beszel-data` (SQLite/PocketBase — pre-create with `docker volume create beszel-data` before first deploy)
- `APP_URL=https://beszel.swallow-spectrum.ts.net` baked into compose; admin user is created via web UI on first launch
- Agents installed by `ansible/playbooks/beszel-agent-install.yml` using the `beszel-agent` role; auth via universal token (hub Settings → Tokens) + hub SSH public key, set as `BESZEL_AGENT_KEY` / `BESZEL_AGENT_TOKEN` in `semaphore/.env` (matches the `BULLETIN_API_KEY` pattern; role reads via `lookup('env', ...)`)

**maintainerr** (`maintainerr/docker-compose.yml`) — rules-based Plex library retention/cleanup (added 2026-07)
- `ghcr.io/maintainerr/maintainerr` (v3; migrated off deprecated `ghcr.io/jorenn92/maintainerr` v2.19 → v3.19 with a backup, 2026-07). Port 6246, external volume `maintainerr-data`. TS service `maintainerr.swallow-spectrum.ts.net` (DockTail).
- Plex connected via web UI (host-plex:32400 + admin token). **Two live rule groups**, both ARMED (`arrAction=Delete`, `listExclusions=1`, `forceSeerr=1`, `deleteAfterDays=30`): "Leaving Soon - TV" (collection id 1, Sonarr #1, Delete entire show) and "Leaving Soon - Movies" (collection id 2, Radarr #1). 30-day grace = Leaving Soon veto window.
- Maintainerr's "Amount of watched episodes" reads **all-user Plex-native** watch state — more accurate for "never watched" than Tautulli (whose history only starts 2025-04; Plex's own `/status/sessions/history/all` goes back to 2022, all accounts).
- **v3 config gotcha:** the delete flags (`listExclusions`/`forceSeerr`/`arrAction`/`deleteAfterDays`) live on the **`collection`** table, NOT `rule_group`. `GET /api/rules` reads rule_group and shows them as `None` — read the `collection` table in `maintainerr.sqlite` (`docker cp maintainerr:/opt/data/maintainerr.sqlite`) for authoritative values.
- **One-time live purge (2026-07-28, grace bypassed just this once):** deleted **464 titles / ~9.7 TB** (316 movies via Radarr 1508→1192; 148 shows via Sonarr 993→845; TV 71→65.4 TB, Movies 20→16.0 TB). Driven **item-by-item** via `POST /api/collections/media/handle` `{collectionId, mediaId=ratingKey}` — this per-item endpoint **ignores grace** and deletes now, so the 30-day setting was never changed (no config to restore). 53 stale "ghost" rows (dead ratingKeys from a Plex rescan; content lives under new keys) returned `removed-missing` and freed nothing — expect ~10% of any tracked count to be such ghosts. Import-list exclusions written (Radarr 318 / Sonarr 393): to recover a deleted title, remove its exclusion in *arr before re-requesting or Seerr silently refuses the re-grab. Radarr/Sonarr **recycleBin is empty** → deletes are permanent unlinks, space freed immediately. After a bulk delete, run ONE full Plex section scan + emptyTrash per section (per-item Connect scans coalesce/drop).

**arr-dashboard** (`arr-dashboard/docker-compose.yml`) — unified Sonarr/Radarr/Prowlarr dashboard (added 2026-07)
- `khak1s/arr-dashboard`, container port 3000 → **host 3005** (3000 taken by tracearr), external volume `arr-dashboard-data`. TS service `arr-dashboard.swallow-spectrum.ts.net`; WebAuthn pinned to that origin. First-run: create admin + add *arr instances via UI.

**Sonarr/Radarr → Plex** — both have a *Plex Media Server* Connect (updateLibrary on) so new arrivals/renames/deletes trigger an instant targeted Plex scan. `renameEpisodes`/`renameMovies` both ON. NOTE: for a *bulk* rename, do the renames then ONE full Plex section scan — the per-item burst gets coalesced/dropped by Plex, leaving stale paths (broken playback) until a full rescan.

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

## Last Updated: 2026-07-28
