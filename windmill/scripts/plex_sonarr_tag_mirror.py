# requirements:
# httpx>=0.27.0
# wmill>=1.0.0

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
        sonarr_url = sonarr_url or wmill.get_variable("u/dschless/sonarr_url")
        sonarr_api_key = sonarr_api_key or wmill.get_variable("u/dschless/sonarr_api_key")
        plex_url = plex_url or wmill.get_variable("u/dschless/plex_url")
        plex_token = plex_token or wmill.get_variable("u/dschless/plex_token")
    if not all([sonarr_url, sonarr_api_key, plex_url, plex_token]):
        raise RuntimeError("Missing one of: sonarr_url, sonarr_api_key, plex_url, plex_token")

    sonarr = SonarrClient(sonarr_url.rstrip("/"), sonarr_api_key)
    plex = PlexClient(plex_url.rstrip("/"), plex_token)

    # Case-insensitive matching: Plex auto-capitalizes the first letter of
    # labels on write (e.g. "sync:foo" becomes "Sync:foo"), so we key the
    # union by lower-cased label and treat differing cases as the same tag.
    prefix_lc = prefix.lower()

    series_list = sonarr.series()
    series_by_tvdb = {s["tvdbId"]: s for s in series_list if s.get("tvdbId")}

    # sonarr_index[key_lc] = {"tag_id": int, "label": str (original case)}
    sonarr_index: dict[str, dict] = {}
    for t in sonarr.tags():
        if t["label"].lower().startswith(prefix_lc):
            sonarr_index[t["label"].lower()] = {"tag_id": t["id"], "label": t["label"]}

    sonarr_state: dict[str, set[int]] = {}
    for s in series_list:
        for tid in s.get("tags", []):
            for key_lc, info in sonarr_index.items():
                if info["tag_id"] == tid:
                    sonarr_state.setdefault(key_lc, set()).add(s["tvdbId"])
                    break

    section_key = plex.find_tv_section_key()
    plex_shows = plex.all_shows(section_key)
    plex_by_tvdb = {s["tvdbId"]: s for s in plex_shows}
    tvdb_by_rk = {s["ratingKey"]: s["tvdbId"] for s in plex_shows}

    # plex_index[key_lc] = "label" (original case from Plex's label registry)
    plex_index: dict[str, str] = {}
    plex_state: dict[str, set[int]] = {}
    for label_info in plex.labels_in_section(section_key, prefix_lc):
        key_lc = label_info["title"].lower()
        plex_index[key_lc] = label_info["title"]
        rks = plex.shows_for_label(section_key, label_info["key"])
        for rk in rks:
            tvdb = tvdb_by_rk.get(rk)
            if tvdb is not None:
                plex_state.setdefault(key_lc, set()).add(tvdb)

    sonarr_changes: dict[int, set[int]] = {}
    plex_changes: dict[str, set[str]] = {}
    actions: list[str] = []
    errors: list[str] = []

    for key_lc in sorted(set(sonarr_state) | set(plex_state)):
        s_set = sonarr_state.get(key_lc, set())
        p_set = plex_state.get(key_lc, set())
        union = s_set | p_set
        # Display label: prefer Plex's casing if it has one, else Sonarr's, else lowercase.
        display = plex_index.get(key_lc) or (sonarr_index.get(key_lc, {}).get("label")) or key_lc

        for tvdb_id in sorted(union - s_set):
            series = series_by_tvdb.get(tvdb_id)
            if series is None:
                errors.append(f"sonarr: tvdb:{tvdb_id} (label '{display}') not in Sonarr library")
                continue
            if key_lc not in sonarr_index:
                if dry_run:
                    actions.append(f"[dry] +sonarr tag '{display}' (would create)")
                    sonarr_index[key_lc] = {"tag_id": -1, "label": display}
                else:
                    new_tag = sonarr.create_tag(display)
                    sonarr_index[key_lc] = {"tag_id": new_tag["id"], "label": new_tag["label"]}
                    actions.append(f"+sonarr tag '{new_tag['label']}' created (id={new_tag['id']})")
            sonarr_changes.setdefault(series["id"], set()).add(sonarr_index[key_lc]["tag_id"])
            actions.append(f"+sonarr {display} -> {series['title']} (tvdb:{tvdb_id})")

        # When propagating to Plex, use Plex's stored casing if it exists for this
        # key. Otherwise use the source label (Plex will likely capitalize anyway).
        plex_label_to_write = plex_index.get(key_lc) or display
        for tvdb_id in sorted(union - p_set):
            show = plex_by_tvdb.get(tvdb_id)
            if show is None:
                errors.append(f"plex: tvdb:{tvdb_id} (label '{display}') not in Plex library")
                continue
            plex_changes.setdefault(show["ratingKey"], set()).add(plex_label_to_write)
            actions.append(f"+plex {plex_label_to_write} -> {show['title']} (tvdb:{tvdb_id})")

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
        if not dry_run:
            try:
                plex.add_labels(section_key, rating_key, sorted(labels_to_add))
            except Exception as exc:
                errors.append(f"plex update {show['title']}: {exc}")

    summary = {
        "dry_run": dry_run,
        "prefix": prefix,
        "shared_tags_seen": sorted(
            (plex_index.get(k) or (sonarr_index.get(k, {}).get("label")) or k)
            for k in (set(sonarr_state) | set(plex_state))
        ),
        "actions": actions,
        "errors": errors,
        "counts": {
            "sonarr_series_updated": len(sonarr_changes),
            "plex_shows_updated": len(plex_changes),
            "sonarr_tags_known": len(sonarr_index),
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

    def all_shows(self, section_key: int) -> list[dict]:
        """All shows in the section with TVDB IDs. Does not include labels —
        the /all endpoint omits Label fields. Use labels_with_tvdbs() instead
        to map labels to shows."""
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
            })
        return out

    def labels_in_section(self, section_key: int, prefix_lc: str) -> list[dict]:
        """Labels in the section whose name (case-insensitive) starts with prefix_lc.
        Returns [{key: <numeric label id>, title: <label string>}, ...]."""
        r = httpx.get(
            f"{self.base}/library/sections/{section_key}/label",
            headers=self.headers,
            timeout=30,
        )
        r.raise_for_status()
        return [
            {"key": d["key"], "title": d["title"]}
            for d in r.json().get("MediaContainer", {}).get("Directory", [])
            if d.get("title", "").lower().startswith(prefix_lc)
        ]

    def shows_for_label(self, section_key: int, label_key: str) -> list[str]:
        """Rating keys of shows tagged with the given numeric label id."""
        r = httpx.get(
            f"{self.base}/library/sections/{section_key}/all",
            headers=self.headers,
            params={"label": label_key, "type": 2},
            timeout=60,
        )
        r.raise_for_status()
        return [
            str(s["ratingKey"])
            for s in r.json().get("MediaContainer", {}).get("Metadata", [])
        ]

    def add_labels(self, section_key: int, rating_key: str, labels: list[str]) -> None:
        """Append labels to a show without replacing the existing set.
        Plex's tag.value syntax adds; tag.tag would replace."""
        if not labels:
            return
        params: list[tuple[str, str]] = [
            ("type", "2"),
            ("id", str(rating_key)),
            ("label.locked", "1"),
            ("X-Plex-Token", self.token),
        ]
        for label in labels:
            params.append(("label[].tag.tag.value", label))
        r = httpx.put(
            f"{self.base}/library/sections/{section_key}/all",
            params=params,
            timeout=30,
        )
        r.raise_for_status()
