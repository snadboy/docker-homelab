# requirements:
# requests>=2.31.0
# wmill>=1.0.0

# Windmill path: f/plex/airing_soon_tagger  (workspace w1)
# Schedule: "0 20 2,8,14,20 * * *" UTC (6-hourly, rolls the 7-day window)
# Pair: Agregarr sonarrtag config 953887 "Airing This Week" (tag 'airing-soon',
#       Plex collection 75580, TV library). This file is the source of record.

import requests
import wmill
from datetime import datetime, timedelta, timezone

TAG_LABEL = "airing-soon"
COLLECTION_NAME = "Airing This Week"
PLEX_TV_SECTION = 2


def main(
    window_days: int = 7,
    sonarr_url: str = "",
    plex_url: str = "http://host-plex.isnadboy.com:32400",
    dry_run: bool = False,
):
    """Maintain the 'Airing This Week' shelf: monitored shows whose next episode airs
    within `window_days`.

    Mechanism: sync the Sonarr tag 'airing-soon' to the qualifying set; Agregarr's
    10-minute sonarrtag sync mirrors the tag into the Plex collection. The show
    posters already carry the 'S4E2 - Thu, Jul 30' banner (Agregarr overlay
    templates 39/40), so this is purely a surfacing mechanism — clicking a member
    opens the ordinary show page. No placeholders, no fake episodes.

    Handles two failure modes learned the hard way (2026-07-30):
    - Sonarr CULLS a tag once nothing references it, so the tag is recreated by
      label on every run rather than pinned by id.
    - Agregarr's sonarrtag sync SKIPS when a tag yields zero items, stranding the
      last Plex collection member(s) forever. When the qualifying set is empty,
      this job empties the Plex collection itself.
    """
    sonarr_url = (sonarr_url or wmill.get_variable("u/dschless/sonarr_url")).rstrip("/")
    sonarr_key = wmill.get_variable("u/dschless/sonarr_api_key")
    plex_token = wmill.get_variable("u/dschless/plex_token")
    sh = {"X-Api-Key": sonarr_key}
    ph = {"Accept": "application/json", "X-Plex-Token": plex_token}

    # ---- qualifying set ----
    series = requests.get(f"{sonarr_url}/api/v3/series", headers=sh, timeout=60).json()
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=window_days)
    want = {}
    for s in series:
        na = s.get("nextAiring")
        if not (s.get("monitored") and na):
            continue
        dt = datetime.fromisoformat(na.replace("Z", "+00:00"))
        if now <= dt <= horizon:
            want[s["id"]] = {"title": s["title"], "airs": na[:10], "tags": s.get("tags", [])}

    # ---- ensure the tag exists (Sonarr culls unused tags) ----
    tags = requests.get(f"{sonarr_url}/api/v3/tag", headers=sh, timeout=30).json()
    tag = next((t for t in tags if t["label"] == TAG_LABEL), None)
    if tag is None and not dry_run:
        tag = requests.post(f"{sonarr_url}/api/v3/tag", headers=sh,
                            json={"label": TAG_LABEL}, timeout=30).json()
    tag_id = tag["id"] if tag else None

    # ---- diff current vs wanted tag membership ----
    have = {s["id"] for s in series if tag_id in (s.get("tags") or [])} if tag_id else set()
    to_add = sorted(set(want) - have)
    to_remove = sorted(have - set(want))

    if not dry_run and tag_id:
        for ids, op in ((to_add, "add"), (to_remove, "remove")):
            if ids:
                requests.put(f"{sonarr_url}/api/v3/series/editor", headers=sh,
                             json={"seriesIds": ids, "tags": [tag_id], "applyTags": op},
                             timeout=60).raise_for_status()

    # ---- empty-set guard: Agregarr strands the last member, so empty Plex ourselves ----
    emptied = []
    if not want and not dry_run:
        cols = requests.get(f"{plex_url}/library/sections/{PLEX_TV_SECTION}/collections",
                            headers=ph, timeout=30).json()["MediaContainer"].get("Metadata", [])
        for c in cols:
            if c.get("title") == COLLECTION_NAME:
                kids = requests.get(f"{plex_url}/library/collections/{c['ratingKey']}/children",
                                    headers=ph, timeout=30).json()["MediaContainer"].get("Metadata", [])
                for m in kids:
                    requests.delete(
                        f"{plex_url}/library/collections/{c['ratingKey']}/children/{m['ratingKey']}",
                        headers=ph, timeout=30)
                    emptied.append(m.get("title"))

    return {
        "dry_run": dry_run,
        "window_days": window_days,
        "qualifying": len(want),
        "tagged_added": [want[i]["title"] for i in to_add if i in want],
        "tag_removed_count": len(to_remove),
        "plex_members_emptied": emptied,
        "shelf": sorted((v["airs"], v["title"]) for v in want.values()),
    }
