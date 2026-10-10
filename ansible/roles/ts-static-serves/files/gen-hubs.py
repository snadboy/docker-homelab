#!/usr/bin/env python3
"""Generate the `home` page (index of every service) for Tailscale Services.
Runs on a ts-advertiser VM; gathers live data via Tailscale SSH to the nodes
(advertiser has tag:ssh). Writes self-contained HTML to OUTDIR.
The topic hubs -- proxmox (guests + datastores), servarr (live arr status),
containers, zigbee -- are modals on home, reachable as home…/#<hub>."""
import subprocess, html, os, datetime, json, urllib.request, urllib.parse, urllib.error
import concurrent.futures, socket, ssl
import base64, re, hashlib

TS = "swallow-spectrum.ts.net"
DOCKHAND = f"https://dockhand.{TS}/containers?search="  # + urlencoded container name
# TS_HUBS_OUTDIR lets a test run write somewhere other than the served directory.
OUTDIR = os.environ.get("TS_HUBS_OUTDIR", "/var/lib/ts-hubs")
ICONDIR = os.path.join(OUTDIR, "icons")
ICON_CDN = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/{}.svg"

PVE_NODES_FALLBACK = [("euler", "pve-euler"), ("gauss", "pve-gauss"), ("maxwell", "pve-maxwell")]  # seed + fallback; live list discovered from the cluster
PBS_NODES = [("alexandria", "pbs-alexandria"), ("svalbard", "pbs-svalbard")]

# Servarr: (label, svc-name, icon-slug on dashboard-icons)
SERVARR = [
    ("Indexers",   [("Prowlarr", "prowlarr", "prowlarr")]),
    ("Managers",   [("Sonarr", "sonarr", "sonarr"), ("Radarr", "radarr", "radarr"),
                    ("Bazarr", "bazarr", "bazarr"), ("Agregarr", "agregarr", None)]),
    ("Requests",   [("Overseerr", "overseerr", "overseerr")]),
    ("Access",     [("Wizarr", "wizarr", "wizarr")]),  # Plex invites / user onboarding
    ("Download",   [("SABnzbd", "sabnzbd", "sabnzbd")]),
    ("Monitoring", [("Tautulli", "tautulli", "tautulli"), ("Tracearr", "tracearr", None)]),
    ("Retention",  [("Maintainerr", "maintainerr", "maintainerr")]),  # "Leaving Soon"
    ("Tools",      [("GPU Benchmark", "gpu-benchmark", None)]),  # 4K transcode benchmark
]

# Docker hosts: (host, node-or-None, access) access = ("ssh",user,host) | ("pct",pvehost,vmid)
DOCKER_HOSTS = [
    ("utilities", "euler",   ("ssh", "snadboy", "utilities")),
    ("arr",       "gauss",   ("ssh", "snadboy", "arr")),
    ("fetch",     "gauss",   ("ssh", "snadboy", "fetch")),
    ("bedrock",   "maxwell", ("ssh", "snadboy", "bedrock")),
    ("plex-lxc",  "euler",   ("pct", "pve-euler", "107")),
    ("sdevs",     "faraday", ("ssh", "snadboy", "sdevs")),
]

# Hosts scanned for DockTail service labels by the `home` index. Deliberately a
# superset of DOCKER_HOSTS: `edge` runs a docktail agent (and the two retired Z2M
# shells), so a service re-enabled there must show up on the index even though
# edge is not yet a card on the containers hub.
DOCKTAIL_HOSTS = DOCKER_HOSTS + [("edge", "gauss", ("ssh", "snadboy", "edge"))]

def ssh(host, cmd, user="root", timeout=20):
    # Host keys are NOT pinned: the transport is the WireGuard-authenticated,
    # ACL-gated tailnet, and homelab VMs get rebuilt (new host keys) often enough
    # that accept-new would hard-fail with "REMOTE HOST IDENTIFICATION HAS CHANGED"
    # and silently blank a hub. /dev/null + no-checking keeps it self-healing.
    try:
        r = subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no",
                            "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR",
                            "-o", "ConnectTimeout=8", f"{user}@{host}", cmd],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None

def human(n):
    for u in ("B", "K", "M", "G", "T", "P"):
        if abs(n) < 1024: return f"{n:.0f}{u}" if u == "B" else f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}E"

# ---------- icons ----------
def icon_svg(slug):
    """Return inline SVG markup for an app (cached), or None."""
    if not slug:
        return None
    os.makedirs(ICONDIR, exist_ok=True)
    cache = os.path.join(ICONDIR, slug + ".svg")
    if not os.path.exists(cache):
        try:
            req = urllib.request.Request(ICON_CDN.format(slug),
                                         headers={"User-Agent": "ts-hubs"})
            data = urllib.request.urlopen(req, timeout=8).read()
            if b"<svg" in data:
                open(cache, "wb").write(data)
            else:
                return None
        except Exception:
            return None
    try:
        return open(cache).read()
    except Exception:
        return None

def icon_img(url):
    """A PNG icon an app serves itself, fetched once and inlined as a data URI."""
    os.makedirs(ICONDIR, exist_ok=True)
    cache = os.path.join(ICONDIR, re.sub(r"[^a-z0-9]+", "_", url.lower()) + ".png")
    if not os.path.exists(cache):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ts-hubs"})
            data = urllib.request.urlopen(req, timeout=8).read()
            if data[:8] != b"\x89PNG\r\n\x1a\n":
                return None
            open(cache, "wb").write(data)
        except Exception:
            return None
    try:
        return "data:image/png;base64," + base64.b64encode(open(cache, "rb").read()).decode()
    except Exception:
        return None

def icon_or_badge(label, slug):
    # A slug may also be inline SVG markup, or an https URL to the app's own PNG.
    if slug and slug.startswith("<svg"):
        return f'<span class="ico">{slug}</span>'
    if slug and slug.startswith("https://"):
        src = icon_img(slug)
        if src:
            return f'<span class="ico"><img src="{src}" alt=""></span>'
        slug = None
    svg = icon_svg(slug)
    if svg:
        return f'<span class="ico">{svg}</span>'
    return f'<span class="ico badge-ico">{html.escape(label[0])}</span>'

CSS = """
:root{--bg:#0f1216;--card:#171c22;--edge:#232b34;--fg:#e6edf3;--dim:#8b98a5;
--accent:#c9a227;--ok:#3fb950;--off:#f85149;--warn:#d29922;--link:#58a6ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:2rem}
.wrap{max-width:1100px;margin:0 auto}
h1{font-size:1.5rem;margin:0 0 .25rem;letter-spacing:.5px}
.sub{color:var(--dim);margin:0 0 1.75rem;font-size:.85rem}
h3.section{font-size:.8rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--accent);
margin:1.5rem 0 .8rem;padding-bottom:.35rem;border-bottom:1px solid var(--edge)}
h3.section:first-of-type{margin-top:0}
.grid{display:grid;gap:1rem;grid-template-columns:repeat(auto-fill,minmax(290px,1fr))}
.card{background:var(--card);border:1px solid var(--edge);border-radius:12px;padding:1.1rem 1.25rem}
.card h2{margin:0 0 .1rem;font-size:1.05rem}
.card h2 a{color:var(--link);text-decoration:none}.card h2 a:hover{text-decoration:underline}
.meta{color:var(--dim);font-size:.78rem;margin:0 0 .75rem}
.node-badge{display:inline-block;font-size:.62rem;font-weight:700;padding:.05rem .4rem;
border-radius:4px;background:#1f2b1f;color:var(--ok);margin-left:.4rem;vertical-align:middle}
ul{list-style:none;margin:.5rem 0 0;padding:0}
li{display:flex;align-items:center;gap:.5rem;padding:.22rem 0;font-size:.9rem}
.badge{font-size:.62rem;font-weight:700;padding:.05rem .35rem;border-radius:4px;background:var(--edge);color:var(--dim)}
.dot{width:8px;height:8px;border-radius:50%;flex:0 0 auto}
.dot.on{background:var(--ok)}.dot.warn{background:var(--warn)}.dot.off{background:var(--dim)}
.gname{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.gid{color:var(--dim);font-size:.72rem}
.foot{color:var(--dim);font-size:.72rem;margin-top:2rem;text-align:center}
a.svc{color:var(--link);text-decoration:none;display:flex;align-items:center;gap:.55rem;flex:1 1 auto;min-width:0}
a.svc:hover{text-decoration:underline}
.stat{color:var(--dim);font-size:.75rem;white-space:nowrap;flex:0 0 auto;margin-left:auto}
.stat.down{color:var(--off)}
.ico{width:22px;height:22px;flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center}
.ico svg{width:22px;height:22px}
.ico img{width:22px;height:22px;border-radius:5px}
.badge-ico{background:var(--edge);color:var(--fg);border-radius:5px;font-size:.7rem;font-weight:700}
.bar{height:7px;border-radius:4px;background:var(--edge);overflow:hidden;margin:.35rem 0 .1rem}
.bar > span{display:block;height:100%}
.bar-lo>span{background:var(--ok)}.bar-mid>span{background:var(--warn)}.bar-hi>span{background:var(--off)}
.usage{font-size:.78rem;color:var(--dim)}
/* Unreachable/absent hardware is informational, not an alarm: render the whole
   card gray so red stays meaningful for things that are actually broken. */
.card.unreach h2,.card.unreach h2 a,.card.unreach .gname,
.card.unreach .stat,.card.unreach .stat.down{color:var(--dim)}
.card.unreach .meta{color:#6b7681}
.search{display:flex;align-items:center;gap:.75rem;margin:-.5rem 0 1.5rem}
.search input{flex:0 1 360px;background:var(--card);border:1px solid var(--edge);
border-radius:8px;color:var(--fg);padding:.55rem .8rem;font-size:.9rem;outline:none}
.search input:focus{border-color:var(--link)}
.toplink{margin-left:auto;color:var(--link);text-decoration:none;font-size:.85rem;
border:1px solid var(--edge);border-radius:8px;padding:.45rem .75rem;white-space:nowrap}
.toplink:hover{border-color:var(--link);background:var(--card)}
a.cname{flex:1;color:var(--fg);text-decoration:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
a.cname:hover{color:var(--link);text-decoration:underline}
/* home index: the service NAME is the thing worth remembering (it is the URL),
   so it gets the monospace/primary slot and the description is secondary. */
.sname{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.85rem}
.sdesc{color:var(--dim);font-size:.72rem;margin-left:auto;text-align:right;flex:0 1 auto;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding-left:.5rem}
li.hit{background:#1b2430;border-radius:6px;box-shadow:0 0 0 1px var(--link) inset}
.cardhead{display:flex;align-items:baseline;gap:.75rem}
.cardhead h2{margin:0}
.hublink{margin-left:auto;flex:0 0 auto;font-size:.72rem;color:var(--link);
text-decoration:none;white-space:nowrap;border:1px solid var(--edge);
border-radius:6px;padding:.15rem .45rem}
.hublink:hover{border-color:var(--link);background:#1b2430}
.hublink .hsum{color:var(--dim);margin-right:.4rem}
.hublink .hname{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.hint{color:var(--dim);font-size:.72rem}
kbd{background:var(--edge);border-radius:4px;padding:.05rem .3rem;font-size:.68rem;
font-family:ui-monospace,monospace}
.cat{margin-top:1.5rem}.cat:first-of-type{margin-top:0}
.grid.wide{grid-template-columns:repeat(auto-fill,minmax(360px,1fr));align-items:start}
/* Uniform card height: the list gets a fixed height and scrolls, so a 15-row
   category and a 2-row one occupy the same box. The height is dropped while a
   filter is active (body.filtering) -- otherwise a search returning two rows would
   leave most of every card empty. */
.grid.wide .card{display:flex;flex-direction:column}
.grid.wide .card ul{height:18rem;overflow-y:auto;overscroll-behavior:contain;
padding-right:.35rem}
/* No body.filtering escape hatch: the cards stay equal while filtering too. JS
   equalise() then shrinks that shared height to the tallest VISIBLE result, so a
   filtered view is uniform without every card being a mostly-empty 18rem box. */
/* A visible scrollbar is the only cue that a list continues below the fold. */
.grid.wide .card ul::-webkit-scrollbar{width:8px}
.grid.wide .card ul::-webkit-scrollbar-track{background:transparent}
.grid.wide .card ul::-webkit-scrollbar-thumb{background:var(--edge);border-radius:4px}
.grid.wide .card ul::-webkit-scrollbar-thumb:hover{background:#313c48}
.grid.wide .card ul{scrollbar-width:thin;scrollbar-color:var(--edge) transparent}
.ccount{color:var(--dim);font-size:.72rem;font-weight:400;margin-left:.45rem;vertical-align:middle}
/* MUST come with !important. The UA sheet's [hidden]{display:none} loses to ANY
   author display rule regardless of specificity, and `li` and `.grid.wide .card`
   both set display here -- so without this the filter marks rows hidden and they
   stay on screen. Verified by computed style, not by querySelector: every
   `li[data-k]:not([hidden])` selector test passes either way. */
[hidden]{display:none!important}
/* Equalise header height whether or not the card has a hub link (the link's border
   + padding made those cards 2px taller). */
.cardhead{height:1.75rem;align-items:center}  /* fixed, not min-: baseline
alignment recomputes the flex line height and leaves a 1px drift between cards
that have a hub link and cards that do not. */
"""

