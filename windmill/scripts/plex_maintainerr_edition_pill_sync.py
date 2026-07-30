# requirements:
# requests>=2.31.0
# Pillow>=10.0.0
# wmill>=1.0.0

# Windmill path: f/plex/maintainerr_edition_pill_sync  (workspace w1)
# Schedule: "0 30 0,8,16 * * *" UTC — 30 min after Maintainerr's rule runs
#           (rules_handler_job_cron = "0 0-23/8 * * *" => 00:00/08:00/16:00 UTC)
# Deployed on the Windmill instance at bedrock; this file is the source of record.

import io
import hashlib

import requests
import wmill
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta

# Maintainerr collection -> Plex library mapping
TARGETS = [
    {"collection": 1, "plex_section": 2, "plex_type": 2, "subtitle": "TV"},
    {"collection": 2, "plex_section": 1, "plex_type": 1, "subtitle": "MOVIES"},
]

# Branded collection poster, following the Agregarr family pattern (Coming Soon /
# TV Requests): brand-colour gradient + title + 2x2 grid of member art. Colour is
# the same Maintainerr red (#B20710) the overlay pills use.
POSTER_W, POSTER_H = 1000, 1500
RED_TOP, RED_BOTTOM = (178, 7, 16), (46, 2, 5)


def _render_poster(title, subtitle, tiles, font_bytes):
    img = Image.new("RGB", (POSTER_W, POSTER_H))
    draw = ImageDraw.Draw(img)
    for y in range(POSTER_H):                       # vertical gradient
        f = y / POSTER_H
        row = tuple(int(RED_TOP[i] + (RED_BOTTOM[i] - RED_TOP[i]) * f) for i in range(3))
        draw.line([(0, y), (POSTER_W, y)], fill=row)
    big = ImageFont.truetype(io.BytesIO(font_bytes), 96)
    small = ImageFont.truetype(io.BytesIO(font_bytes), 44)
    w = draw.textlength(title, font=big)
    draw.text(((POSTER_W - w) / 2, 70), title, font=big, fill=(255, 255, 255))
    w = draw.textlength(subtitle, font=small)
    draw.text(((POSTER_W - w) / 2, 190), subtitle, font=small, fill=(255, 210, 210))
    # 2x2 grid of member posters, rounded corners
    tw, th, gap = 400, 600, 40
    x0 = (POSTER_W - (tw * 2 + gap)) // 2
    y0 = 280
    mask = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, tw, th], radius=28, fill=255)
    for i, tile in enumerate(tiles[:4]):
        try:
            t = Image.open(io.BytesIO(tile)).convert("RGB").resize((tw, th))
        except Exception:
            continue
        x = x0 + (i % 2) * (tw + gap)
        y = y0 + (i // 2) * (th + gap)
        img.paste(t, (x, y), mask)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def main(
    plex_url: str = "http://host-plex.isnadboy.com:32400",
    maintainerr_url: str = "https://maintainerr.swallow-spectrum.ts.net",
    pill_prefix: str = "Leaving ",
    force_poster: bool = False,
    dry_run: bool = False,
):
    """Sync Maintainerr 'Leaving Soon' membership onto Plex TV/movie Edition pills.

    Plex's Editions feature (TV editions released 2026-07, Plex Pass) renders
    `editionTitle` as a pill next to the content rating on the detail page — the page
    where someone actually decides to press play. Maintainerr's poster overlay is only
    visible while browsing shelves, so this puts the deletion warning where it matters:
    each queued item gets a pill like "Leaving Aug 28" (its real deletion date =
    collection addDate + deleteAfterDays).

    Store-and-restore: the previous editionTitle of every item we stamp is kept in
    Windmill state and restored when the item leaves the collection (vetoed or
    deleted). If a human changes the pill while we manage it, we adopt their value and
    walk away — user intent wins. Editing via the API is the watch-history-preserving
    path (equivalent to the Web edit UI, NOT the {edition-...} folder rename, which
    re-imports the show as a new item).

    Membership is read from the PAGED endpoint /api/collections/media/{id}/content/{p}
    — the media array embedded in GET /api/collections is truncated and must not be
    used.
    """
    plex_url = plex_url.rstrip("/")
    plex_token = wmill.get_variable("u/dschless/plex_token")
    plex_headers = {"Accept": "application/json", "X-Plex-Token": plex_token}

    # ---- Maintainerr: grace period per collection + full membership (paged) ----
    coll_info = {c["id"]: c for c in requests.get(
        f"{maintainerr_url}/api/collections", timeout=60).json()}

    def members(cid):
        out, page = [], 1
        while True:
            d = requests.get(
                f"{maintainerr_url}/api/collections/media/{cid}/content/{page}",
                timeout=60).json()
            items = d.get("items", []) or []
            out.extend(items)
            if not items or len(out) >= int(d.get("totalSize") or 0):
                return out
            page += 1

    # ---- desired pill per Plex ratingKey ----
    desired = {}   # rk -> (pill_text, section, type)
    for t in TARGETS:
        grace = int(coll_info.get(t["collection"], {}).get("deleteAfterDays") or 0)
        for m in members(t["collection"]):
            rk = str(m["mediaServerId"])
            add = (m.get("addDate") or "")[:10]
            try:
                due = datetime.fromisoformat(add) + timedelta(days=grace)
                text = f"{pill_prefix}{due.strftime('%b %-d')}"
            except ValueError:
                text = pill_prefix.strip()
            desired[rk] = (text, t["plex_section"], t["plex_type"])

    # ---- Plex: current editionTitle for every item, one listing per section ----
    current = {}
    for t in TARGETS:
        r = requests.get(
            f"{plex_url}/library/sections/{t['plex_section']}/all",
            params={"type": t["plex_type"]}, headers=plex_headers, timeout=120)
        r.raise_for_status()
        for it in r.json()["MediaContainer"].get("Metadata", []) or []:
            current[str(it["ratingKey"])] = (
                it.get("editionTitle") or "", t["plex_section"], t["plex_type"])

    def put_edition(rk, section, typ, value, lock):
        if dry_run:
            return
        r = requests.put(
            f"{plex_url}/library/sections/{section}/all",
            params={"type": typ, "id": rk,
                    "editionTitle.value": value,
                    "editionTitle.locked": 1 if lock else 0},
            headers=plex_headers, timeout=60)
        r.raise_for_status()

    state = dict(wmill.get_state() or {})
    managed = dict(state.get("managed", {}))

    stamped, restored, adopted, errors = [], [], [], []

    # add/update pills for current members
    for rk, (text, section, typ) in desired.items():
        if rk not in current:
            continue                       # stale ratingKey; nothing to stamp
        cur = current[rk][0]
        rec = managed.get(rk)
        try:
            if rec is None:
                put_edition(rk, section, typ, text, lock=True)
                managed[rk] = {"prev": cur, "set": text}
                stamped.append(f"{rk}:{text}")
            elif cur not in (rec["set"], text):
                adopted.append(rk)         # human changed it — their value wins
                managed.pop(rk, None)
            elif cur != text:
                put_edition(rk, section, typ, text, lock=True)
                rec["set"] = text
                stamped.append(f"{rk}:{text}")
        except Exception as exc:
            errors.append(f"stamp {rk}: {exc}")

    # restore pills for items that left the collection
    for rk in [k for k in managed if k not in desired]:
        rec = managed[rk]
        info = current.get(rk)
        try:
            if info is None:               # item deleted from Plex entirely
                managed.pop(rk)
                continue
            cur, section, typ = info
            if cur == rec["set"]:
                prev = rec.get("prev") or ""
                put_edition(rk, section, typ, prev, lock=bool(prev))
                restored.append(f"{rk}:{prev or '(cleared)'}")
            else:
                adopted.append(rk)         # human changed it — leave alone
            managed.pop(rk)
        except Exception as exc:
            errors.append(f"restore {rk}: {exc}")

    if not dry_run:
        wmill.set_state({"managed": managed})

    # ---- branded collection posters (re-render when membership changes) ----
    posters = {}
    poster_sig = dict(state.get("poster_sig", {}))
    font_bytes = None
    for t in TARGETS:
        cid = t["collection"]
        mem = [rk for rk, (_, sec, _typ) in desired.items() if sec == t["plex_section"]]
        sig = hashlib.sha1(",".join(sorted(mem)).encode()).hexdigest()
        if poster_sig.get(str(cid)) == sig and not force_poster:
            posters[cid] = "unchanged"
            continue
        if dry_run:
            posters[cid] = f"would re-render ({len(mem)} members)"
            continue
        try:
            if font_bytes is None:
                font_bytes = requests.get(
                    f"{maintainerr_url}/api/overlays/fonts/Inter-Bold.ttf", timeout=60).content
            tiles = []
            for rk in mem[:4]:
                m = requests.get(f"{plex_url}/library/metadata/{rk}",
                                 headers=plex_headers, timeout=30).json()
                thumb = m["MediaContainer"]["Metadata"][0].get("thumb")
                if thumb:
                    tiles.append(requests.get(f"{plex_url}{thumb}",
                                              headers=plex_headers, timeout=30).content)
            jpg = _render_poster("Leaving Soon", t["subtitle"], tiles, font_bytes)
            up = requests.post(f"{maintainerr_url}/api/collections/{cid}/poster",
                               files={"poster": ("leaving-soon.jpg", jpg, "image/jpeg")},
                               timeout=120)
            up.raise_for_status()
            poster_sig[str(cid)] = sig
            posters[cid] = f"rendered+uploaded ({len(tiles)} tiles) pushed={up.json().get('pushed')}"
        except Exception as exc:
            errors.append(f"poster {cid}: {exc}")
            posters[cid] = "FAILED"

    if not dry_run:
        wmill.set_state({"managed": managed, "poster_sig": poster_sig})

    return {
        "dry_run": dry_run,
        "posters": posters,
        "members": len(desired),
        "pills_managed": len(managed),
        "stamped": stamped,
        "restored": restored,
        "adopted_user_edits": adopted,
        "errors": errors,
    }
