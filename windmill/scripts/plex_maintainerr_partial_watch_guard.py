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

# Plex library section -> Maintainerr rule group, and what a "resume point" hangs off.
# For shows the offset lives on an episode and we protect its grandparent series;
# for movies the item itself carries the offset.
DEFAULT_TARGETS = [
    {"section": 2, "rule_group": 1, "collection": 1, "kind": "show"},
    {"section": 1, "rule_group": 2, "collection": 2, "kind": "movie"},
]


def main(
    targets: list = None,
    stale_days: int = 365,
    plex_url: str = "http://host-plex.isnadboy.com:32400",
    maintainerr_url: str = "https://maintainerr.swallow-spectrum.ts.net",
    dry_run: bool = False,
):
    """Protect part-watched media from Maintainerr's 'Leaving Soon' deletion.

    Every Maintainerr watch property is derived from Plex's *watch history*, and Plex
    only writes history on a COMPLETED view:
      - shows: sw_viewedEpisodes / sw_lastWatched read history directly
      - movies: viewCount comes from getWatchState(), which returns history.length and
        falls back to 0 when there is none
    So something you are partway through -- an episode you never finished, or a film
    you are 77% into -- looks exactly like "never watched" and gets queued for deletion.
    (Tautulli logs partial plays but drops anything under its 120s
    logging_ignore_interval, so it is not a reliable substitute.)

    The only complete signal is Plex's own resume point: per-item `viewOffset` plus
    `lastViewedAt`. This job reads those directly and maintains Maintainerr exclusions
    for anything with a recent resume point.

    Only exclusions this script created are ever retracted -- tracked in Windmill state,
    keyed by rule group -- so manual exclusions and those written by deletions are never
    touched.
    """
    # stale_days deliberately matches the rules' own 365-day window: anything you have
    # touched within the year is protected, and beyond that the rule's own definition of
    # "abandoned" applies even to a part-watched item. A shorter window silently leaves
    # part-watched media exposed (at 90d, a film 77% watched 110 days ago was unprotected).
    targets = targets or DEFAULT_TARGETS
    plex_url = plex_url.rstrip("/")
    # NOTE: deliberately not using the u/dschless/plex_url variable's old value -- it
    # pointed at the retired https://plex.isnadboy.com. Passed explicitly instead.
    plex_token = wmill.get_variable("u/dschless/plex_token")
    # token travels in a header, never the query string, so it can't leak into job logs
    plex_headers = {"Accept": "application/json", "X-Plex-Token": plex_token}
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - stale_days * 86400

    # state is {rule_group: [mediaServerId, ...]}; migrate the old flat-list format
    raw_state = wmill.get_state()
    if isinstance(raw_state, list):
        state = {"1": list(raw_state)}
    else:
        state = dict(raw_state or {})

    summary = {}

    for target in targets:
        section = target["section"]
        group = target["rule_group"]
        collection = target["collection"]
        kind = target["kind"]
        plex_type = 4 if kind == "show" else 1

        # --- 1. newest resume point per protectable item ---
        in_progress: dict[str, dict] = {}
        start, page = 0, 2000
        while True:
            r = requests.get(
                f"{plex_url}/library/sections/{section}/all",
                params={
                    "type": plex_type,
                    "X-Plex-Container-Start": start,
                    "X-Plex-Container-Size": page,
                },
                headers=plex_headers,
                timeout=120,
            )
            r.raise_for_status()
            mc = r.json()["MediaContainer"]
            items = mc.get("Metadata", []) or []
            if not items:
                break
            for item in items:
                if int(item.get("viewOffset") or 0) <= 0:
                    continue
                seen_at = int(item.get("lastViewedAt") or 0)
                if not seen_at:
                    continue
                if kind == "show":
                    key = str(item.get("grandparentRatingKey") or "")
                    label = item.get("grandparentTitle")
                    detail = f'S{item.get("parentIndex", "?")}E{item.get("index", "?")}'
                else:
                    key = str(item.get("ratingKey") or "")
                    label = f'{item.get("title")} ({item.get("year", "")})'
                    detail = ""
                if not key:
                    continue
                prior = in_progress.get(key)
                if prior is None or seen_at > prior["last_viewed"]:
                    in_progress[key] = {
                        "title": label,
                        "detail": detail,
                        "last_viewed": seen_at,
                        "at_min": round(int(item.get("viewOffset") or 0) / 60000, 1),
                    }
            start += len(items)
            if start >= int(mc.get("totalSize") or 0):
                break

        active = {k: v for k, v in in_progress.items() if v["last_viewed"] >= cutoff}

        # --- 2. reconcile against Maintainerr ---
        ex = requests.get(
            f"{maintainerr_url}/api/rules/exclusion",
            params={"rulegroupId": group},
            timeout=60,
        )
        ex.raise_for_status()
        existing = {str(e["mediaServerId"]) for e in ex.json()}

        managed = set(state.get(str(group), []))
        # housekeeping: drop anything we think we manage that is no longer excluded
        # (someone removed it by hand), so state can't grow stale forever
        managed &= existing
        to_add = [k for k in active if k not in existing]
        # only ever retract our own exclusions, and only once the resume point goes stale
        to_remove = [k for k in managed if k in existing and k not in active]

        added, removed, errors = [], [], []
        if not dry_run:
            for key in to_add:
                try:
                    resp = requests.post(
                        f"{maintainerr_url}/api/rules/exclusion",
                        json={"mediaId": int(key), "ruleGroupId": group},
                        timeout=60,
                    )
                    resp.raise_for_status()
                    managed.add(key)
                    added.append(active[key]["title"])
                except Exception as exc:
                    errors.append(f"add {key}: {exc}")
            for key in to_remove:
                try:
                    # Symmetric to the ADD. Excluding a show writes rows for the show AND
                    # every season/episode beneath it, so removal must expand the same way;
                    # deleting the single row by id would strand the children and leave the
                    # show permanently half-excluded.
                    # Must pass collectionId, NOT ruleGroupId: Maintainerr's
                    # removeExclusionWitData dereferences data.context.type without a null
                    # check on the non-collectionId branch, so a {mediaId, ruleGroupId}
                    # body 500s. The collectionId branch resolves the group itself and
                    # expands to the same child ids the ADD wrote.
                    resp = requests.post(
                        f"{maintainerr_url}/api/rules/exclusion",
                        json={
                            "mediaId": int(key),
                            "collectionId": collection,
                            "action": 1,  # ExclusionAction.REMOVE
                        },
                        timeout=90,
                    )
                    resp.raise_for_status()
                    managed.discard(key)
                    removed.append(in_progress.get(key, {}).get("title", key))
                except Exception as exc:
                    errors.append(f"remove {key}: {exc}")
            state[str(group)] = sorted(managed)

        summary[kind] = {
            "rule_group": group,
            "with_resume_point": len(in_progress),
            "actively_in_progress": len(active),
            "protected_now": len(managed),
            "added": added,
            "removed": removed,
            "would_add": [active[k]["title"] for k in to_add] if dry_run else None,
            "would_remove": (
                [in_progress.get(k, {}).get("title", k) for k in to_remove]
                if dry_run
                else None
            ),
            "errors": errors,
        }

    if not dry_run:
        wmill.set_state(state)

    return {"dry_run": dry_run, "targets": summary}