def page(title, subtitle, body):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M %Z").strip()
    host = os.uname().nodename
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head><body><div class="wrap">
<h1>{html.escape(title)}</h1><p class="sub">{html.escape(subtitle)}</p>
{body}
<p class="foot">generated {now} on {html.escape(host)} · swallow-spectrum.ts.net</p>
</div></body></html>"""

# ---------- pve ----------
def pve_guests(host):
    out = ssh(host, "qm list 2>/dev/null; echo ===; pct list 2>/dev/null")
    if out is None:
        return False, []
    guests, section = [], "VM"
    for ln in out.splitlines():
        if ln.strip() == "===":
            section = "CT"; continue
        p = ln.split()
        if not p or p[0] == "VMID":
            continue
        if section == "VM" and len(p) >= 3:
            guests.append(("VM", p[0], p[1], p[2]))
        elif section == "CT" and len(p) >= 3:
            guests.append(("CT", p[0], p[2], p[1]))
    return True, guests

def discover_pve_nodes():
    """Live [(short, pve-host)] from the cluster so new nodes appear automatically.
    Seeds from the fallback hosts (any one reachable returns the whole cluster);
    falls back to the static list if discovery fails, so a cluster hiccup never
    blanks the hub."""
    for _, seed in PVE_NODES_FALLBACK:
        out = ssh(seed, "pvesh get /nodes --output-format json 2>/dev/null")
        if not out:
            continue
        try:
            nodes = json.loads(out)
        except Exception:
            continue
        found = []
        for n in nodes:
            node = n.get("node")
            if not node:
                continue
            short = node[4:] if node.startswith("pve-") else node
            found.append((short, node))
        if found:
            return sorted(found)
    return PVE_NODES_FALLBACK

def pve_cards():
    cards, node_count, guest_count = [], 0, 0
    data = HUB_DATA.setdefault("proxmox", {}).setdefault("nodes", [])
    for name, host in discover_pve_nodes():
        node_count += 1
        ok, guests = pve_guests(host)
        data.append({"name": name, "ok": ok, "guests": guests})
        url = f"https://{name}.{TS}"
        rows = ""
        for kind, vmid, gname, status in sorted(guests, key=lambda g: (g[0], g[2].lower())):
            on = "on" if status == "running" else "off"
            rows += (f'<li><span class="dot {on}"></span><span class="badge">{kind}</span>'
                     f'<span class="gname">{html.escape(gname)}</span><span class="gid">{vmid}</span></li>')
        state = f"{len(guests)} guests" if ok else '<span style="color:var(--off)">unreachable</span>'
        guest_count += len(guests)
        cards.append(f'<div class="card"><h2><a href="{url}">{html.escape(name)}</a></h2>'
                     f'<p class="meta">Proxmox VE · {state}</p><ul>{rows}</ul></div>')
    return '<div class="grid">' + "".join(cards) + "</div>", node_count, guest_count

# ---------- pbs ----------
def pbs_stores(host):
    out = ssh(host, "proxmox-backup-manager datastore list --output-format json 2>/dev/null")
    if out is None:
        return False, []
    try:
        stores = json.loads(out)
    except Exception:
        return True, []
    result = []
    for d in stores:
        name, path = d.get("name", "?"), d.get("path", "")
        usage = ssh(host, f"df -B1 --output=size,used,pcent {path} 2>/dev/null | tail -1")
        size = used = pct = None
        if usage:
            f = usage.split()
            if len(f) >= 3:
                size, used = int(f[0]), int(f[1])
                pct = int(f[2].rstrip("%"))
        result.append((name, size, used, pct))
    return True, result

def pbs_cards():
    cards = []
    data = HUB_DATA.setdefault("proxmox", {}).setdefault("pbs", [])
    for name, host in PBS_NODES:
        ok, stores = pbs_stores(host)
        data.append({"name": name, "ok": ok, "stores": stores})
        url = f"https://{name}.{TS}"
        rows = ""
        for sname, size, used, pct in stores:
            if pct is None:
                rows += f'<li><span class="badge">DS</span><span class="gname">{html.escape(sname)}</span></li>'
            else:
                cls = "bar-hi" if pct >= 85 else "bar-mid" if pct >= 70 else "bar-lo"
                rows += (f'<li style="display:block"><div style="display:flex;gap:.5rem">'
                         f'<span class="badge">DS</span><span class="gname">{html.escape(sname)}</span>'
                         f'<span class="usage">{pct}%</span></div>'
                         f'<div class="bar {cls}"><span style="width:{pct}%"></span></div>'
                         f'<div class="usage">{human(used)} / {human(size)} used</div></li>')
        state = f"{len(stores)} datastores" if ok else '<span style="color:var(--off)">unreachable</span>'
        cards.append(f'<div class="card"><h2><a href="{url}">{html.escape(name)}</a></h2>'
                     f'<p class="meta">Proxmox Backup Server · {state}</p><ul>{rows}</ul></div>')
    return '<div class="grid">' + "".join(cards) + "</div>"

def render_proxmox():
    pve_html, nodes, guests = pve_cards()
    body = (f'<h3 class="section">Virtualization</h3>{pve_html}'
            f'<h3 class="section">Backup</h3>{pbs_cards()}')
    HUB_SUMMARY["proxmox"] = f"{guests} guests · {nodes} nodes"
    return page("Proxmox", "Virtualization cluster and backup servers — click any node for its web UI.", body)

# ---------- servarr live status ----------
# Each app's status + one at-a-glance metric is gathered by SSHing to the host it
# runs on and reading the API key straight out of the running container, then
# curling localhost. Keeps secrets on the media host (where they already live) —
# nothing is copied onto the advertiser VM or into the repo. All *arr apps live on
# `arr`; SABnzbd on `fetch`. Icon-only apps (Prowlarr/Bazarr/Agregarr/Tracearr)
# get an up/down dot but no metric.
#
# Wizarr is the one exception to "read the key out of the container": it stores
# only a bcrypt `key_hash`, so the plaintext key can't be recovered from /data.
# Its key lives in `~snadboy/.wizarr-api-key` on `arr` (mode 600, also recorded in
# shareables .env as WIZARR_API_KEY). If that file goes missing after a rebuild the
# probe degrades to an up/down dot — it never reports Wizarr as down.
_PROBE_ARR = r'''
gx(){ docker exec "$1" cat "$2" 2>/dev/null; }
xk(){ gx "$1" /config/config.xml | grep -oiE '<ApiKey>[^<]+' | sed 's/<ApiKey>//i'; }
code(){ curl -s -o /dev/null -w '%{http_code}' -m5 "http://localhost:$1/" 2>/dev/null; }
num(){ grep -oE "\"$1\" *: *\"?[0-9]+" | head -1 | grep -oE '[0-9]+$'; }
k=$(xk sonarr); q=$(curl -s -m6 "http://localhost:8989/api/v3/queue?apikey=$k" | num totalRecords); echo "sonarr|$(code 8989)|queue=${q}"
k=$(xk radarr); q=$(curl -s -m6 "http://localhost:7878/api/v3/queue?apikey=$k" | num totalRecords); echo "radarr|$(code 7878)|queue=${q}"
echo "prowlarr|$(code 9696)|"
echo "bazarr|$(code 6767)|"
echo "agregarr|$(code 7171)|"
echo "tracearr|$(code 3000)|"
k=$(gx overseerr /app/config/settings.json | grep -oE '"apiKey": *"[^"]+' | head -1 | sed -E 's/.*"apiKey": *"//')
p=$(curl -s -m6 -H "X-Api-Key: $k" http://localhost:5055/api/v1/request/count | num pending); echo "overseerr|$(code 5055)|pending=${p}"
k=$(gx tautulli /config/config.ini | grep -E '^api_key' | head -1 | sed 's/.*= *//')
s=$(curl -s -m6 "http://localhost:8181/api/v2?apikey=$k&cmd=get_activity&out_type=json" | num stream_count); echo "tautulli|$(code 8181)|streams=${s}"
k=$(cat "$HOME/.wizarr-api-key" 2>/dev/null)
w=$(curl -s -m6 -H "X-API-Key: $k" http://localhost:5690/api/status)
echo "wizarr|$(code 5690)|users=$(printf '%s' "$w" | num users);pending=$(printf '%s' "$w" | num pending)"
l=$(curl -s -m6 http://localhost:6246/api/collections | python3 -c "import sys,json;d=json.load(sys.stdin);print(sum(c.get('mediaCount',0) for c in d if str(c.get('title','')).lower().startswith('leaving soon') and c.get('isActive')))" 2>/dev/null)
echo "maintainerr|$(code 6246)|leaving=${l}"
'''

_PROBE_FETCH = r'''
k=$(docker exec sabnzbd cat /config/sabnzbd.ini 2>/dev/null | grep -E '^api_key' | head -1 | sed 's/.*= *//')
j=$(curl -s -m6 "http://localhost:8080/api?mode=queue&output=json&apikey=$k")
st=$(printf '%s' "$j" | grep -oE '"status":"[^"]+' | head -1 | sed 's/.*"//')
kb=$(printf '%s' "$j" | grep -oE '"kbpersec":"[^"]+' | sed 's/.*"//')
sl=$(printf '%s' "$j" | grep -oE '"noofslots":[0-9]+' | grep -oE '[0-9]+')
echo "sabnzbd|$(curl -s -o /dev/null -w '%{http_code}' -m5 http://localhost:8080/)|status=${st};kbps=${kb};slots=${sl}"
'''

def _rate(kbps):
    try:
        kb = float(kbps)
    except Exception:
        return ""
    return f"{kb/1024:.1f} MB/s" if kb >= 1024 else f"{kb:.0f} KB/s"

def _fmt_stat(svc, kv):
    if svc in ("sonarr", "radarr"):
        q = kv.get("queue")
        return f"{q} in queue" if q not in (None, "") else ""
    if svc == "overseerr":
        p = kv.get("pending")
        return f"{p} pending" if p not in (None, "") else ""
    if svc == "tautulli":
        s = kv.get("streams")
        if s in (None, ""):
            return ""
        return f"{s} streaming" if s != "0" else "idle"
    if svc == "maintainerr":
        l = kv.get("leaving")
        return f"{l} leaving soon" if l not in (None, "") else ""
    if svc == "wizarr":
        p, u = kv.get("pending"), kv.get("users")
        if p not in (None, "", "0"):
            return f"{p} invite{'' if p == '1' else 's'} pending"
        return f"{u} user{'' if u == '1' else 's'}" if u not in (None, "") else ""
    if svc == "sabnzbd":
        st = kv.get("status", "")
        if st == "Downloading":
            r = _rate(kv.get("kbps", ""))
            sl = kv.get("slots", "0")
            return f"↓ {r} · {sl} queued" if r else f"{sl} queued"
        return "idle" if st in ("Idle", "", None) else st.lower()
    return ""

def _parse_probe(out):
    res = {}
    if not out:
        return res
    for ln in out.splitlines():
        parts = ln.split("|")
        if len(parts) < 2 or not parts[0].strip():
            continue
        svc, code = parts[0].strip(), parts[1].strip()
        kv = {}
        if len(parts) >= 3 and parts[2].strip():
            for pair in parts[2].split(";"):
                if "=" in pair:
                    a, b = pair.split("=", 1)
                    kv[a.strip()] = b.strip()
        res[svc] = {"up": bool(code) and code != "000", "stat": _fmt_stat(svc, kv), "kv": kv}
    return res

# gpu-benchmark is the one servarr app not on a docker host we SSH into: it runs
# in the plex LXC (CT 107), which has no Tailscale node. The advertiser can reach
# it directly on the LAN, so probe it locally instead of over SSH.
GPU_BENCH_URL = "http://192.168.86.40:8088/"

def _http_up(url, timeout=6):
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True   # any HTTP response means it is serving
    except Exception:
        return False

def servarr_status():
    st = {}
    st.update(_parse_probe(ssh("arr", _PROBE_ARR, user="snadboy", timeout=50)))
    st.update(_parse_probe(ssh("fetch", _PROBE_FETCH, user="snadboy", timeout=30)))
    st["gpu-benchmark"] = {"up": _http_up(GPU_BENCH_URL), "stat": ""}
    return st

# ---------- servarr ----------
def render_servarr():
    status = servarr_status()
    HUB_DATA["servarr"] = {"status": status}
    cards = []
    for heading, items in SERVARR:
        links = ""
        for label, svc, slug in items:
            st = status.get(svc, {})
            up = st.get("up", False)
            stat = st.get("stat", "")
            if not up:
                stat_html = '<span class="stat down">down</span>'
            elif stat:
                stat_html = f'<span class="stat">{html.escape(stat)}</span>'
            else:
                stat_html = ""
            links += (f'<li><span class="dot {"on" if up else "off"}"></span>'
                      f'<a class="svc" href="https://{svc}.{TS}">'
                      f'{icon_or_badge(label, slug)}<span class="gname">{html.escape(label)}</span></a>'
                      f'{stat_html}</li>')
        cards.append(f'<div class="card"><h2>{html.escape(heading)}</h2><ul>{links}</ul></div>')
    n_up = sum(1 for v in status.values() if v.get("up"))
    HUB_SUMMARY["servarr"] = f"{n_up}/{len(status)} up"
    return page("Media Automation",
                "The Servarr media stack — live status; green = up, grey = down. Click any service to open it.",
                '<div class="grid">' + "".join(cards) + "</div>")

# ---------- containers ----------
def docker_ps(access):
    if access[0] == "ssh":
        _, user, host = access
        out = ssh(host, "docker ps -a --format '{{.Names}}|{{.State}}|{{.Status}}' 2>/dev/null", user=user)
    else:
        _, pvehost, vmid = access
        out = ssh(pvehost, f"pct exec {vmid} -- docker ps -a --format '{{{{.Names}}}}|{{{{.State}}}}|{{{{.Status}}}}' 2>/dev/null")
    if out is None:
        return None
    rows = []
    for ln in out.splitlines():
        p = ln.split("|")
        if len(p) >= 2:
            rows.append((p[0], p[1], p[2] if len(p) > 2 else ""))
    return rows

DOCKHAND_HOSTS = {"utilities", "arr", "fetch", "cadre", "bedrock", "plex-lxc"}

SEARCH_JS = """
<script>
const q=document.getElementById('q'),cnt=document.getElementById('cnt');
function flt(){
 const t=q.value.trim().toLowerCase();let n=0;
 document.querySelectorAll('.card[data-host]').forEach(card=>{
  const hostMatch=!t||card.dataset.host.includes(t);let shown=0;
  card.querySelectorAll('li[data-name]').forEach(li=>{
   const m=!t||hostMatch||li.dataset.name.includes(t);
   li.style.display=m?'':'none';if(m)shown++;});
  card.style.display=(!t||shown>0)?'':'none';
  if(t)n+=shown;});
 cnt.textContent=t?(n+' match'+(n==1?'':'es')):'';
}
q.addEventListener('input',flt);
</script>"""

def render_containers():
    cards, total, running_total = [], 0, 0
    data = HUB_DATA.setdefault("containers", {"hosts": []})["hosts"]
    for hostname, node, access in DOCKER_HOSTS:
        rows = docker_ps(access)
        data.append({"name": hostname, "node": node, "rows": rows})
        nb = (f'<span class="node-badge">{html.escape(node)}</span>' if node
              else '<span class="node-badge" style="background:#2b2320;color:var(--warn)">bare-metal</span>')
        if rows is None:
            cards.append(f'<div class="card" data-host="{html.escape(hostname)}"><h2>{html.escape(hostname)}{nb}</h2>'
                         f'<p class="meta"><span style="color:var(--off)">unreachable</span></p></div>')
            continue
        total += len(rows)
        running = sum(1 for _, st, _ in rows if st == "running")
        running_total += running
        # running first (green/amber), then stopped (grey), each alphabetical
        def sortkey(r):
            return (0 if r[1] == "running" else 1, r[0].lower())
        li = ""
        for cname, state, status in sorted(rows, key=sortkey):
            if state == "running":
                dot = "warn" if "unhealthy" in status.lower() else "on"
            else:
                dot = "off"
            esc = html.escape(cname)
            if hostname in DOCKHAND_HOSTS:
                link = DOCKHAND + urllib.parse.quote(cname)
                name_html = f'<a class="cname" href="{link}">{esc}</a>'
            else:
                name_html = f'<span class="gname">{esc}</span>'
            li += f'<li data-name="{esc.lower()}"><span class="dot {dot}"></span>{name_html}</li>'
        cards.append(f'<div class="card" data-host="{html.escape(hostname)}"><h2>{html.escape(hostname)}{nb}</h2>'
                     f'<p class="meta">Docker · {running}/{len(rows)} running</p><ul>{li}</ul></div>')
    HUB_SUMMARY["containers"] = f"{running_total}/{total} running"
    search = ('<div class="search"><input id="q" type="search" placeholder="Filter containers or hosts…" '
              'autocomplete="off" autofocus><span id="cnt" class="usage"></span>'
              f'<a class="toplink" href="https://dockhand.{TS}">Dockhand ⬈</a></div>')
    return page("Docker Containers",
                f"All containers across the fleet — {running_total} running of {total} total, grouped by host with "
                f"its PVE node. Green = running, amber = unhealthy, grey = stopped. Click a container to open it in Dockhand.",
                search + '<div class="grid">' + "".join(cards) + "</div>" + SEARCH_JS)

# ---------- zigbee ----------
# Zigbee2MQTT instances: (container, ssh-host, host-published port, DockTail service name)
# The host port is probed over SSH rather than via the ts.net name so a lost DockTail
# advertisement is not misreported as a dead server.
# office + laundry removed 2026-09-20: retired on purpose (empty shells, containers
# exited on `edge`), and their VIP service definitions were deleted, so the cards
# were advertising links that could not resolve. Do not re-add them — see
# ~/projects/docs/thread-matter.md / the Z2M estate note.
Z2M_INSTANCES = [
    ("zigbee2mqtt-upstairs", "utilities", 8082, "zigbee2mqtt-upstairs"),
    ("zigbee2mqtt-basement", "utilities", 8086, "zigbee2mqtt-basement"),
]

# SLZB radios: (label, model, ip, coordinator tcp port). Laundry sits on the
# 192.168.10.0/24 VLAN, not the main LAN - the advertiser can still reach it.
# (label, model, ip, coordinator tcp port, role). Physical locations confirmed by the
# user 2026-09-01 - HA's area labels for these are WRONG and must not be trusted.
# The SLZB-06M spares and the SLZB-06Mg24U were physically removed 2026-10-02; the
# two MR1Us below are the only SLZB radios left in the house.
SLZB_RADIOS = [
    ("slzb-mr1u-upstairs", "SLZB-MR1U", "192.168.86.130", 7638, "upstairs (office) - coordinator, ch 20"),
    ("slzb-mr1u-basement", "SLZB-MR1U", "192.168.86.245", 7638, "basement (laundry) - coordinator, ch 25, PoE"),
]

def _icmp(ip):
    try:
        return subprocess.run(["ping", "-c2", "-W3", ip], capture_output=True,
                              timeout=10).returncode == 0
    except Exception:
        return False

def _http_code(url, timeout=5):
    try:
        r = subprocess.run(["curl", "-sk", "-o", "/dev/null", "-w", "%{http_code}",
                            "--max-time", str(timeout), url],
                           capture_output=True, text=True, timeout=timeout + 4)
        return r.stdout.strip() or "000"
    except Exception:
        return "000"

def _tcp_open(ip, port, timeout=4):
    import socket
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False

def z2m_probe(container, host, port):
    """Container state + frontend liveness + config, in one SSH round trip.

    The frontend probe is the load-bearing check: on 2026-09-01 the adapter
    socket timed out, Z2M logged 'Stopping Zigbee2MQTT (restart=false)' and
    exited -- but the CONTAINER stayed up, so `docker ps` still read healthy and
    the failure was invisible for hours. A dead Z2M stops answering on 8080
    while the container still reports Up; that divergence is the alarm.
    Deliberately greps only base_topic/adapter/port -- configuration.yaml also
    holds the MQTT password in plaintext and it must never reach this page.
    """
    cmd = (f"docker inspect -f '{{{{.State.Status}}}}|{{{{.State.StartedAt}}}}' {container} 2>/dev/null; echo '@@'; "
           f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 http://localhost:{port}/ 2>/dev/null; echo; echo '@@'; "
           f"docker exec {container} sh -c 'grep -E \"base_topic:|port: tcp|adapter:\" /app/data/configuration.yaml 2>/dev/null; "
           f"echo DEVS=$(grep -c . /app/data/database.db 2>/dev/null || echo 0)' 2>/dev/null")
    out = ssh(host, cmd, user="snadboy", timeout=30)
    d = {"state": None, "http": "000", "base_topic": None, "adapter": None,
         "target": None, "devices": None}
    if out is None:
        return d
    parts = out.split("@@")
    if parts and parts[0].strip():
        d["state"] = parts[0].strip().split("|")[0]
    if len(parts) > 1:
        d["http"] = parts[1].strip() or "000"
    if len(parts) > 2:
        for ln in parts[2].splitlines():
            ln = ln.strip()
            if ln.startswith("base_topic:"):
                d["base_topic"] = ln.split(":", 1)[1].strip()
            elif ln.startswith("adapter:"):
                d["adapter"] = ln.split(":", 1)[1].strip()
            elif ln.startswith("port:") and "tcp://" in ln:
                d["target"] = ln.split(":", 1)[1].strip()
            elif ln.startswith("DEVS="):
                try:
                    n = int(ln.split("=", 1)[1])
                    d["devices"] = max(n - 1, 0) if n else 0   # database.db includes the coordinator
                except Exception:
                    pass
    return d

def _row(ok, label, value, warn=False):
    dot = "on" if ok else ("warn" if warn else "off")
    return (f'<li><span class="dot {dot}"></span><span class="gname">{html.escape(label)}</span>'
            f'<span class="stat{"" if ok else " down"}">{html.escape(value)}</span></li>')

def render_zigbee():
    # --- Z2M servers ---
    probes, cards = {}, []
    for container, host, port, svc in Z2M_INSTANCES:
        p = z2m_probe(container, host, port)
        probes[container] = p
        up = p["http"].startswith("2") or p["http"].startswith("3")
        running = p["state"] == "running"
        configured = bool(p["target"])

        if running and not up:
            note = "container up, Z2M NOT RESPONDING"
        elif not running:
            note = "container not running"
        elif not configured:
            note = "running but no adapter configured"
        else:
            note = "healthy"
        zdata = HUB_DATA.setdefault("zigbee", {"servers": [], "radios": []})
        zdata["servers"].append({"container": container, "host": host, "svc": svc, "probe": p,
                                 "up": up, "running": running, "configured": configured,
                                 "healthy": up and configured, "note": note})

        rows = _row(up, "frontend", f'HTTP {p["http"]}')
        rows += _row(running, "container", p["state"] or "unknown")
        rows += _row(configured, "adapter", p["target"] or "not configured")
        rows += _row(bool(p["base_topic"]), "base topic", p["base_topic"] or "-")
        if p["devices"] is not None:
            rows += _row(True, "devices", str(p["devices"]))

        badge = f'<span class="node-badge">{html.escape(host)}</span>'
        klass = "card" if running else "card unreach"
        cards.append(
            f'<div class="{klass}"><h2><a href="https://{svc}.{TS}">{html.escape(container)}</a>{badge}</h2>'
            f'<p class="meta">{html.escape(note)}</p><ul>{rows}</ul></div>')

    # map radio IP -> the instance using it, from live config
    used_by = {}
    for container, p in probes.items():
        t = p.get("target") or ""
        if "tcp://" in t:
            used_by[t.split("//", 1)[1].split(":")[0]] = container

    # --- SLZB radios ---
    rcards, radio_up = [], []
    for label, model, ip, cport, role in SLZB_RADIOS:
        # Probe all three independently and treat ANY positive as present. Gating
        # the HTTP/socket checks behind ICMP meant a single dropped ping blanked
        # the whole card (observed 2026-09-01: MR1U-HOUSE rendered unreachable
        # while it was serving traffic normally).
        icmp = _icmp(ip)
        code = _http_code(f"http://{ip}/")
        web = code.startswith("2") or code.startswith("3")
        sock = _tcp_open(ip, cport)
        up = icmp or web or sock
        radio_up.append(up)
        user = used_by.get(ip)
        HUB_DATA.setdefault("zigbee", {"servers": [], "radios": []})["radios"].append(
            {"label": label, "model": model, "ip": ip, "cport": cport, "role": role,
             "up": up, "web": web, "code": code, "sock": sock, "user": user})

        rows = _row(up, "network", "up" if up else "unreachable")
        rows += _row(web, "web UI", f"HTTP {code}")
        rows += _row(sock, f"coordinator :{cport}", "listening" if sock else "closed")
        rows += _row(bool(user), "used by", user or "unused")

        title = (f'<a href="http://{ip}/">{html.escape(label)}</a>' if up
                 else html.escape(label))
        rklass = "card" if up else "card unreach"
        rcards.append(
            f'<div class="{rklass}"><h2>{title}</h2>'
            f'<p class="meta">{html.escape(model)} · {html.escape(ip)} · {html.escape(role)}</p><ul>{rows}</ul></div>')

    live = sum(1 for c, p in probes.items()
               if (p["http"].startswith("2") or p["http"].startswith("3")) and p["target"])
    radios_up = sum(radio_up)

    HUB_SUMMARY["zigbee"] = f"{live} servers · {radios_up}/{len(SLZB_RADIOS)} radios"
    body = (f'<h3 class="section">Zigbee2MQTT servers</h3><div class="grid">{"".join(cards)}</div>'
            f'<h3 class="section">SLZB radios</h3><div class="grid">{"".join(rcards)}</div>')
    return page("Zigbee",
                f"Zigbee2MQTT servers and SLZB coordinator radios — {live} fully-configured server(s) responding, "
                f"{radios_up}/{len(SLZB_RADIOS)} radios reachable. A server whose container is up but whose "
                f"frontend does not answer has died inside a healthy-looking container. Click a server or radio to open it.",
                body)

# ---------- home (root index of every service) ----------
# The point of this page is that `home` is the only name you have to remember.
#
# The LIST is discovered, never hand-maintained. It comes from the local netmap's
# MagicDNS records (`tailscale debug netmap` -> DNS.ExtraRecords), which carry one
# entry per VIP service and are therefore complete by construction — verified
# 2026-09-20 to match `GET /api/v2/tailnet/-/vip-services` name-for-name, all 61,
# with no OAuth secret on the advertiser.
#
# Do NOT "simplify" this to scraping DockTail labels + the static-serve files.
# That was the first cut and it silently omitted five live services (claude,
# infra-test, pkdb-app, plex-recent, pwa). All five are published by ONE container
# -- pwa-appserver on bedrock -- through DockTail's NUMBERED labels
# (docktail.service.name plus docktail.service.<N>.name), and that scraper read
# only the un-numbered key, so it saw `bulletin` and missed the other five.
#
# The scraper below now handles both label forms, but that is NOT a reason to
# promote it back to being the source of truth: it costs an SSH round trip per
# host, it silently under-reports any host that is unreachable, and it has to keep
# pace with every label form DockTail adds. The netmap has none of those failure
# modes. These two sources are kept only to annotate WHERE a service runs.
#
# Why this matters: the old `sbhome` dashboard hardcoded its source (the Traefik
# API) and served an empty page for months after Traefik was retired in July 2026.
# A stale *blurb* below is cosmetic; a stale *list* is the failure that killed it.
#
# Categories and blurbs are hand-written because nothing on the wire knows them.
# Anything discovered but uncategorised falls into "Other" rather than being
# dropped, so a new service is always reachable even before it is classified.
# Each topic hub hangs off the category card it belongs to, as a named link in that
# card's header (not a separate row up top) -- the drill-down sits where the content
# is, and the hub's NAME stays visible, which is the whole point of this page.
#
# `zigbee` is deliberately labelled by name rather than as a generic "Details":
# it covers only the two Z2M entries of "Home & automation", not ha/homelab-bar/trmnl,
# so a generic label there would overpromise.
CATEGORY_HUBS = {
    "Media":                    "servarr",
    "Virtualization & backup":  "proxmox",
    "Containers & monitoring":  "containers",
    "Home & automation":        "zigbee",
}

# Headline numbers for those links, filled in by each hub's own renderer. A global
# because the hub renderers already compute these while building their pages, and
# recomputing them for `home` would mean a second round of SSH to every host.
# main() therefore renders the hubs BEFORE home.
HUB_SUMMARY = {}

# The full data behind each hub, for the modals on `home`. Filled the same way and
# for the same reason as HUB_SUMMARY: the hub renderers already gather it.
HUB_DATA = {}

HOME_CATEGORIES = [
    ("Home & automation", ["ha", "zigbee2mqtt-upstairs", "zigbee2mqtt-basement",
                           "slzb-upstairs", "slzb-basement",
                           "homelab-bar", "trmnl"]),
    ("Media", ["plex", "plex-recent", "jellyfin", "tautulli", "sonarr", "radarr",
               "prowlarr", "bazarr", "sabnzbd", "overseerr", "agregarr", "tracearr",
               "maintainerr", "wizarr", "gpu-benchmark"]),
    ("Virtualization & backup", ["euler", "gauss", "maxwell", "faraday",
                                 "alexandria", "svalbard", "pve-api"]),
    ("Containers & monitoring", ["dockhand", "beszel", "pulse",
                                 "uptime-kuma", "gotify", "bulletin", "peanut",
                                 "infra-test"]),
    ("Network & storage", ["unifi", "unifi-toolkit", "wan-pin", "technitium",
                           "media", "unas-able", "unas-baker"]),
    ("Automation & workflows", ["semaphore", "windmill"]),
    ("Apps & personal", ["pkdb", "pkdb-app", "pwa", "claude", "aoe", "actual",
                         "firefly", "firefly-import", "termix", "pdf"]),
    ("Games", ["cubeloop", "squadblitz", "crowncrush", "hearts", "sbsave"]),
]

# service -> (dashboard-icons slug or None, blurb). A missing entry is fine: the
# blurb falls back to where the service actually runs, and a slug the CDN does not
# have degrades to a letter badge.
SBSAVE_ICON = ('<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="sbsv" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7b5cf0"/><stop offset="1" stop-color="#3d2a9e"/></linearGradient></defs><rect width="64" height="64" rx="14" fill="url(#sbsv)"/><path d="M20 45h25a9 9 0 0 0 1-18 13 13 0 0 0-25-3 10.5 10.5 0 0 0-1 21z" fill="#fff"/><path d="M25.5 35.5l5 5 9-10" fill="none" stroke="#e8b923" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/></svg>')

HOME_META = {
    "ha":                   ("home-assistant", "Home Assistant"),
    "zigbee2mqtt-upstairs": ("zigbee2mqtt", "Z2M — upstairs (office) coordinator"),
    "zigbee2mqtt-basement": ("zigbee2mqtt", "Z2M — basement (laundry) coordinator"),
    # The adapter hardware behind those two Z2M servers (SLZB-OS web UI). Blurbs
    # are explicit because a missing HOME_META entry falls back to showing where
    # the service runs, which renders as a bare IP.
    "slzb-upstairs":        (None, "SLZB-MR1U radio — office (Zigbee + Thread)"),
    "slzb-basement":        (None, "SLZB-MR1U radio — laundry (Zigbee)"),
    "homelab-bar":          (None, "RPi rack-panel dashboard"),
    "trmnl":                (None, "BYOS TRMNL e-ink server"),
    "plex":                 ("plex", "Plex Media Server"),
    "plex-recent":          ("plex", "Recently-added feed"),
    "jellyfin":             ("jellyfin", "Jellyfin"),
    "tautulli":             ("tautulli", "Plex stats and history"),
    "sonarr":               ("sonarr", "TV"),
    "radarr":               ("radarr", "Movies"),
    "prowlarr":             ("prowlarr", "Indexers"),
    "bazarr":               ("bazarr", "Subtitles"),
    "sabnzbd":              ("sabnzbd", "Usenet downloader"),
    "overseerr":            ("overseerr", "Media requests"),
    "agregarr":             (None, "Plex collection management"),
    "tracearr":             (None, "arr activity trace"),
    "maintainerr":          ("maintainerr", "Library retention / Leaving Soon"),
    "wizarr":               ("wizarr", "Plex invites and onboarding"),
    "gpu-benchmark":        (None, "4K transcode benchmark (Arc iGPU)"),
    "euler":                ("proxmox", "Proxmox VE node"),
    "gauss":                ("proxmox", "Proxmox VE node"),
    "maxwell":              ("proxmox", "Proxmox VE node"),
    "faraday":              ("proxmox", "Proxmox VE node"),
    "alexandria":           ("proxmox", "Proxmox Backup Server"),
    "svalbard":             ("proxmox", "Proxmox Backup Server"),
    "pve-api":              (None, "Proxmox API helper (/health)"),
    "dockhand":             (None, "Docker stack deploys"),
    "beszel":               ("beszel", "System metrics"),
    "pulse":                (None, "Proxmox monitoring"),
    "uptime-kuma":          ("uptime-kuma", "Uptime monitoring"),
    "gotify":               ("gotify", "Push notifications"),
    "bulletin":             (None, "Homelab bulletin board"),
    "peanut":               (None, "NUT / UPS dashboard"),
    "unifi":                ("unifi", "UniFi Network controller"),
    "unifi-toolkit":        ("unifi", "UniFi helper tools"),
    "wan-pin":              (None, "Pin a client to a WAN uplink"),
    "technitium":           ("technitium", "DNS server"),
    "media":                ("synology", "Synology DSM (syn-media)"),
    "unas-able":            (None, "UNAS Pro Able — hosts shareables"),
    "unas-baker":           (None, "UNAS Pro Baker"),
    "semaphore":            ("semaphore", "Ansible playbook runner"),
    "windmill":             ("windmill", "Workflow engine"),
    "infra-test":           (None, "Infra test suite (suite itself retired)"),
    "pkdb":                 (None, "Personal knowledge database"),
    "pkdb-app":             (None, "PKDB app"),
    "pwa":                  (None, "PWA hub"),
    "claude":               (None, "Claude Code Remote Control"),
    "aoe":                  (None, "Agent of Empires - agent session manager"),
    "actual":               ("actual-budget", "Actual Budget"),
    "firefly":              ("firefly-iii", "Firefly III"),
    "firefly-import":       ("firefly-iii", "Firefly III data importer"),
    "termix":               (None, "Web terminal"),
    "pdf":                  ("stirling-pdf", "Stirling PDF tools"),
    "cubeloop":             ("https://cubeloop.swallow-spectrum.ts.net/icons/icon-192.png", "SB Cube Loop — loop-sort puzzle"),
    "squadblitz":           ("https://squadblitz.swallow-spectrum.ts.net/icons/icon-192.png", "SB Squad Blitz — gate runner shooter"),
    "crowncrush":           ("https://crowncrush.swallow-spectrum.ts.net/icons/icon-192.png", "SB Crown Crush — match-3"),
    "hearts":               ("https://hearts.swallow-spectrum.ts.net/icons/icon-192.png", "SB Hearts — card game with a coach"),
    "sbsave":               (SBSAVE_ICON, "SB Save — cloud saves for SB games"),
}

def tailnet_services():
    """Every VIP service name on the tailnet, from the local netmap.

    One MagicDNS ExtraRecord per service per address family; machine names are not
    in ExtraRecords, so the set needs no filtering beyond the suffix and rejecting
    anything with a further label. Returns an empty set on failure, which the
    caller treats as "keep the previous page" rather than publishing a blank index.
    """
    try:
        r = subprocess.run(["tailscale", "debug", "netmap"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return set()
        recs = (json.loads(r.stdout).get("DNS") or {}).get("ExtraRecords") or []
    except Exception:
        return set()
    names, suffix = set(), "." + TS
    for rec in recs:
        n = (rec.get("Name") or "").rstrip(".")
        if n.endswith(suffix):
            short = n[:-len(suffix)]
            if short and "." not in short:
                names.add(short)
    return names

def _desired_file(path):
    """name -> value from a reconciler desired-state file ('name value' lines)."""
    d = {}
    try:
        for ln in open(path):
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            parts = ln.split(None, 1)
            if len(parts) == 2:
                d[parts[0]] = parts[1]
    except FileNotFoundError:
        pass
    return d

# Emits "<container>\t<state>\t<labels-json>" per container. Dumps ALL labels and
# filters in Python rather than asking for one by name, because DockTail lets a
# single container publish several services via NUMBERED labels
# (docktail.service.name plus docktail.service.<N>.name). pwa-appserver on bedrock
# publishes SIX that way; a probe reading only the un-numbered key sees one.
_PROBE_DOCKTAIL = (
    "docker ps -a --format '{{.Names}}' 2>/dev/null | while read n; do "
    "printf '%s\\t%s\\t' \"$n\" "
    "\"$(docker inspect -f '{{.State.Status}}' \"$n\" 2>/dev/null)\"; "
    "docker inspect -f '{{json .Config.Labels}}' \"$n\" 2>/dev/null; done")

def docktail_services():
    """{service: (host, container-state)} from the labels that create them.

    Reads the labels rather than the Tailscale API on purpose: the API needs an
    OAuth secret, and this role deliberately keeps secrets off the advertiser VMs.
    The labels are also what DockTail itself acts on, so this is the same desired
    state — and it catches a service whose container has stopped, which the API
    cannot distinguish from a healthy one.
    """
    found = {}

    def scan(entry):
        hostname, _node, access = entry
        if access[0] == "ssh":
            out = ssh(access[2], _PROBE_DOCKTAIL, user=access[1], timeout=30)
        else:
            _, pvehost, vmid = access
            inner = _PROBE_DOCKTAIL.replace("{{", "{{{{").replace("}}", "}}}}")
            out = ssh(pvehost, f"pct exec {vmid} -- sh -c {json.dumps(inner)}", timeout=30)
        return hostname, out

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for hostname, out in ex.map(scan, DOCKTAIL_HOSTS):
            if not out:
                continue
            for ln in out.splitlines():
                parts = ln.split("\t")
                if len(parts) < 3:
                    continue
                cname, state, raw = parts[0], parts[1], parts[2]
                try:
                    labels = json.loads(raw) or {}
                except Exception:
                    continue
                if labels.get("docktail.service.enable") != "true":
                    continue
                for key, val in labels.items():
                    # docktail.service.name and docktail.service.<N>.name
                    if not val or not key.startswith("docktail.service."):
                        continue
                    tail = key[len("docktail.service."):]
                    if tail == "name" or (tail.endswith(".name") and tail[:-5].isdigit()):
                        found[val] = (hostname, state)
    return found

def vip_status(names):
    """{name: bool} — does the VIP answer at all. Any HTTP status counts.

    Never follows redirects: tautulli 303s to a location that refuses off-host
    connections, so following it turns a healthy service into a timeout. Same trap
    ts-service-healer documents.
    """
    def probe(n):
        return n, _http_code(f"https://{n}.{TS}/", timeout=8) != "000"
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        return dict(ex.map(probe, names))

# ---------- home page: look ----------
# The home page has its own stylesheet and script (the hub pages above keep the
# shared CSS). Dark by default, light under prefers-color-scheme: light.
HOME_CSS = """
:root{color-scheme:dark;--bg:#0B0E13;--surface:#12171E;--surface-2:#171D26;--line:#222A35;
--line-strong:#344052;--text:#E9EEF4;--dim:#94A1B0;--ok:#3DD68C;--ok-ring:rgba(61,214,140,.16);
--warn:#F0B44C;--bad:#F2685F;--mute:#5B6575;--accent:#7CB7FF;--ring:rgba(124,183,255,.22);
--scrim:rgba(4,6,10,.68);--shadow:0 1px 0 rgba(255,255,255,.03) inset;
--tb-l:60%;--tb-a:.14;--tf-s:80%;--tf-l:76%;--sw-s:65%;--sw-l:62%;
--sans:'Instrument Sans',ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
--mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
@media (prefers-color-scheme:light){:root{color-scheme:light;--bg:#F6F7F9;--surface:#fff;
--surface-2:#F1F4F8;--line:#E2E6EC;--line-strong:#C3CBD6;--text:#0F1722;--dim:#556171;--ok:#13A05F;
--ok-ring:rgba(19,160,95,.12);--warn:#B87208;--bad:#C93C32;--mute:#A3ACB8;--accent:#1F5FD1;
--ring:rgba(31,95,209,.16);--scrim:rgba(15,23,34,.42);--shadow:0 1px 2px rgba(15,23,34,.05);
--tb-l:50%;--tb-a:.11;--tf-s:60%;--tf-l:34%;--sw-s:60%;--sw-l:48%}}
/* MUST be !important: the UA [hidden] rule loses to any author display rule, and
   tiles/sections/chips all set display. Without it the filter "hides" rows that stay
   on screen (the bug the old index shipped with). */
[hidden]{display:none!important}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 var(--sans);-webkit-font-smoothing:antialiased}
body:has(dialog[open]){overflow:hidden}
a{color:inherit}
.mono{font-family:var(--mono)}
.wrap{max-width:1240px;margin:0 auto;padding-left:clamp(16px,4vw,40px);padding-right:clamp(16px,4vw,40px)}
.tint{background:hsla(var(--h),70%,var(--tb-l),var(--tb-a));color:hsl(var(--h),var(--tf-s),var(--tf-l))}
.d{width:8px;height:8px;border-radius:50%;flex:0 0 auto;display:inline-block}
.d-ok{background:var(--ok)}.d-warn{background:var(--warn)}.d-bad{background:var(--bad)}.d-mute{background:var(--mute)}
:where(a,button,input):focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* header */
.top{border-bottom:1px solid var(--line)}
.top .wrap{display:flex;flex-wrap:wrap;align-items:center;gap:16px 24px;padding-top:18px;padding-bottom:18px}
.brand{display:flex;align-items:center;gap:12px;text-decoration:none}
.brand-mark{width:34px;height:34px;border-radius:9px;background:var(--text);color:var(--bg);display:inline-flex;align-items:center;justify-content:center}
.brand-txt{display:flex;flex-direction:column;line-height:1.15}
.brand-txt b{font-size:16px;letter-spacing:-.01em}
.brand-txt span{font-family:var(--mono);font-size:12px;color:var(--dim)}
.hubnav{display:flex;flex-wrap:wrap;gap:4px;margin-left:auto}
.hubnav a{font-size:13px;font-weight:500;color:var(--dim);text-decoration:none;padding:8px 12px;min-height:44px;display:inline-flex;align-items:center;border:1px solid transparent;border-radius:8px}
.hubnav a:hover{color:var(--text);border-color:var(--line-strong)}
.pill{display:inline-flex;align-items:center;gap:8px;font-size:13px;font-weight:500;padding:7px 12px;border-radius:999px;border:1px solid var(--line);background:var(--surface);font-variant-numeric:tabular-nums}
.pill .d{box-shadow:0 0 0 3px var(--ok-ring)}
.pill.warn .d{background:var(--warn);box-shadow:0 0 0 3px rgba(240,180,76,.18)}

