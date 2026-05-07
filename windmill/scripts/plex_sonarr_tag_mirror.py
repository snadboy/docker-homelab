"""
Plex <-> Sonarr tag mirror.

Convention: any Sonarr tag OR Plex label whose name starts with `prefix`
(default "sync:") is treated as a shared tag. Membership is unioned across
both sides on every run, so tagging a show on either side propagates to the
other within one cycle.

Add-only: this script never removes a tag/label. Removing a shared tag
requires removing it on both sides manually.

Match key: TVDB ID (Plex stores tvdb://N in each show's Guid list).

Designed to be a Windmill Python script. Schedule every 5-10 minutes.
"""

import logging
from typing import Any

import httpx

try:
    import wmill
except ImportError:
    wmill = None

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


def main(
    sonarr_url: str = "",
    sonarr_api_key: str = "",
    plex_url: str = "",
    plex_token: str = "",
    prefix: str = "sync:",
    dry_run: bool = False,
) -> dict[str, Any]:
    if wmill is not None:
        sonarr_url = sonarr_url or wmill.get_variable("u/admin/SONARR_URL")
        sonarr_api_key = sonarr_api_key or wmill.get_variable("u/admin/SONARR_API_KEY")
        plex_url = plex_url or wmill.get_variable("u/admin/PLEX_URL")
        plex_token = plex_token or wmill.get_variable("u/admin/PLEX_TOKEN")
    if not all([sonarr_url, sonarr_api_key, plex_url, plex_token]):
        raise RuntimeError("Missing one of: sonarr_url, sonarr_api_key, plex_url, plex_token")

    sonarr = SonarrClient(sonarr_url.rstrip("/"), sonarr_api_key)
    plex = PlexClient(plex_url.rstrip("/"), plex_token)

    sync_tags = {t["id"]: t["label"] for t in sonarr.tags() if t["label"].startswith(prefix)}
    tag_id_by_label = {v: k for k, v in sync_tags.items()}
    series_list = sonarr.series()
    series_by_tvdb = {s["tvdbId"]: s for s in series_list if s.get("tvdbId")}

    sonarr_state: dict[str, set[int]] = {}
    for s in series_list:
        for tid in s.get("tags", []):
            if tid in sync_tags:
                sonarr_state.setdefault(sync_tags[tid], set()).add(s["tvdbId"])

    section_key = plex.find_tv_section_key()
    plex_shows = plex.shows_with_labels(section_key)
    plex_by_tvdb = {s["tvdbId"]: s for s in plex_shows}

    plex_state: dict[str, set[int]] = {}
    for show in plex_shows:
        for label in show["labels"]:
            if label.startswith(prefix):
                plex_state.setdefault(label, set()).add(show["tvdbId"])

    sonarr_changes: dict[int, set[int]] = {}
    plex_changes: dict[str, set[str]] = {}
    actions: list[str] = []
    errors: list[str] = []

    for label in sorted(set(sonarr_state) | set(plex_state)):
        s_set = sonarr_state.get(label, set())
        p_set = plex_state.get(label, set())
        union = s_set | p_set

        for tvdb_id in sorted(union - s_set):
            series = series_by_tvdb.get(tvdb_id)
            if series is None:
                errors.append(f"sonarr: tvdb:{tvdb_id} (label '{label}') not in Sonarr library")
                continue
            if label not in tag_id_by_label:
                if dry_run:
                    actions.append(f"[dry] +sonarr tag '{label}' (would create)")
                    tag_id_by_label[label] = -1
                else:
                    new_tag = sonarr.create_tag(label)
                    tag_id_by_label[label] = new_tag["id"]
                    actions.append(f"+sonarr tag '{label}' created (id={new_tag['id']})")
            sonarr_changes.setdefault(series["id"], set()).add(tag_id_by_label[label])
            actions.append(f"+sonarr {label} -> {series['title']} (tvdb:{tvdb_id})")

        for tvdb_id in sorted(union - p_set):
            show = plex_by_tvdb.get(tvdb_id)
            if show is None:
                errors.append(f"plex: tvdb:{tvdb_id} (label '{label}') not in Plex library")
                continue
            plex_changes.setdefault(show["ratingKey"], set()).add(label)
            actions.append(f"+plex {label} -> {show['title']} (tvdb:{tvdb_id})")

    for series_id, tag_ids in sonarr_changes.items():
        if -1 in tag_ids:
            continue
        series = next(s for s in series_list if s["id"] == series_id)
        merged = sorted(set(series.get("tags", [])) | tag_ids)
        if not dry_run:
            try:
                sonarr.update_series_tags(series_id, merged)
            except Exception as exc:
                errors.append(f"sonarr update {series['title']}: {exc}")

    for rating_key, labels_to_add in plex_changes.items():
        show = next(s for s in plex_shows if s["ratingKey"] == rating_key)
        merged = sorted(set(show["labels"]) | labels_to_add)
        if not dry_run:
            try:
                plex.set_labels(section_key, rating_key, merged)
            except Exception as exc:
                errors.append(f"plex update {show['title']}: {exc}")

    summary = {
        "dry_run": dry_run,
        "prefix": prefix,
        "shared_tags_seen": sorted(set(sonarr_state) | set(plex_state)),
        "actions": actions,
        "errors": errors,
        "counts": {
            "sonarr_series_updated": len(sonarr_changes),
            "plex_shows_updated": len(plex_changes),
            "sonarr_tags_known": len(sync_tags),
            "errors": len(errors),
        },
    }
    for line in actions:
        logger.info(line)
    for line in errors:
        logger.warning(line)
    return summary


