# docker-homelab

**Repo:** https://github.com/snadboy/docker-homelab (main)
**Local:** `/home/snadboy/projects/docker-homelab`
**Last Updated:** 2026-07-29

---

## Deployment

Stacks are managed by **Dockhand** (hawser agents on each host). Push to git → Dockhand detects → deploys automatically.

| Host | Dockhand Env ID | Connection | Key Stacks |
|------|-----------------|------------|------------|
| utilities | 1 ("Utilities") | local socket — Dockhand runs on utilities itself, no agent needed | semaphore, uptime-kuma, dockhand, gotify, homepage, beszel hub, container-watchdog |
| arr | 3 | hawser-edge agent | sonarr, radarr, prowlarr, overseerr, tautulli, agregarr, tracearr, bazarr, maintainerr, wizarr |
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
- **Duplicate-record hardening (2026-08-03).** euler's kernel-update reboot (Aug 2 21:29 UTC) raced Plex's startup/Sonarr-triggered scans against the LXC's `soft` NFS mounts: missing paths → trash → `autoEmptyTrash` deleted show records → recreation scans raced → **duplicate show records** for the two actively-importing shows (Lucky (2026), Rectify). Fixed with `PUT /library/metadata/{keeper}/merge?ids={dup}`; find splits by scanning section for repeated `guid`. Hardened: `autoEmptyTrash=0` (Plex prefs — trash now needs explicit emptying after bulk deletes, see maintainerr runbook) + docker.service drop-in `wait-for-media.conf` in CT 107 (`RequiresMountsFor` both NFS mounts — no NAS, no Plex, no empty-tree scans).

**beszel** (`beszel/docker-compose.yml`) — system-metrics monitoring (complements Uptime Kuma)
- Container port 8090; host-side mapped to 8091 on utilities.
- External named volume `beszel-data` (SQLite/PocketBase — pre-create with `docker volume create beszel-data` before first deploy)
- `APP_URL=https://beszel.swallow-spectrum.ts.net` baked into compose; admin user is created via web UI on first launch
- Agents installed by `ansible/playbooks/beszel-agent-install.yml` using the `beszel-agent` role; auth via universal token (hub Settings → Tokens) + hub SSH public key, set as `BESZEL_AGENT_KEY` / `BESZEL_AGENT_TOKEN` in `semaphore/.env` (matches the `BULLETIN_API_KEY` pattern; role reads via `lookup('env', ...)`)