/* hero + search */
.hero{padding:clamp(40px,7vw,72px) 0 32px;display:flex;flex-direction:column;gap:14px}
.eyebrow{margin:0;font-family:var(--mono);font-size:12px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
.hero h1{margin:0;font-size:clamp(32px,4.6vw,52px);line-height:1.05;font-weight:600;letter-spacing:-.025em;max-width:18ch}
.lede{margin:0;font-size:17px;color:var(--dim);max-width:58ch}
.lede .mono{font-size:15px;color:var(--text)}
.search{margin-top:14px;display:flex;flex-direction:column;gap:10px;max-width:640px}
.sbox{position:relative}
.sbox svg{position:absolute;left:16px;top:50%;transform:translateY(-50%);color:var(--dim);pointer-events:none}
.sbox input{width:100%;height:56px;padding:0 128px 0 48px;font:inherit;font-size:16px;color:var(--text);background:var(--surface);border:1px solid var(--line);border-radius:12px;outline:none;box-shadow:var(--shadow);-webkit-appearance:none;appearance:none}
.sbox input::placeholder{color:var(--dim)}
.sbox input:focus{border-color:var(--accent);box-shadow:0 0 0 4px var(--ring)}
.sbox input::-webkit-search-cancel-button{display:none}
.scnt{position:absolute;right:14px;top:50%;transform:translateY(-50%);font-size:12px;color:var(--dim);font-variant-numeric:tabular-nums;pointer-events:none}
.hint{margin:0;font-size:13px;color:var(--dim);display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}
kbd{font-family:var(--mono);font-size:11px;padding:2px 6px;border-radius:5px;border:1px solid var(--line);background:var(--surface);color:var(--text)}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.cap{margin:0 0 14px;font-size:13px;font-weight:600;color:var(--dim);letter-spacing:.02em}

/* hub cards */
.hubs{padding:8px 0 40px}
.hubgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
.hub{display:flex;flex-direction:column;gap:18px;padding:20px;min-height:148px;text-decoration:none;background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);transition:border-color .15s,background-color .15s}
.hub:hover{border-color:var(--line-strong);background:var(--surface-2)}
.hub-top{display:flex;align-items:center;gap:10px}
.hub-ico{width:32px;height:32px;border-radius:8px;display:inline-flex;align-items:center;justify-content:center}
.hub-name{font-family:var(--mono);font-size:14px;font-weight:500}
.hub-top .exp{margin-left:auto;color:var(--dim)}
.hub-num{display:flex;flex-direction:column;gap:2px}
.big{font-size:30px;font-weight:600;letter-spacing:-.02em;font-variant-numeric:tabular-nums;line-height:1.1}
.big .of{color:var(--dim);font-weight:500}
.big .unit{color:var(--dim);font-weight:500;font-size:18px;letter-spacing:0}
.hub-lbl{font-size:13px;color:var(--dim)}