class SonarrClient:
    def __init__(self, url: str, api_key: str):
        self.base = url
        self.headers = {"X-Api-Key": api_key}

    def tags(self) -> list[dict]:
        return self._get("/api/v3/tag")

    def create_tag(self, label: str) -> dict:
        return self._post("/api/v3/tag", {"label": label})

    def series(self) -> list[dict]:
        return self._get("/api/v3/series")

    def update_series_tags(self, series_id: int, tag_ids: list[int]) -> None:
        series = self._get(f"/api/v3/series/{series_id}")
        series["tags"] = tag_ids
        self._put(f"/api/v3/series/{series_id}", series)

    def _get(self, path: str) -> Any:
        r = httpx.get(f"{self.base}{path}", headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> Any:
        r = httpx.post(f"{self.base}{path}", headers=self.headers, json=body, timeout=30)
        r.raise_for_status()
        return r.json()

    def _put(self, path: str, body: dict) -> None:
        r = httpx.put(f"{self.base}{path}", headers=self.headers, json=body, timeout=30)
        r.raise_for_status()


class PlexClient:
    def __init__(self, url: str, token: str):
        self.base = url
        self.token = token
        self.headers = {"X-Plex-Token": token, "Accept": "application/json"}

    def find_tv_section_key(self) -> int:
        r = httpx.get(f"{self.base}/library/sections", headers=self.headers, timeout=30)
        r.raise_for_status()
        for d in r.json()["MediaContainer"]["Directory"]:
            if d.get("type") == "show":
                return int(d["key"])
        raise RuntimeError("No Plex TV (show) library section found")

    def shows_with_labels(self, section_key: int) -> list[dict]:
        r = httpx.get(
            f"{self.base}/library/sections/{section_key}/all",
            headers=self.headers,
            params={"includeGuids": 1, "type": 2},
            timeout=120,
        )
        r.raise_for_status()
        out = []
        for show in r.json().get("MediaContainer", {}).get("Metadata", []):
            tvdb_id = None
            for g in show.get("Guid", []):
                gid = g.get("id", "")
                if gid.startswith("tvdb://"):
                    try:
                        tvdb_id = int(gid.split("//", 1)[1].split("?", 1)[0])
                    except ValueError:
                        pass
                    break
            if tvdb_id is None:
                continue
            out.append({
                "ratingKey": str(show["ratingKey"]),
                "tvdbId": tvdb_id,
                "title": show.get("title", ""),
                "labels": [l["tag"] for l in show.get("Label", [])],
            })
        return out

    def set_labels(self, section_key: int, rating_key: str, labels: list[str]) -> None:
        params = {
            "type": 2,
            "id": rating_key,
            "label.locked": 1,
            "X-Plex-Token": self.token,
        }
        for i, label in enumerate(labels):
            params[f"label[{i}].tag.tag"] = label
        r = httpx.put(
            f"{self.base}/library/sections/{section_key}/all",
            params=params,
            timeout=30,
        )
        r.raise_for_status()
