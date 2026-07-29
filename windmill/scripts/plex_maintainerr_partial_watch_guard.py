# requirements:
# requests>=2.31.0
# wmill>=1.0.0

# Windmill path: f/plex/maintainerr_partial_watch_guard  (workspace w1)
# Schedule: "0 45 7,15,23 * * *" UTC — 15 min before Maintainerr's rule runs
#           (rules_handler_job_cron = "0 0-23/8 * * *" => 00:00/08:00/16:00 UTC)
# Deployed on the Windmill instance at bedrock; this file is the source of record.

import requests
import wmill
from datetime import datetime, timezone


def main(
    plex_section: int = 2,
    rule_group_id: int = 1,
    stale_days: int = 90,
    plex_url: str = "http://host-plex.isnadboy.com:32400",
    maintainerr_url: str = "https://maintainerr.swallow-spectrum.ts.net",
    dry_run: bool = False,
):
    """Protect part-watched shows from Maintainerr's 'Leaving Soon' deletion.

    Maintainerr's date properties all read Plex's *watch history*, which Plex only
    writes on a COMPLETED view. An episode you started but never finished leaves no
    history entry at all, so a show you are actively partway through can look
    abandoned and get queued for deletion. (Tautulli logs partial plays but drops
    anything under its 120s logging_ignore_interval, so it isn't a reliable
    substitute either.)

    The only complete signal is Plex's per-episode `viewOffset` (resume point) plus
    `lastViewedAt`. This job reads those directly and maintains Maintainerr
    exclusions for shows with a recent resume point.

    Only exclusions this script created are ever removed -- tracked in Windmill
    state -- so manual exclusions and those written by deletions are never touched.
    """
    # NOTE: deliberately not using the u/dschless/plex_url variable -- it still points at
    # https://plex.isnadboy.com, a retired Traefik-era hostname that is now NXDOMAIN.
    plex_url = plex_url.rstrip("/")
    plex_token = wmill.get_variable("u/dschless/plex_token")
    # token travels in a header, never the query string, so it can't leak into job logs
    plex_headers = {"Accept": "application/json", "X-Plex-Token": plex_token}
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - stale_days * 86400

    # --- 1. every episode with a resume point, newest partial watch per show ---
    in_progress: dict[str, dict] = {}
    start, page = 0, 2000
    while True:
        r = requests.get(
            f"{plex_url}/library/sections/{plex_section}/all",
            params={
                "type": 4,
                "X-Plex-Container-Start": start,
                "X-Plex-Container-Size": page,
            },
            headers=plex_headers,
            timeout=120,
        )
        r.raise_for_status()
        mc = r.json()["MediaContainer"]
        episodes = mc.get("Metadata", []) or []
        if not episodes:
            break
        for ep in episodes:
            if int(ep.get("viewOffset") or 0) <= 0:
                continue
            show_id = str(ep.get("grandparentRatingKey") or "")
            seen_at = int(ep.get("lastViewedAt") or 0)
            if not show_id or not seen_at:
                continue
            prior = in_progress.get(show_id)
            if prior is None or seen_at > prior["last_viewed"]:
                in_progress[show_id] = {
                    "show": ep.get("grandparentTitle"),
                    "episode": f'S{ep.get("parentIndex", "?")}E{ep.get("index", "?")}',
                    "last_viewed": seen_at,
                    "offset_min": round(int(ep.get("viewOffset") or 0) / 60000, 1),
                }
        start += len(episodes)
        if start >= int(mc.get("totalSize") or 0):
            break

    active = {sid: d for sid, d in in_progress.items() if d["last_viewed"] >= cutoff}

    # --- 2. reconcile against Maintainerr ---
    ex = requests.get(
        f"{maintainerr_url}/api/rules/exclusion",
        params={"rulegroupId": rule_group_id},
        timeout=60,
    )
    ex.raise_for_status()
    existing = {str(e["mediaServerId"]): e["id"] for e in ex.json()}

    managed = set(wmill.get_state() or [])

    to_add = [sid for sid in active if sid not in existing]
    # only ever retract our own exclusions, and only once the resume point goes stale
    to_remove = [sid for sid in managed if sid in existing and sid not in active]

    added, removed, errors = [], [], []
    if not dry_run:
        for sid in to_add:
            try:
                resp = requests.post(
                    f"{maintainerr_url}/api/rules/exclusion",
                    json={"mediaId": int(sid), "ruleGroupId": rule_group_id},
                    timeout=60,
                )
                resp.raise_for_status()
                managed.add(sid)
                added.append(active[sid]["show"])
            except Exception as exc:
                errors.append(f"add {sid}: {exc}")
        for sid in to_remove:
            try:
                # Symmetric to the ADD: excluding a show writes rows for the show AND every
                # season/episode beneath it, so removal must expand the same way. Deleting the
                # single show row by id (DELETE /api/rules/exclusion/{id}) would strand the
                # per-episode rows and leave the show permanently half-excluded.
                resp = requests.post(
                    f"{maintainerr_url}/api/rules/exclusion",
                    json={
                        "mediaId": int(sid),
                        "ruleGroupId": rule_group_id,
                        "action": 1,  # ExclusionAction.REMOVE
                    },
                    timeout=60,
                )
                resp.raise_for_status()
                managed.discard(sid)
                removed.append(in_progress.get(sid, {}).get("show", sid))
            except Exception as exc:
                errors.append(f"remove {sid}: {exc}")
        wmill.set_state(sorted(managed))

    return {
        "episodes_with_resume_point": len(in_progress),
        "actively_in_progress": len(active),
        "protected_now": len(managed),
        "added": added,
        "removed": removed,
        # on a dry run nothing is written, so surface the intended changes instead
        "would_add": [active[s]["show"] for s in to_add] if dry_run else None,
        "would_remove": (
            [in_progress.get(s, {}).get("show", s) for s in to_remove] if dry_run else None
        ),
        "errors": errors,
        "dry_run": dry_run,
        "detail": sorted(
            (
                {
                    "show": d["show"],
                    "episode": d["episode"],
                    "resumed": datetime.fromtimestamp(
                        d["last_viewed"], timezone.utc
                    ).strftime("%Y-%m-%d"),
                    "at_min": d["offset_min"],
                }
                for d in active.values()
            ),
            key=lambda x: x["resumed"],
            reverse=True,
        ),
    }