/* service sections */
.chipbar{position:sticky;top:0;z-index:2;background:var(--bg);padding:14px 0;margin:0 0 8px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.chipbar .cap{margin:0 10px 0 0}
/* On a phone the wrapped chips are five rows of a sticky bar; one sideways-scrolling
   row keeps the list readable. */
@media (max-width:640px){.chipbar{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;margin-left:calc(-1*clamp(16px,4vw,40px));margin-right:calc(-1*clamp(16px,4vw,40px));padding-left:clamp(16px,4vw,40px);padding-right:clamp(16px,4vw,40px)}
.chipbar::-webkit-scrollbar{display:none}.chip{flex:0 0 auto}}
.chip{font:inherit;font-size:13px;font-weight:500;cursor:pointer;display:inline-flex;align-items:center;gap:8px;min-height:36px;padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:var(--surface);color:var(--dim);transition:border-color .15s,color .15s}
.chip:hover{color:var(--text);border-color:var(--line-strong)}
.chip .cc{font-size:12px;font-variant-numeric:tabular-nums}
.chip[aria-pressed="true"]{background:var(--text);border-color:var(--text);color:var(--bg)}
.svc{padding:20px 0 16px;display:flex;flex-direction:column;gap:14px}
.shead{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px}
.swatch{width:10px;height:10px;border-radius:3px;background:hsl(var(--h),var(--sw-s),var(--sw-l))}
.shead h3{margin:0;font-size:18px;font-weight:600;letter-spacing:-.01em}
.scount{font-size:13px;color:var(--dim);font-variant-numeric:tabular-nums}
.hublink{margin-left:auto;display:inline-flex;align-items:center;gap:8px;min-height:36px;padding:6px 12px;font-size:13px;color:var(--dim);text-decoration:none;border:1px solid var(--line);border-radius:8px}
.hublink:hover{color:var(--text);border-color:var(--line-strong)}
.hublink .mono{color:var(--accent)}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(272px,1fr));gap:10px}
.tile{display:flex;align-items:center;gap:12px;padding:12px 14px;min-height:64px;text-decoration:none;background:var(--surface);border:1px solid var(--line);border-radius:12px;transition:border-color .15s,background-color .15s}
.tile:hover{border-color:var(--line-strong);background:var(--surface-2)}
.tile.hit{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}
.tile.off{opacity:.62}
.ico{flex:0 0 auto;width:38px;height:38px;border-radius:9px;display:inline-flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:13px;font-weight:600;letter-spacing:-.02em;background:var(--surface-2) center/24px 24px no-repeat}
.ico.sm{width:24px;height:24px;border-radius:6px;font-size:10px;background-size:16px 16px}
.ico.tint{background:hsla(var(--h),70%,var(--tb-l),var(--tb-a))}  /* .ico's shorthand would repaint it grey */
.tbody{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;gap:1px}
.tname{font-family:var(--mono);font-size:14px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tdesc{font-size:13px;color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tend{flex:0 0 auto;display:inline-flex;align-items:center;gap:8px}
.tag{font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--dim);padding:2px 7px;border-radius:5px;border:1px solid var(--line)}
.go{color:var(--dim);opacity:0;transition:opacity .15s}
.tile:hover .go{opacity:1}
.empty{padding:56px 24px;text-align:center;border:1px dashed var(--line-strong);border-radius:14px;display:flex;flex-direction:column;align-items:center;gap:12px}
.empty p{margin:0}
.empty .t{font-size:17px;font-weight:600}
.empty .s{font-size:14px;color:var(--dim)}
.empty button{font:inherit;font-size:14px;font-weight:500;cursor:pointer;min-height:44px;padding:8px 16px;border-radius:10px;border:1px solid var(--line);background:var(--surface);color:var(--text)}
footer{border-top:1px solid var(--line);margin-top:48px}
footer .wrap{padding-top:22px;padding-bottom:22px;display:flex;flex-wrap:wrap;gap:8px 24px;font-size:13px;color:var(--dim)}
footer .r{margin-left:auto}

/* hub modal */
dialog.hubdlg{width:min(960px,calc(100vw - 32px));max-width:none;max-height:calc(100vh - 32px);max-height:calc(100dvh - 32px);margin:auto;padding:0;border:1px solid var(--line-strong);border-radius:18px;background:var(--bg);color:var(--text);box-shadow:0 30px 80px -20px rgba(0,0,0,.55);overflow:hidden;flex-direction:column}
dialog.hubdlg[open]{display:flex;animation:rise .22s cubic-bezier(.2,.8,.2,1)}
dialog.hubdlg::backdrop{background:var(--scrim);backdrop-filter:blur(4px)}
@keyframes rise{from{opacity:0;transform:translateY(12px) scale(.985)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){dialog.hubdlg[open]{animation:none}}
.mhead{flex:0 0 auto;display:flex;flex-wrap:wrap;align-items:flex-start;gap:14px 16px;padding:22px 22px 18px 24px;border-bottom:1px solid var(--line);background:var(--surface)}
.mico{flex:0 0 auto;width:44px;height:44px;border-radius:11px;display:inline-flex;align-items:center;justify-content:center}
.mtitle{flex:1 1 320px;min-width:0;display:flex;flex-direction:column;gap:4px}
.mtl{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px}
.mtl h2{margin:0;font-size:22px;font-weight:600;letter-spacing:-.015em}
.mtl .mono{font-size:13px;color:var(--accent)}
.mtitle p{margin:0;font-size:14px;color:var(--dim);max-width:64ch}
.mact{flex:0 0 auto;display:flex;align-items:center;gap:8px;margin-left:auto}
.mbtn{font:inherit;cursor:pointer;background:transparent;display:inline-flex;align-items:center;gap:8px;min-height:40px;padding:8px 12px;font-size:13px;font-weight:500;color:var(--dim);text-decoration:none;border:1px solid var(--line);border-radius:9px}
.mbtn:hover{color:var(--text);border-color:var(--line-strong)}
.xbtn{font:inherit;cursor:pointer;width:44px;height:44px;display:inline-flex;align-items:center;justify-content:center;border:0;border-radius:10px;background:transparent;color:var(--dim)}
.xbtn:hover{background:var(--surface-2);color:var(--text)}
.mbody{flex:1 1 auto;overflow-y:auto;overscroll-behavior:contain;padding:22px 24px 26px;display:flex;flex-direction:column;gap:26px}
.mbody>*{flex-shrink:0}  /* a scrolling flex column squashes its children otherwise */
dialog.hubdlg:focus{outline:none}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
@media (max-width:520px){.mhead{padding:18px 16px 14px}.mbody{padding:16px}.metric{padding:12px 14px}.metric .big{font-size:24px}}
.metric{display:flex;flex-direction:column;gap:4px;padding:16px 18px;background:var(--surface);border:1px solid var(--line);border-radius:12px}
.m-lbl{font-size:12px;font-weight:500;color:var(--dim)}
.metric .big{font-size:28px}
.m-sub{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--dim)}
.m-sub .d{width:6px;height:6px}
.mcap{margin:0;font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--dim)}
.mgroup{display:flex;flex-direction:column;gap:10px}
.mgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(var(--min,260px),1fr));gap:10px;align-items:start}
.mcard{display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.mcard>.mcap{padding:12px 14px 8px}
.mrow{display:flex;align-items:center;gap:10px;padding:9px 14px;min-height:44px;text-decoration:none;border-top:1px solid var(--line)}
a.mrow:hover,a.mhd:hover{background:var(--surface-2)}
.mrow.off{opacity:.62}
.mrow-name{flex:1 1 auto;min-width:0;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mrow-stat{font-size:13px;color:var(--dim);font-variant-numeric:tabular-nums;white-space:nowrap}
.mrow-stat.bad{color:var(--bad)}
.mhd{display:flex;align-items:center;gap:10px;padding:12px 14px;min-height:44px;text-decoration:none}
.mhd .mono{font-size:14px;font-weight:600}
.mhd .r{margin-left:auto;font-size:12px;color:var(--dim);font-variant-numeric:tabular-nums}
.mhd .r.bad{color:var(--bad)}
.guests{display:flex;flex-direction:column;padding:4px 0 8px;border-top:1px solid var(--line)}
.guest{display:flex;align-items:center;gap:10px;padding:5px 14px;font-size:13px}
.guest.off{opacity:.55}
.kind{flex:0 0 auto;width:26px;font-family:var(--mono);font-size:10px;font-weight:600;text-align:center;padding:1px 0;border-radius:4px}
.kind.vm{--h:268}.kind.ct{--h:205}
.guest .n{flex:1 1 auto;font-family:var(--mono);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.guest .id{font-family:var(--mono);font-size:12px;color:var(--dim)}
.store{display:flex;flex-direction:column;gap:6px;padding:12px 16px 14px;border-top:1px solid var(--line)}
.store-row{display:flex;align-items:baseline;gap:8px;font-size:13px}
.store-row .mono{color:var(--dim)}
.store-row .u{margin-left:auto;color:var(--dim);font-variant-numeric:tabular-nums}
.store-row b{font-variant-numeric:tabular-nums}
.bar{display:block;height:8px;border-radius:99px;background:var(--line);overflow:hidden}
.bar>span{display:block;height:100%;border-radius:99px;background:var(--ok)}
.bar.warn>span{background:var(--warn)}.bar.bad>span{background:var(--bad)}
.hostcard{display:flex;flex-direction:column;gap:12px;padding:14px 16px;background:var(--surface);border:1px solid var(--line);border-radius:12px}
.hosthd{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.hosthd .mono{font-size:14px;font-weight:600}
.badge{font-size:11px;font-weight:500;color:var(--dim);padding:1px 7px;border-radius:5px;border:1px solid var(--line)}
.hosthd .r{margin-left:auto;font-size:13px;font-variant-numeric:tabular-nums}
.hosthd .r span{color:var(--dim)}
.hosthd .r.bad{color:var(--bad)}
.ctrs{display:flex;flex-wrap:wrap;gap:6px}
.ctr{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);font-size:12px;padding:3px 8px;border-radius:6px;background:var(--surface-2);border:1px solid var(--line);text-decoration:none}
a.ctr:hover{border-color:var(--line-strong)}
.ctr .d{width:6px;height:6px}
.ctr.off{opacity:.6}
.mfilter{width:100%;max-width:360px;height:40px;padding:0 12px;font:inherit;font-size:14px;color:var(--text);background:var(--surface);border:1px solid var(--line);border-radius:9px;outline:none}
.mfilter:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--ring)}
.zhd{display:flex;flex-direction:column;gap:2px;padding:12px 16px;text-decoration:none}
a.zhd:hover{background:var(--surface-2)}
.zhd .l{display:flex;align-items:center;gap:10px}
.zhd .mono{font-size:14px;font-weight:600}
.zhd .s{font-size:12px;color:var(--dim)}
.state{margin-left:auto;display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:2px 8px;border-radius:99px;white-space:nowrap}
.state .d{width:6px;height:6px}
.state.ok{color:var(--ok);background:var(--ok-ring)}
.state.warn{color:var(--warn);background:rgba(240,180,76,.14)}
.state.bad{color:var(--bad);background:rgba(242,104,95,.14)}
.kv{margin:0;padding:6px 16px 12px;border-top:1px solid var(--line);display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:6px 12px;font-size:13px}
.kv dt{color:var(--dim)}
.kv dd{margin:0;font-family:var(--mono);font-size:12px;text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kv dd.bad{color:var(--bad)}
.mfoot{margin:0;font-size:12px;color:var(--dim)}
.mfoot .mono{color:var(--text)}
"""

HOME_JS = r"""
(()=>{
const q=document.getElementById('q'),cnt=document.getElementById('cnt'),
 nextWrap=document.getElementById('next'),nextName=document.getElementById('next-name'),
 empty=document.getElementById('empty'),emptyQ=document.getElementById('empty-q');
const secs=[...document.querySelectorAll('section.svc')];
const chips=[...document.querySelectorAll('.chip[data-cat]')];
let cat='all',target=null;
function apply(){
 const t=q.value.trim().toLowerCase();let total=0;const per={};target=null;
 secs.forEach(s=>{
  const tiles=[...s.querySelectorAll('.tile')];
  // A section-name (or hub-name) hit expands the section ONLY when no row inside
  // it matched -- otherwise `arr` drags plex and sabnzbd in just because the hub
  // is called servarr, while `proxmox` (no service is called that) still shows the
  // nodes instead of nothing.
  const rowHit=!!t&&tiles.some(a=>a.dataset.k.includes(t));
  const useAll=!!t&&!rowHit&&s.dataset.k.includes(t);
  let shown=0;
  tiles.forEach(a=>{const m=!t||useAll||a.dataset.k.includes(t);a.hidden=!m;a.classList.remove('hit');if(m)shown++;});
  per[s.dataset.cat]=shown;total+=shown;
  const vis=shown>0&&(cat==='all'||cat===s.dataset.cat);
  s.hidden=!vis;
  s.querySelector('.scount').textContent=t?shown+' of '+tiles.length:tiles.length+' services';
  if(vis&&!target){
   // Typing a hub name means you want the hub, not the first service inside it.
   const hub=s.dataset.hub;
   target=(t&&hub&&hub.startsWith(t))?{hub:hub,name:hub}:{el:tiles.find(a=>!a.hidden)};
   if(!target.el&&!target.hub)target=null;
  }
 });
 chips.forEach(c=>{const n=c.dataset.cat==='all'?total:(per[c.dataset.cat]||0);c.querySelector('.cc').textContent=n;});
 if(t&&target&&target.el){target.el.classList.add('hit');}
 nextWrap.hidden=!(t&&target);
 if(t&&target)nextName.textContent=target.hub||target.el.dataset.name;
 cnt.textContent=t?(total+' match'+(total===1?'':'es')):cnt.dataset.all;
 const none=!secs.some(s=>!s.hidden);
 empty.hidden=!none;emptyQ.textContent=q.value.trim();
}
q.addEventListener('input',apply);
q.addEventListener('keydown',e=>{
 if(e.key==='Enter'&&target){e.preventDefault();if(target.hub)openHub(target.hub);else location.href=target.el.href;}
 if(e.key==='Escape'){q.value='';apply();}
});
document.getElementById('clear').addEventListener('click',()=>{q.value='';cat='all';chips.forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.cat==='all')));apply();q.focus();});

// Hub modals. #servarr, #proxmox, #containers, #zigbee open one, so a link or an
// old bookmark lands on the hub -- the hubs need no addresses of their own.
const dlgs={};
document.querySelectorAll('dialog.hubdlg').forEach(d=>{dlgs[d.id.slice(4)]=d;});
function show(n){
 const d=dlgs[n];if(!d||d.open)return;
 Object.values(dlgs).forEach(x=>{if(x.open)x.close();});
 // Focus the dialog itself, not its first button: the copy/close buttons would
 // otherwise open with a focus ring every time.
 d.showModal();d.focus();d.querySelector('.mbody').scrollTop=0;
}
function openHub(n){
 if(!dlgs[n])return;
 if(location.hash!=='#'+n)history.pushState(null,'','#'+n);
 show(n);
}
function sync(){
 const n=location.hash.slice(1).toLowerCase();
 if(dlgs[n])show(n);else Object.values(dlgs).forEach(d=>{if(d.open)d.close();});
}
Object.entries(dlgs).forEach(([n,d])=>{
 d.addEventListener('close',()=>{if(location.hash==='#'+n)history.replaceState(null,'',location.pathname+location.search);});
 d.addEventListener('click',e=>{if(e.target===d)d.close();});  // backdrop
});
document.addEventListener('click',e=>{
 const a=e.target.closest('a[data-hub]');
 if(a){
  // A modified click (new tab, new window) keeps the browser's own behaviour; the
  // new tab opens on the hash and lands on the modal.
  if(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey||e.button)return;
  e.preventDefault();openHub(a.dataset.hub);return;
 }
 const x=e.target.closest('[data-close]');
 if(x){x.closest('dialog').close();return;}
 const cp=e.target.closest('[data-copy]');
 if(cp){
  const url=location.origin+location.pathname+'#'+cp.dataset.copy,lab=cp.querySelector('span');
  const done=()=>{lab.textContent='Copied';setTimeout(()=>{lab.textContent='Copy link';},1600);};
  if(navigator.clipboard)navigator.clipboard.writeText(url).then(done,()=>{lab.textContent=url;});
  else lab.textContent=url;
  return;
 }
 const ch=e.target.closest('.chip[data-cat]');
 if(ch){
  cat=(ch.dataset.cat===cat&&cat!=='all')?'all':ch.dataset.cat;
  chips.forEach(c=>c.setAttribute('aria-pressed',String(c.dataset.cat===cat)));
  apply();
 }
});
addEventListener('hashchange',sync);
addEventListener('popstate',sync);

// Filter inside the containers modal.
document.querySelectorAll('input.mfilter').forEach(inp=>inp.addEventListener('input',()=>{
 const t=inp.value.trim().toLowerCase();
 inp.closest('dialog').querySelectorAll('[data-host]').forEach(card=>{
  const hm=!t||card.dataset.host.includes(t);let n=0;
  card.querySelectorAll('[data-name]').forEach(c=>{const m=!t||hm||c.dataset.name.includes(t);c.hidden=!m;if(m)n++;});
  card.hidden=!(!t||n>0);
 });
}));

apply();sync();
})();
"""

# ---------- home page: data → markup ----------
CATEGORY_HUE = {
    "Home & automation": 152, "Media": 18, "Virtualization & backup": 268,
    "Containers & monitoring": 205, "Network & storage": 228,
    "Automation & workflows": 45, "Apps & personal": 330, "Games": 290, "Other": 210,
}
HUB_CATEGORY = {hub: cat for cat, hub in CATEGORY_HUBS.items()}
HUB_ORDER = ["servarr", "proxmox", "containers", "zigbee"]

HUB_INFO = {
    "servarr": ("Media automation",
                "The Servarr stack — indexers, managers, requests, downloads and retention, "
                "with live queue and library numbers."),
    "proxmox": ("Proxmox cluster",
                "Virtualization nodes and backup servers. Open a node for its web UI."),
    "containers": ("Docker containers",
                   "Every container across the fleet, grouped by Docker host and the PVE node it "
                   "runs on. Click a container to open it in Dockhand."),
    "zigbee": ("Zigbee",
               "Zigbee2MQTT servers and their SLZB coordinator radios. A server only counts as "
               "healthy when its frontend answers — a dead Z2M can hide inside a running container."),
}

_P = {  # stroke-icon path data, 24×24 viewBox
    "servarr": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m10 9 5 3-5 3z"/>',
    "proxmox": '<rect x="3" y="4" width="18" height="7" rx="1.5"/><rect x="3" y="13" width="18" height="7" rx="1.5"/><path d="M7 7.5h.01M7 16.5h.01"/>',
    "containers": '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
    "zigbee": '<path d="M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0"/><path d="M12 19.5h.01"/><path d="M1.5 9a15 15 0 0 1 21 0"/>',
    "expand": '<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>',
    "out": '<path d="M7 17 17 7M8 7h9v9"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1"/><path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "brand": '<path d="M3 12h3l3-7 4 14 3-7h5"/>',
}

def _svg(key, size=18, cls=""):
    c = f' class="{cls}"' if cls else ""
    return (f'<svg{c} width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_P[key]}</svg>')

# App logos, each emitted ONCE into the page's stylesheet as a background image and
# referenced by class. Never inline the SVG markup: dashboard-icons files carry their
# own <style> blocks (.st0{fill:…}) that leak page-wide once inlined, so one logo
# repaints another -- the old index rendered several with the wrong colours.
_ICON_CSS = {}

def _icon_class(slug):
    if not slug:
        return None
    key = "ic-" + hashlib.sha1(slug.encode()).hexdigest()[:10]
    if key in _ICON_CSS:
        return key
    if slug.startswith("<svg"):
        uri = "data:image/svg+xml;base64," + base64.b64encode(slug.encode()).decode()
    elif slug.startswith("https://"):
        uri = icon_img(slug)
    else:
        svg = icon_svg(slug)
        uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode() if svg else None
    if not uri:
        return None
    _ICON_CSS[key] = uri
    return key

def _mono(name):
    parts = [p for p in name.split("-") if p]
    if len(parts) > 1:
        return (parts[0][0] + parts[1][0]).upper()
    return name[:1].upper() + name[1:2]

def _ico(slug, label, small=False):
    """App logo when one exists, else a two-letter monogram in the category tint."""
    sm = " sm" if small else ""
    cls = _icon_class(slug)
    if cls:
        return f'<span class="ico{sm} {cls}" aria-hidden="true"></span>'
    return f'<span class="ico{sm} tint" aria-hidden="true">{html.escape(_mono(label))}</span>'

def _big(value, of="", unit=""):
    of_html = f'<span class="of">{html.escape(of)}</span>' if of else ""
    unit_html = f' <span class="unit">{html.escape(unit)}</span>' if unit else ""
    return f'<span class="big">{html.escape(str(value))}{of_html}{unit_html}</span>'

def _metric(label, value, of="", sub="", tone="ok"):
    return (f'<div class="metric"><span class="m-lbl">{html.escape(label)}</span>{_big(value, of)}'
            f'<span class="m-sub"><span class="d d-{tone}"></span>{html.escape(sub)}</span></div>')

def _pct_tone(pct):
    return "bad" if pct >= 85 else "warn" if pct >= 70 else "ok"

def _num(v):
    return "—" if v is None else str(v)

def _hub_servarr():
    d = HUB_DATA.get("servarr")
    if not d:
        return None
    status = d["status"]
    n, n_up = len(status), sum(1 for v in status.values() if v.get("up"))

    def kvint(svc, key):
        try:
            return int(status.get(svc, {}).get("kv", {}).get(key))
        except (TypeError, ValueError):
            return None
    queues = [kvint("sonarr", "queue"), kvint("radarr", "queue")]
    queue = sum(x for x in queues if x is not None) if any(x is not None for x in queues) else None
    pending, leaving = kvint("overseerr", "pending"), kvint("maintainerr", "leaving")
    metrics = [
        _metric("Services up", n_up, f"/{n}", "all answering" if n_up == n else f"{n - n_up} down",
                "ok" if n_up == n else "bad"),
        _metric("In queue", _num(queue), "", "Sonarr + Radarr", "mute" if queue is None else "ok"),
        _metric("Pending requests", _num(pending), "", "Overseerr",
                "mute" if pending is None else "warn" if pending else "ok"),
        _metric("Leaving soon", _num(leaving), "", "Maintainerr retention", "mute" if leaving is None else "ok"),
    ]
    groups = ""
    for heading, items in SERVARR:
        rows = ""
        for label, svc, slug in items:
            st = status.get(svc, {})
            up = st.get("up", False)
            stat = st.get("stat", "") if up else "down"
            rows += (f'<a class="mrow{"" if up else " off"}" href="https://{svc}.{TS}">'
                     f'<span class="d d-{"ok" if up else "mute"}"></span>{_ico(slug, label, True)}'
                     f'<span class="mrow-name">{html.escape(label)}</span>'
                     f'<span class="mrow-stat{"" if up else " bad"}">{html.escape(stat)}</span></a>')
        groups += f'<div class="mcard"><h3 class="mcap">{html.escape(heading)}</h3>{rows}</div>'
    return {"tile": (_big(n_up, f"/{n}"), "media services up"), "metrics": metrics,
            "body": f'<div class="mgrid">{groups}</div>', "ext": None}

def _hub_proxmox():
    d = HUB_DATA.get("proxmox") or {}
    nodes, pbs = d.get("nodes"), d.get("pbs", [])
    if nodes is None:
        return None
    guests = [g for nd in nodes for g in nd["guests"]]
    vms = sum(1 for g in guests if g[0] == "VM")
    stopped = sum(1 for g in guests if g[3] != "running")
    ok_nodes = sum(1 for nd in nodes if nd["ok"])
    ok_pbs = sum(1 for b in pbs if b["ok"])
    stores = [s for b in pbs for s in b["stores"] if s[3] is not None]
    size, used = sum(s[1] for s in stores), sum(s[2] for s in stores)
    pct = round(100 * used / size) if size else None
    gsub = f"{vms} VMs · {len(guests) - vms} containers" + (f" · {stopped} stopped" if stopped else "")
    metrics = [
        _metric("Nodes", ok_nodes, f"/{len(nodes)}",
                "all online" if ok_nodes == len(nodes) else f"{len(nodes) - ok_nodes} unreachable",
                "ok" if ok_nodes == len(nodes) else "bad"),
        _metric("Guests", len(guests), "", gsub, "warn" if stopped else "ok"),
        _metric("Backup servers", ok_pbs, f"/{len(pbs)}",
                "all reachable" if ok_pbs == len(pbs) else f"{len(pbs) - ok_pbs} unreachable",
                "ok" if ok_pbs == len(pbs) else "bad"),
        _metric("Backup storage", _num(pct), "%" if pct is not None else "",
                f"{human(used)} of {human(size)} used" if size else "no datastore usage",
                _pct_tone(pct) if pct is not None else "mute"),
    ]
    ncards = ""
    for nd in nodes:
        ng = len(nd["guests"])
        right = (f'<span class="r">{ng} guest{"" if ng == 1 else "s"}</span>' if nd["ok"]
                 else '<span class="r bad">unreachable</span>')
        rows = ""
        for kind, vmid, gname, gstatus in sorted(nd["guests"], key=lambda g: (g[0], g[2].lower())):
            on = gstatus == "running"
            rows += (f'<div class="guest{"" if on else " off"}"><span class="d d-{"ok" if on else "mute"}"></span>'
                     f'<span class="kind tint {kind.lower()}">{kind}</span>'
                     f'<span class="n">{html.escape(gname)}</span><span class="id">{html.escape(vmid)}</span></div>')
        ncards += (f'<div class="mcard"><a class="mhd" href="https://{nd["name"]}.{TS}">'
                   f'<span class="d d-{"ok" if nd["ok"] else "bad"}"></span>'
                   f'<span class="mono">{html.escape(nd["name"])}</span>{right}</a>'
                   + (f'<div class="guests">{rows}</div>' if rows else "") + '</div>')
    bcards = ""
    for b in pbs:
        right = ('<span class="r">Proxmox Backup Server</span>' if b["ok"]
                 else '<span class="r bad">unreachable</span>')
        srows = ""
        for sname, ssize, sused, spct in b["stores"]:
            if spct is None:
                srows += (f'<div class="store"><div class="store-row"><span class="mono">{html.escape(sname)}</span>'
                          f'<span class="u">usage unknown</span></div></div>')
                continue
            srows += (f'<div class="store"><div class="store-row"><span class="mono">{html.escape(sname)}</span>'
                      f'<span class="u">{human(sused)} / {human(ssize)}</span><b>{spct}%</b></div>'
                      f'<span class="bar {_pct_tone(spct)}"><span style="width:{spct}%"></span></span></div>')
        bcards += (f'<div class="mcard"><a class="mhd" href="https://{b["name"]}.{TS}">'
                   f'<span class="d d-{"ok" if b["ok"] else "bad"}"></span>'
                   f'<span class="mono">{html.escape(b["name"])}</span>{right}</a>{srows}</div>')
    body = (f'<div class="mgroup"><h3 class="mcap">Virtualization nodes</h3>'
            f'<div class="mgrid" style="--min:210px">{ncards}</div></div>'
            f'<div class="mgroup"><h3 class="mcap">Backup servers</h3>'
            f'<div class="mgrid" style="--min:300px">{bcards}</div></div>')
    return {"tile": (_big(len(guests), "", "guests"), f"across {len(nodes)} nodes · {len(pbs)} backup servers"),
            "metrics": metrics, "body": body, "ext": None}

def _hub_containers():
    d = HUB_DATA.get("containers")
    if not d:
        return None
    hosts = d["hosts"]
    total = running = unhealthy = stopped = reach = 0
    cards = ""
    for h in hosts:
        node = (f'<span class="badge">{html.escape(h["node"])}</span>' if h["node"]
                else '<span class="badge">bare-metal</span>')
        rows = h["rows"]
        if rows is None:
            cards += (f'<div class="hostcard" data-host="{html.escape(h["name"])}"><div class="hosthd">'
                      f'<span class="mono">{html.escape(h["name"])}</span>{node}'
                      f'<span class="r bad">unreachable</span></div></div>')
            continue
        reach += 1
        n_run = sum(1 for _, st, _ in rows if st == "running")
        total += len(rows)
        running += n_run
        chips = ""
        for cname, state, cstatus in sorted(rows, key=lambda r: (0 if r[1] == "running" else 1, r[0].lower())):
            if state == "running":
                bad = "unhealthy" in cstatus.lower()
                unhealthy += bad
                tone, off = ("warn" if bad else "ok"), ""
            else:
                stopped += 1
                tone, off = "mute", " off"
            esc = html.escape(cname)
            inner = f'<span class="d d-{tone}"></span>{esc}'
            if h["name"] in DOCKHAND_HOSTS:
                chips += (f'<a class="ctr{off}" data-name="{esc.lower()}" '
                          f'href="{DOCKHAND + urllib.parse.quote(cname)}">{inner}</a>')
            else:
                chips += f'<span class="ctr{off}" data-name="{esc.lower()}">{inner}</span>'
        width = round(100 * n_run / len(rows)) if rows else 0
        cards += (f'<div class="hostcard" data-host="{html.escape(h["name"])}"><div class="hosthd">'
                  f'<span class="mono">{html.escape(h["name"])}</span>{node}'
                  f'<span class="r"><b>{n_run}</b><span>/{len(rows)} running</span></span></div>'
                  f'<span class="bar{"" if n_run == len(rows) else " warn"}" style="height:4px">'
                  f'<span style="width:{width}%"></span></span><div class="ctrs">{chips}</div></div>')
    metrics = [
        _metric("Running", running, f"/{total}", "fleet-wide", "ok" if running == total else "warn"),
        _metric("Docker hosts", reach, f"/{len(hosts)}",
                "all reachable" if reach == len(hosts) else f"{len(hosts) - reach} unreachable",
                "ok" if reach == len(hosts) else "bad"),
        _metric("Unhealthy", unhealthy, "", "health checks failing" if unhealthy else "none flagged",
                "warn" if unhealthy else "ok"),
        _metric("Stopped", stopped, "", "not running" if stopped else "none stopped",
                "mute" if stopped else "ok"),
    ]
    body = ('<label class="sr" for="mf-containers">Filter containers or hosts</label>'
            '<input id="mf-containers" class="mfilter" type="search" autocomplete="off" '
            'placeholder="Filter containers or hosts…">'
            f'<div class="mgrid" style="--min:280px">{cards}</div>')
    return {"tile": (_big(running, f"/{total}"), "containers running"), "metrics": metrics,
            "body": body, "ext": (f"https://dockhand.{TS}", "Open Dockhand")}

def _hub_zigbee():
    d = HUB_DATA.get("zigbee")
    if not d:
        return None
    servers, radios = d["servers"], d["radios"]
    live = sum(1 for s in servers if s["healthy"])
    radios_up = sum(1 for r in radios if r["up"])
    devs = [s["probe"]["devices"] for s in servers if s["probe"]["devices"] is not None]
    chans = [m.group(1) for r in radios for m in [re.search(r"\bch (\d+)", r["role"])] if m]
    where = [r["role"].split()[0] for r in radios if re.search(r"\bch \d+", r["role"])]
    metrics = [
        _metric("Servers healthy", live, f"/{len(servers)}",
                "frontends answering" if live == len(servers) else f"{len(servers) - live} not healthy",
                "ok" if live == len(servers) else "bad"),
        _metric("Radios reachable", radios_up, f"/{len(radios)}",
                "coordinators up" if radios_up == len(radios) else f"{len(radios) - radios_up} unreachable",
                "ok" if radios_up == len(radios) else "bad"),
        _metric("Devices paired", sum(devs) if devs else "—", "", "across all networks",
                "ok" if devs else "mute"),
        _metric("Channels", " · ".join(chans) or "—", "", " · ".join(where), "ok" if chans else "mute"),
    ]

    def kv(rows):
        bad = ' class="bad"'
        return '<dl class="kv">' + "".join(
            f'<dt>{html.escape(k)}</dt><dd{"" if ok else bad}>{html.escape(v)}</dd>'
            for ok, k, v in rows) + "</dl>"

    scards = ""
    for s in servers:
        p = s["probe"]
        tone = "ok" if s["healthy"] else "bad" if s["running"] and not s["up"] else "warn"
        rows = [(s["up"], "frontend", f'HTTP {p["http"]}'),
                (s["running"], "container", p["state"] or "unknown"),
                (s["configured"], "adapter", p["target"] or "not configured"),
                (bool(p["base_topic"]), "base topic", p["base_topic"] or "—")]
        if p["devices"] is not None:
            rows.append((True, "devices", str(p["devices"])))
        scards += (f'<div class="mcard"><a class="zhd" href="https://{s["svc"]}.{TS}"><span class="l">'
                   f'<span class="mono">{html.escape(s["container"])}</span>'
                   f'<span class="state {tone}"><span class="d d-{tone}"></span>{html.escape(s["note"])}</span></span>'
                   f'<span class="s">on {html.escape(s["host"])}</span></a>{kv(rows)}</div>')
    rcards = ""
    for r in radios:
        tone = "ok" if r["up"] else "bad"
        rows = [(r["up"], "network", "up" if r["up"] else "unreachable"),
                (r["web"], "web UI", f'HTTP {r["code"]}'),
                (r["sock"], f'coordinator :{r["cport"]}', "listening" if r["sock"] else "closed"),
                (bool(r["user"]), "used by", r["user"] or "unused")]
        tag, end = (f'<a class="zhd" href="http://{r["ip"]}/">', "</a>") if r["up"] else ('<div class="zhd">', "</div>")
        rcards += (f'<div class="mcard">{tag}<span class="l"><span class="mono">{html.escape(r["label"])}</span>'
                   f'<span class="state {tone}"><span class="d d-{tone}"></span>{"up" if r["up"] else "unreachable"}</span></span>'
                   f'<span class="s">{html.escape(r["model"])} · {html.escape(r["ip"])} · {html.escape(r["role"])}</span>'
                   f'{end}{kv(rows)}</div>')
    body = (f'<div class="mgroup"><h3 class="mcap">Zigbee2MQTT servers</h3>'
            f'<div class="mgrid" style="--min:320px">{scards}</div></div>'
            f'<div class="mgroup"><h3 class="mcap">SLZB radios</h3>'
            f'<div class="mgrid" style="--min:320px">{rcards}</div></div>')
    return {"tile": (_big(radios_up, f"/{len(radios)}", "radios"),
                     f"{live} Zigbee2MQTT server{'' if live == 1 else 's'} healthy"),
            "metrics": metrics, "body": body, "ext": None}

HUB_BUILDERS = {"servarr": _hub_servarr, "proxmox": _hub_proxmox,
                "containers": _hub_containers, "zigbee": _hub_zigbee}

def _modal(name, hub, now):
    title, blurb = HUB_INFO[name]
    hue = CATEGORY_HUE.get(HUB_CATEGORY.get(name, "Other"), 210)
    ext = ""
    if hub["ext"]:
        url, label = hub["ext"]
        ext = f'<a class="mbtn" href="{url}">{html.escape(label)}{_svg("out", 14)}</a>'
    return (f'<dialog class="hubdlg" id="hub-{name}" tabindex="-1" aria-labelledby="hub-{name}-t" style="--h:{hue}">'
            f'<div class="mhead"><span class="mico tint">{_svg(name, 22)}</span>'
            f'<div class="mtitle"><div class="mtl"><h2 id="hub-{name}-t">{html.escape(title)}</h2>'
            f'<span class="mono">{name}</span></div><p>{html.escape(blurb)}</p></div>'
            f'<div class="mact">{ext}<button type="button" class="mbtn" data-copy="{name}">'
            f'{_svg("link", 14)}<span aria-live="polite">Copy link</span></button>'
            f'<button type="button" class="xbtn" data-close aria-label="Close">{_svg("x", 20)}</button></div></div>'
            f'<div class="mbody"><div class="metrics">{"".join(hub["metrics"])}</div>{hub["body"]}'
            f'<p class="mfoot">Direct link <span class="mono">home.{TS}/#{name}</span> · generated '
            f'{html.escape(now)} · <kbd>Esc</kbd> closes</p></div></dialog>')

def render_home():
    static = _desired_file("/etc/ts-static-serves.txt")
    hubs_file = _desired_file("/etc/ts-static-serves-hubs.txt")

    discovered = tailnet_services()
    if not discovered:
        # Netmap unreadable. Union the two local desired-state files rather than
        # emitting an index that claims the tailnet is empty — an incomplete page
        # is recoverable, a confidently-blank one is what sbhome did.
        discovered = set(static) | set(hubs_file)
    dock = docktail_services()

    # Hub pages still served as their own VIPs are not listed as services: the hub
    # is reached through its modal here. Once those VIPs are retired this set is
    # simply empty.
    hub_vips = set(hubs_file) & discovered
    names = discovered - {"home"}
    listed = sorted(names - hub_vips)
    up = vip_status(listed)

    def origin(name):
        if name in dock:
            host, state = dock[name]
            return (f"container on {host}" if state == "running"
                    else f"container on {host} ({state})")
        if name in static:
            return "→ " + static[name].split("://", 1)[-1]
        return ""

    # The modals are built from what the hub renderers collected into HUB_DATA, NOT
    # from whether a hub VIP exists -- that is what lets the hub VIPs be retired
    # without the drill-downs disappearing with them.
    hubs = {n: h for n in HUB_ORDER for h in [HUB_BUILDERS[n]()] if h}
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M %Z").strip()
    host = os.uname().nodename

    def tile(name):
        slug, blurb = HOME_META.get(name, (None, ""))
        desc = blurb or origin(name)
        ok = up.get(name, False)
        # A stopped container is the reason a link is dead — say so instead of
        # just greying the dot.
        if not ok and name in dock and dock[name][1] != "running":
            desc = origin(name)
        if not ok and not desc:
            desc = "Not serving right now"
        tag = "" if ok else '<span class="tag">Offline</span>'
        return (f'<a class="tile{"" if ok else " off"}" href="https://{name}.{TS}" data-name="{html.escape(name)}" '
                f'data-k="{html.escape((name + " " + desc).lower())}">{_ico(slug, name)}'
                f'<span class="tbody"><span class="tname">{html.escape(name)}</span>'
                f'<span class="tdesc">{html.escape(desc)}</span></span>'
                f'<span class="tend">{tag}<span class="d d-{"ok" if ok else "mute"}" '
                f'title="{"Serving" if ok else "Not serving right now"}"></span>{_svg("out", 16, "go")}</span></a>')

    groups = []
    uncategorised = set(listed)
    for heading, members in HOME_CATEGORIES:
        present = [m for m in members if m in listed]
        uncategorised -= set(present)
        if present:
            groups.append((heading, present))
    if uncategorised:
        groups.append(("Other", sorted(uncategorised)))

    sections, chips = [], []
    total = sum(len(m) for _, m in groups)
    chips.append(f'<button type="button" class="chip" data-cat="all" aria-pressed="true">All'
                 f'<span class="cc">{total}</span></button>')
    for heading, members in groups:
        slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
        hub = CATEGORY_HUBS.get(heading)
        hub = hub if hub in hubs else None
        link = ""
        if hub:
            summary = HUB_SUMMARY.get(hub, "")
            link = (f'<a class="hublink" href="#{hub}" data-hub="{hub}" aria-haspopup="dialog">'
                    f'{html.escape(summary)}<span class="mono">{hub}</span>{_svg("expand", 14)}</a>')
        # The section's own data-k carries the heading AND the hub name, so typing
        # `proxmox` finds the Virtualization section.
        key = html.escape((heading + " " + (hub or "")).strip().lower())
        sections.append(
            f'<section class="svc" data-cat="{slug}" data-k="{key}" data-hub="{hub or ""}" '
            f'aria-label="{html.escape(heading)}" style="--h:{CATEGORY_HUE.get(heading, 210)}">'
            f'<div class="shead"><span class="swatch"></span><h3>{html.escape(heading)}</h3>'
            f'<span class="scount">{len(members)} services</span>{link}</div>'
            f'<div class="tiles">{"".join(tile(m) for m in members)}</div></section>')
        chips.append(f'<button type="button" class="chip" data-cat="{slug}" aria-pressed="false">'
                     f'{html.escape(heading)}<span class="cc">{len(members)}</span></button>')

    hub_cards = ""
    for name, h in hubs.items():
        hue = CATEGORY_HUE.get(HUB_CATEGORY.get(name, "Other"), 210)
        big, label = h["tile"]
        hub_cards += (f'<a class="hub" href="#{name}" data-hub="{name}" aria-haspopup="dialog" style="--h:{hue}">'
                      f'<span class="hub-top"><span class="hub-ico tint">{_svg(name)}</span>'
                      f'<span class="hub-name">{name}</span>{_svg("expand", 16, "exp")}</span>'
                      f'<span class="hub-num">{big}<span class="hub-lbl">{html.escape(label)}</span></span></a>')
    hubs_html = (f'<section class="hubs" aria-labelledby="hubs-t"><h2 id="hubs-t" class="cap">Topic hubs</h2>'
                 f'<div class="hubgrid">{hub_cards}</div></section>') if hubs else ""
    nav = "".join(f'<a href="#{n}" data-hub="{n}" aria-haspopup="dialog">{n}</a>' for n in hubs)

    dark = [n for n in listed if not up.get(n, False)]
    n_up = len(listed) - len(dark)
    pill_title = f' title="Not serving: {html.escape(", ".join(dark))}"' if dark else ""
    icon_css = "".join(f'.{k}{{background-image:url("{v}")}}' for k, v in _ICON_CSS.items())
    modals = "".join(_modal(n, h, now) for n, h in hubs.items())

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light">
<title>Homelab</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&amp;family=JetBrains+Mono:wght@400;500;600&amp;display=swap">
<style>{HOME_CSS}{icon_css}</style></head><body>
<header class="top"><div class="wrap">
<a class="brand" href="/"><span class="brand-mark">{_svg("brand", 20)}</span>
<span class="brand-txt"><b>Homelab</b><span>{TS}</span></span></a>
<nav class="hubnav" aria-label="Topic hubs">{nav}</nav>
<span class="pill{" warn" if dark else ""}"{pill_title}><span class="d d-ok"></span><span>{n_up} of {len(listed)} serving</span></span>
</div></header>
<main class="wrap">
<section class="hero" aria-labelledby="hero-t">
<p class="eyebrow">Service index</p>
<h1 id="hero-t">Every service on the tailnet, one name away.</h1>
<p class="lede">Each name below is its own address: <span class="mono">&lt;name&gt;.{TS}</span>. Type to find one, press Enter to open it.</p>
<div class="search"><label class="sr" for="q">Filter services</label>
<div class="sbox">{_svg("search", 20)}<input id="q" type="search" autocomplete="off" autofocus placeholder="Filter services… try “arr” or “proxmox”"><span id="cnt" class="scnt" data-all="{total} services">{total} services</span></div>
<p class="hint"><span><kbd>Enter</kbd> opens the first match</span><span><kbd>Esc</kbd> clears</span><span id="next" hidden>→ <span id="next-name" class="mono"></span></span></p>
</div></section>
{hubs_html}
<section aria-labelledby="svc-t">
<div class="chipbar"><h2 id="svc-t" class="cap">Services</h2>{"".join(chips)}</div>
{"".join(sections)}
<div id="empty" class="empty" hidden><p class="t">Nothing on the tailnet matches “<span id="empty-q"></span>”.</p>
<p class="s">Search covers names, descriptions and categories.</p>
<button type="button" id="clear">Clear the filter</button></div>
</section>
</main>
<footer><div class="wrap"><span>Generated {html.escape(now)} on <span class="mono">{html.escape(host)}</span> · refreshes every 15 minutes</span>
<span class="r">Source: tailnet netmap, one entry per VIP service</span></div></footer>
{modals}
<script>{HOME_JS}</script>
</body></html>"""


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    # The topic hubs are modals on home since 2026-10-10 and their VIPs are retired,
    # so only home.html is written. The hub renderers still run FIRST: they gather
    # the data home's modals are built from (HUB_DATA, HUB_SUMMARY). Their page
    # output is discarded.
    for fn in (render_proxmox, render_servarr, render_containers, render_zigbee):
        fn()
    out = render_home()
    with open(os.path.join(OUTDIR, "home.html"), "w") as f:
        f.write(out)
    print(f"wrote home.html ({len(out)} bytes)")
    # Pages left from when the hubs were served on their own.
    for stale in ("proxmox", "servarr", "containers", "zigbee"):
        try:
            os.remove(os.path.join(OUTDIR, stale + ".html"))
            print(f"removed stale {stale}.html")
        except FileNotFoundError:
            pass

if __name__ == "__main__":
    main()
