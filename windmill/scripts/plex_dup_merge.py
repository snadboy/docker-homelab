# requirements:
# requests>=2.31.0
# wmill>=1.0.0

# Windmill path: f/plex/plex_dup_merge  (workspace w1)
# Schedule: "0 15 */2 * * *" UTC — every 2 h at :15 (offset from the :00 scans)
# Deployed on the Windmill instance at bedrock; this file is the source of record.
#
# WHY THIS EXISTS (2026-08-14): Plex's scanner is not atomic per show — any two
# overlapping scans over a show with brand-new files can mint a DUPLICATE record
# for the same guid (observed 6x: Lucky x2, Rectify, Hightown, The Mandalorian,
# Silo). Prevention was narrowed as far as practical (FSEvents off, boot-ordered
# mounts, autoEmptyTrash off) but Sonarr Connect scans, the hourly scheduled
# scan, and the stereo newscan refresh can still overlap. This job makes the
# failure self-healing: find split records, merge into the fuller one.
#
# Merge rule (validated by every manual fix so far): keeper = record with the
# most episodes (leafCount); tie -> the OLDER record (lower ratingKey), which
# carries the watch history. Merging preserves watch state; Agregarr/Maintainerr
# collections re-point on their next sync. Old ratingKeys die on merge — that is
# expected and self-heals everywhere except scripts that pin ratingKeys.

import requests
import wmill


def main(plex_url: str = "http://host-plex.isnadboy.com:32400",
         dry_run: bool = False):
    plex_url = plex_url.rstrip("/")
    token = wmill.get_variable("u/dschless/plex_token")
    hdrs = {"Accept": "application/json"}

    merged, checked = [], 0
    for section, mtype in ((2, 2), (1, 1)):          # TV shows, Movies
        r = requests.get(f"{plex_url}/library/sections/{section}/all",
                         params={"type": mtype, "X-Plex-Token": token},
                         headers=hdrs, timeout=120)
        r.raise_for_status()
        items = r.json()["MediaContainer"].get("Metadata", [])
        checked += len(items)

        by_guid = {}
        for m in items:
            g = m.get("guid")
            if g:
                by_guid.setdefault(g, []).append(m)

        for g, group in by_guid.items():
            if len(group) < 2:
                continue
            group.sort(key=lambda m: (-(m.get("leafCount") or 0),
                                      int(m["ratingKey"])))
            keeper, dups = group[0], group[1:]
            ids = ",".join(d["ratingKey"] for d in dups)
            desc = (f"{keeper['title']}: keep {keeper['ratingKey']} "
                    f"({keeper.get('leafCount', '-')} leaves), merge {ids}")
            if not dry_run:
                mr = requests.put(
                    f"{plex_url}/library/metadata/{keeper['ratingKey']}/merge",
                    params={"ids": ids, "X-Plex-Token": token}, timeout=60)
                desc += f" -> HTTP {mr.status_code}"
            merged.append(desc)
            print(("DRY-RUN " if dry_run else "MERGED ") + desc)

    if not merged:
        print(f"no duplicate records ({checked} items checked)")
    return {"merged": merged, "items_checked": checked}