**maintainerr** (`maintainerr/docker-compose.yml`) — rules-based Plex library retention/cleanup (added 2026-07)
- `ghcr.io/maintainerr/maintainerr` (v3; migrated off deprecated `ghcr.io/jorenn92/maintainerr` v2.19 → v3.19 with a backup, 2026-07). Port 6246, external volume `maintainerr-data`. TS service `maintainerr.swallow-spectrum.ts.net` (DockTail).
- Plex connected via web UI (host-plex:32400 + admin token). **Two live rule groups**, both ARMED (`arrAction=Delete`, `listExclusions=1`, `forceSeerr=1`, `deleteAfterDays=30`): "Leaving Soon - TV" (collection id 1, Sonarr #1, Delete entire show) and "Leaving Soon - Movies" (collection id 2, Radarr #1). 30-day grace = Leaving Soon veto window.
- **Watched-episode properties (corrected 2026-07-29 — the earlier note here was imprecise).** Two different Plex properties exist and they disagree:
  - `sw_viewedEpisodes` (id 15) — episodes with a **watch-history** entry (`/status/sessions/history/all`, all accounts). Still better than Tautulli (history only from 2025-04), but Plex's own history only reaches ~2022 and it counts *partial* plays.
  - `sw_markedWatchedEpisodes` (id 45) — `viewedLeafCount`, Plex's **watched flag**. Permanent, includes manually-marked-watched. This is the watched/unwatched state the Plex UI shows.
  - Measured divergence: Crime Story 41 marked / 39 history; The Twilight Zone 155 marked / **24** history.
  - Use `sw_markedWatchedEpisodes < sw_episodes` for "has unwatched episodes" — using `sw_viewedEpisodes` there reads pre-2022 history gaps as unwatched and flags **fully-watched** shows as abandoned. Use `sw_viewedEpisodes == 0` for "nobody ever pressed play" (stricter, safer). `sw_lastWatched` (13) is history-based too and returns **null** with no history, so `BEFORE` fails safe.
- **TV rule definition** (rewritten 2026-07-29; hardened 2026-08-01 against BOTH re-import corruption classes), collection 1:
  - section 0 ("never watched"): `sw_viewedEpisodes == 0` AND `sw_lastEpisodeAddedAt` BEFORE 365d AND `sw_markedWatchedEpisodes == 0` — the last term added 2026-08-01: watched-pre-2022 shows have flags but no history (Pushing Daisies 22/22 marked, 0 history, was queued)
  - OR section 1 ("abandoned"): `sw_markedWatchedEpisodes < sw_episodes` AND `sw_lastWatched` BEFORE 365d AND `sw_lastEpisodeAddedAt` BEFORE 365d AND `sw_viewedEpisodes < sw_episodes` — the last term added 2026-08-01: the Jul-20 re-import WIPED watched flags on some shows while history survived (The Blacklist / A Suitable Boy / Overcompensating: full history, 0 flags, were queued). Both watch signals must now agree unwatched episodes remain.
  - Both branches keep the `sw_lastEpisodeAddedAt` staleness guard **by choice**: it's what stops freshly-downloaded, not-yet-watched shows being queued (without it the rule matched 384 shows / ~34 TB instead of 22 / 2.26 TB). Cost: abandoned-but-still-airing shows (For All Mankind, Bridgerton, Silo) are protected and never caught.
  - Sections: rules within a section are ANDed; each section joins the previous via the operator on that section's **first** rule (`null` for section 0, `"1"` = OR).
  - Verify any rule change with `POST /api/rules/test` `{rulegroupId, mediaId}` — it returns a per-section, per-rule breakdown with the actual values. This is how the fully-watched-shows bug above was caught.
- **`PUT /api/rules` is destructive if under-specified.** It replaces the whole group, and these reset silently when omitted: `deleteAfterDays` (→ null = **no grace period**), `listExclusions` (→ false), `forceSeerr` (→ false), `arrAction`, `sonarrSettingsId`, and the overlay fields (`collection.overlayEnabled`/`overlayTemplateId` → off/null). Safest pattern: `GET /api/rules/{id}`, rebuild the full payload from it (parse each `rules[].ruleJson`), change only what you mean to change. Changing `libraryId`/`dataType`/`manualCollection` **wipes all collection media and exclusions**. Back up first (`docker exec maintainerr cp /opt/data/maintainerr.sqlite /opt/data/maintainerr.sqlite.bak-<ts>`), pass those fields explicitly, verify in the DB after. Rebuild with `POST /api/rules/{id}/execute`, poll `GET /api/rules/execute/status` (key is `processingQueue`, there is no `running`).
- **2026-08-01 incident — prefer DIRECT DB INSERT for rule edits.** A full-payload PUT (built per the pattern above) still **failed to save AND tripped "crucial setting changed"** (suspected `libraryId` int-vs-string mismatch), wiping collection 1's media + **all 737 group-1 exclusions**. Restored from the pre-change backup (attach + `insert into exclusion select * from bak.exclusion where ruleGroupId=1`, container stopped). The safe path used since: stop maintainerr → docker cp DB out → `insert into rules (ruleJson, ruleGroupId, section, isActive) values (?,1,<section>,1)` → cp back (rm stale -wal/-shm) → start → verify with `/api/rules/test` → execute. Rule row order within a section is irrelevant for all-AND sections; section membership comes from BOTH the `section` column and the `section` key inside ruleJson.
- **Plex `addedAt` corruption — REPAIRED 2026-07-31.** A mass Plex re-import (~2026-07-20) had stamped 9,078 episodes + 318 shows with that day's date, making the Leaving Soon staleness guard over-protective. Fixed by copying **Sonarr's `episodefile.dateAdded`** (which survived — the event was Plex-side only) onto Plex `addedAt` for items inside the corruption window, field **locked** against re-corruption: 8,694 episodes + 291 shows written, 0 failures; spike collapsed to 291 genuinely-added episodes. True history: the real bulk import day is **2024-06-08** (2,607 eps). Result: Leaving Soon TV queue went 15 → **82 shows / 4.92 TB** (30-day clocks from 2026-07-31 — incl. Breaking Bad, I Love Lucy, The Mandalorian; review before ~Aug 30). Truth also *protects*: Hitchcock Hour's real last file is 2026-02-03, so it stays shielded. Edit API: `PUT /library/sections/2/all?type=4&id=<rk>&addedAt.value=<epoch>&addedAt.locked=1`. 18 shows (270 eps) no longer in Sonarr were left as-is.
- **Poster overlays enabled (2026-07-29):** both collections stamp members' posters with the custom **"Leaving Banner"** template (id 5, replaced Classic Pill 2026-07-30) — a full-width bottom bar, "Leaving <date>" at 96pt, matching the Agregarr Coming Soon banner style; counts down via Maintainerr's own cron. Template create gotcha: `elements` must be a JSON **array**, not a stringified array. Requires BOTH `overlay_settings.enabled=1` (global, `PUT /api/overlays/settings`) AND per-collection `overlayEnabled=1` + `overlayTemplateId` — **AND `overlay_settings.cronSchedule` must be set** (currently `10 0-23/4 * * *`, every 4h). With a null cron the engine logs "Overlay cron disabled" and stamps exactly once; Plex's nightly maintenance then refreshes agent artwork and silently wipes every pill with nothing to re-apply them (happened 2026-07-29). Force a re-stamp with `POST /api/overlays/process` `{"force": true}` — without `force`, items whose state says already-processed are skipped. Fully revertible: original posters stored in `overlay_item_state.originalPosterPath`, restored when an item leaves the collection; `POST /api/overlays/revert/{collectionId}` is the big undo. Two other seeded presets: Countdown Bar (2), Corner Badge (3).
- **Edition pills + branded collection posters (2026-07-29):** `windmill/scripts/plex_maintainerr_edition_pill_sync.py` (Windmill `f/plex/maintainerr_edition_pill_sync`, 00:30/08:30/16:30 UTC) stamps every Leaving Soon member with a Plex **Edition** pill ("Leaving Aug 28" — real deletion date) on the detail page, with store-and-restore of prior edition text (user edits win). Uses Plex TV Editions (released 2026-07, Plex Pass); the edit-API path preserves watch history, unlike `{edition-}` folder renames. It also re-renders the collection posters (Agregarr family pattern: red gradient + title + 2x2 member grid) on membership change, uploaded via `POST /api/collections/{id}/poster` so Maintainerr owns and pushes them. Gotcha: read membership from the **paged** `/api/collections/media/{id}/content/{p}` endpoint — the `media` array in `GET /api/collections` is truncated.
- An empty Leaving Soon collection means nothing is queued *right now* — **not** that the rules are off. They are armed and repopulate continuously.
- **Part-watched media is invisible to Maintainerr — hence the guard.** Plex only writes watch history on a **COMPLETED** view, and every Maintainerr watch property derives from that history:
  - shows — `sw_viewedEpisodes` / `sw_lastWatched` read history directly
  - movies — `viewCount` comes from `getWatchState()`, which returns `history.length` and falls back to 0 when there is none (it logs a warning for natively-watched-but-no-history items)

  So an episode started and never finished, or a film you are 77% through, reads as *never watched* and gets queued. Confirmed live against the real rules: 2001: A Space Odyssey (114/149 min), Hester Street (76/89), The Big Sleep 1946 (83/114), Killers of the Flower Moon and others all evaluated as deletable. Tautulli logs partial plays but drops anything under its `logging_ignore_interval = 120`s, so it is **not** a usable substitute (a 102-second play was missed entirely). The only complete signal is Plex's per-item `viewOffset` + `lastViewedAt`, which **no Maintainerr property exposes**.
  - Mitigation: `windmill/scripts/plex_maintainerr_partial_watch_guard.py`, deployed as `f/plex/maintainerr_partial_watch_guard` on the Windmill instance at bedrock, schedule `0 45 7,15,23 * * *` UTC (15 min before Maintainerr's `rules_handler_job_cron = 0 0-23/8 * * *`). It covers **both** libraries (TV section 2 → group 1, Movies section 1 → group 2) and maintains exclusions for anything with a resume point touched within 365 days — matching the rules' own window; a shorter one silently leaves part-watched media exposed.
  - It only ever retracts exclusions **it** created (tracked in Windmill state keyed by rule group), so manual vetoes are never touched.
  - **API gotcha:** removing an exclusion must pass `collectionId`, **not** `ruleGroupId` — Maintainerr's `removeExclusionWitData` dereferences `data.context.type` without a null check on the non-`collectionId` branch, so a `{mediaId, ruleGroupId}` body returns HTTP 500.
- **Exclusions are permanent opt-outs, not "remind me later", and they expand down the tree.** Excluding a show writes rows for the show **and every season/episode** beneath it (sharing `parent = <show ratingKey>`) — one show became 13 rows — so exclusion counts jump far faster than the number of titles you excluded. Deleting the single show row by id strands the children.
  - This is why the queues look small. As of 2026-07-29 the movie library had 508 titles older than a year, 467 of them never watched — but **445 were excluded during the manual review pass on 2026-07-28 14:00–15:00** (visible in the `collection_log` table: `Added a specific exclusion for "..."`), leaving just **2 movies queued**. TV sat at 13 shows / 0.50 TB.
  - Consequence: both rules now only catch **newly-aging** content — a trickle of titles crossing the 1-year mark that have not already been ruled on, not another multi-TB sweep. To reconsider a vetoed title its exclusion must be removed (UI, or a scripted bulk retraction).
  - Useful audit trail: `collection_log` in `maintainerr.sqlite` records every add/remove/handle with a timestamp — the fastest way to answer "why is this (not) in the queue".
- **v3 config gotcha:** the delete flags (`listExclusions`/`forceSeerr`/`arrAction`/`deleteAfterDays`) live on the **`collection`** table, NOT `rule_group`. `GET /api/rules` reads rule_group and shows them as `None` — read the `collection` table in `maintainerr.sqlite` (`docker cp maintainerr:/opt/data/maintainerr.sqlite`) for authoritative values.
- **One-time live purge (2026-07-28, grace bypassed just this once):** deleted **464 titles / ~9.7 TB** (316 movies via Radarr 1508→1192; 148 shows via Sonarr 993→845; TV 71→65.4 TB, Movies 20→16.0 TB). Driven **item-by-item** via `POST /api/collections/media/handle` `{collectionId, mediaId=ratingKey}` — this per-item endpoint **ignores grace** and deletes now, so the 30-day setting was never changed (no config to restore). 53 stale "ghost" rows (dead ratingKeys from a Plex rescan; content lives under new keys) returned `removed-missing` and freed nothing — expect ~10% of any tracked count to be such ghosts. Import-list exclusions written (Radarr 318 / Sonarr 393): to recover a deleted title, remove its exclusion in *arr before re-requesting or Seerr silently refuses the re-grab. Radarr/Sonarr **recycleBin is empty** → deletes are permanent unlinks, space freed immediately. After a bulk delete, run ONE full Plex section scan + emptyTrash per section (per-item Connect scans coalesce/drop).

**wizarr** (`wizarr/docker-compose.yml`) — Plex invitation / user-onboarding portal (added 2026-08-02)
- `ghcr.io/wizarrrr/wizarr:latest` (v2026.7.1), container port **5690** → host 5690 on arr, external volume `wizarr-data` mounted at `/data` (the entrypoint creates `/data/database`). TS service `wizarr.swallow-spectrum.ts.net` (DockTail); `APP_URL` is baked into compose so generated invite links use the tailnet name.
- **First run is unconfigured** — visit the URL and complete `/setup/` (create admin, then connect the Plex server) before handing out invites.
- **API key** (see shareables .env: `WIZARR_API_KEY`, `WIZARR_URL`). Header is `X-API-Key`; `GET /api/status` → `{users, invites, pending, expired}`, plus `/api/users` and `/api/invitations`. Swagger at `/api/docs/`.
- ⚠️ Wizarr stores only a bcrypt `key_hash` in the `api_key` table — **the plaintext key cannot be recovered from the container** (unlike every *arr app, whose key sits in a readable config). Losing it means minting a new one in the UI. A second copy lives at `~snadboy/.wizarr-api-key` on arr (mode 600) so the servarr hub probe can read it locally; recreate that file after any arr rebuild.
- Listed on the **servarr hub** (`servarr.swallow-spectrum.ts.net`) under a new "Access" card — shows pending-invite count, falling back to user count. See `ansible/roles/ts-static-serves/files/gen-hubs.py`.
- ⚠️ Docker's default `172.17–172.31` bridge pool is **exhausted on arr**, so `wizarr_default` fell through to `192.168.0.0/20`. No conflict today (the LAN is `192.168.86.0/24`), but the next stack added to arr will keep climbing that pool — set an explicit `default-address-pools` in `/etc/docker/daemon.json` before it reaches `192.168.86.0`.

**arr-dashboard** — **REMOVED 2026-08-01** (commit 4055ce6, superseded by live status on the servarr hub). Compose dir deleted; its `git_stacks` row (id 25, env 3) was left behind and fails the nightly deploy every night with `Compose file not found`. Same for `kiosk-dashboard` (id 19, removed 2026-05-02) and `status-dashboard` (id 13, removed 2026-05-22).
- `khak1s/arr-dashboard`, container port 3000 → **host 3005** (3000 taken by tracearr), external volume `arr-dashboard-data`. TS service `arr-dashboard.swallow-spectrum.ts.net`; WebAuthn pinned to that origin. First-run: create admin + add *arr instances via UI.

**Available / Upcoming Episodes** (Plex TV collections; 2026-07-31 redesign, replacing the day-old Episodes trio after real-world viewing found it noisy) —
- **Available Episodes - JaD/J/D** (renamed-in-place configs 831979/835232/835245→835235; Plex rks 62724/62734/62732): pool tag AND ≥1 downloaded-unwatched episode. If the show's next episode airs ≤30d (necessarily undownloaded), the tagger sets a detail-page **Edition chip** `S4E3 - Aug 6` — store-and-restore in `~/scripts/upcoming-chips.json` on arr; **Leaving Soon pills always win the slot** (chip job skips Maintainerr group-1 members via localhost:6246 paged endpoint). Dual-members (also on Upcoming) DO show the red banner here — see next bullet.
- **Upcoming Episodes** (config 960058, tag `upcoming-episodes`, autoPoster): monitored + has files + next **UNDOWNLOADED** episode ≤30d — regardless of watch state (2026-08-01: dual membership with Available is allowed; the caught-up-only rule was dropped by request). **Every Upcoming member gets the red banner** (2026-08-02 reversal, user decision after learning shows have ONE poster in Plex: banner-everywhere beats banner-gaps-in-Upcoming; dual-members therefore show banners on Available too — accepted). The patched `hasUnwatchedDownloaded` context field still exists but is no longer used in any condition. "Undownloaded" matters: pre-released boxsets (Granite Harbour S3 on iPlayer) have future *air* dates but files on disk — the tagger checks per-episode `hasFile` (NOT series `nextAiring`), and an agregarr-patch context field `sonarrNextAiringDownloaded` (season fileCount≥totalCount) suppresses the banner fields for the same case.
- **Banner template 39** (only one enabled for TV): condition = 3 OR-sections (daysUntilRelease / daysUntilNextEpisode / daysUntilNextSeason, each ≤30 AND monitored; watch-state gate removed 2026-08-02). The next-episode section was missing until 2026-08-01 (lost in the PUT-wipe incident) — symptom: banners only on season premieres, never mid-season. Template edits do NOT change item hashes — null `media_item_metadata.lastOverlayInputHash` for affected rks, then run the overlay job.
- ⚠️ **`applyOverlaysDuringSync` is OFF on all four shelf configs** (2026-08-01, deliberately): the collection-sync overlay path passes slim items with **no leafCount/viewedLeafCount** — with the 2026-08-02 gate removal this specific hazard is moot, but keep it off: the slim path can misevaluate any leaf-count-dependent condition that returns later. Banners stamp via the nightly 03:00 `overlay-application` job (or manual `POST /api/v1/settings/jobs/overlay-application/run`) — up to a day's lag for new members. Steady-state sweep is ~15 min (hash-skips); a full re-render after context/patch changes is SLOW (~15-20s/item, ~4h for 749 shows; RT fetches) — one died mid-run on an unexplained container restart, so verify completion, don't assume it.
- **Coming Soon** (118662) excludes all four configs → reduced to **new-series placeholders/trailers only** (returning premieres ≤30d land in Upcoming; CS's own window is 30d, so nothing returning remains).
- Tagger: `f/plex/jad_lifecycle_tagger` (30-min schedule) computes everything; tags by label with Agregarr `sonarrTagId` self-re-pointing.
- ⚠️ API-created Agregarr configs omit fields the UI always sets and later **validates** — config 960058 was missing `sonarrInstanceId` (empty instance dropdown) and `customTVTemplate` ("TV template is required" error blocking saves). When creating a config via API, copy the full field set from a UI-created sibling.
- **PRNZ / TMDB-orphan pipeline**: user created the TMDB entry (330416) + TVDB external id for Project Runway New Zealand; Agregarr's TVDB→TMDB lookup now succeeds, but the **Plex item still has only `tvdb://` in its Guid list** (Plex's cloud metadata lags new TMDB links by days) and Agregarr maps TMDB→Plex by GUID → `mapping completed found:0`. Self-heals when Plex ingests the link; a metadata refresh does NOT force it. Gotcha: with 0 mapped items the sync **refuses to modify the collection** ("No items to create collection from"), stranding stale members — removed Project Runway manually (`DELETE /library/collections/{rk}/children/{itemRk}`).
- ⚠️ **Agregarr template PUT wipes `applicationCondition` when omitted** (route explicitly nulls it) — a templateData-only PUT left banners condition-less for a day (part of the observed noise). Always send templateData AND applicationCondition together; verify via the PUT **response** (docker-cp'd sqlite reads miss WAL).

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

## Last Updated: 2026-07-29
