#!/usr/bin/env python3
"""Generate static hub (mini-homepage) HTML for Tailscale Services.
Runs on a ts-advertiser VM; gathers live data via Tailscale SSH to the nodes
(advertiser has tag:ssh). Writes self-contained HTML to OUTDIR.
Hubs: pve (guest map), pbs (datastore usage), servarr (icons), containers."""
import subprocess, html, os, datetime, json, urllib.request, urllib.parse, urllib.error

TS = "swallow-spectrum.ts.net"
DOCKHAND = f"https://dockhand.{TS}/containers?search="  # + urlencoded container name
OUTDIR = "/var/lib/ts-hubs"
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

def icon_or_badge(label, slug):
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
    cards = []
    for name, host in discover_pve_nodes():
        ok, guests = pve_guests(host)
        url = f"https://{name}.{TS}"
        rows = ""
        for kind, vmid, gname, status in sorted(guests, key=lambda g: (g[0], g[2].lower())):
            on = "on" if status == "running" else "off"
            rows += (f'<li><span class="dot {on}"></span><span class="badge">{kind}</span>'
                     f'<span class="gname">{html.escape(gname)}</span><span class="gid">{vmid}</span></li>')
        state = f"{len(guests)} guests" if ok else '<span style="color:var(--off)">unreachable</span>'
        cards.append(f'<div class="card"><h2><a href="{url}">{html.escape(name)}</a></h2>'
                     f'<p class="meta">Proxmox VE · {state}</p><ul>{rows}</ul></div>')
    return '<div class="grid">' + "".join(cards) + "</div>"

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
    for name, host in PBS_NODES:
        ok, stores = pbs_stores(host)
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
    body = (f'<h3 class="section">Virtualization</h3>{pve_cards()}'
            f'<h3 class="section">Backup</h3>{pbs_cards()}')
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
        res[svc] = {"up": bool(code) and code != "000", "stat": _fmt_stat(svc, kv)}
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
    for hostname, node, access in DOCKER_HOSTS:
        rows = docker_ps(access)
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
Z2M_INSTANCES = [
    ("zigbee2mqtt-upstairs", "utilities", 8082, "zigbee2mqtt-upstairs"),
    ("zigbee2mqtt-basement", "utilities", 8086, "zigbee2mqtt-basement"),
    ("zigbee2mqtt-office",   "edge",      8082, "zigbee2mqtt-office"),
    ("zigbee2mqtt-laundry",  "edge",      8083, "zigbee2mqtt-laundry"),
]

# SLZB radios: (label, model, ip, coordinator tcp port). Laundry sits on the
# 192.168.10.0/24 VLAN, not the main LAN - the advertiser can still reach it.
# (label, model, ip, coordinator tcp port, role). Physical locations confirmed by the
# user 2026-09-01 - HA's area labels for these are WRONG and must not be trusted.
SLZB_RADIOS = [
    ("SLZB-MR1U-HOUSE", "SLZB-MR1U", "192.168.86.130", 7638, "upstairs (office) - coordinator"),
    ("SLZB-MR1U",       "SLZB-MR1U", "192.168.86.245", 7638, "basement (laundry) - coordinator, PoE"),
    ("SLZB-06M",        "SLZB-06M",  "192.168.10.33",  6638, "SPARE - location unknown"),
    ("SLZB-06M",        "SLZB-06M",  "192.168.86.251", 6638, "SPARE - unplugged"),
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

    body = (f'<h3 class="section">Zigbee2MQTT servers</h3><div class="grid">{"".join(cards)}</div>'
            f'<h3 class="section">SLZB radios</h3><div class="grid">{"".join(rcards)}</div>')
    return page("Zigbee",
                f"Zigbee2MQTT servers and SLZB coordinator radios — {live} fully-configured server(s) responding, "
                f"{radios_up}/{len(SLZB_RADIOS)} radios reachable. A server whose container is up but whose "
                f"frontend does not answer has died inside a healthy-looking container. Click a server or radio to open it.",
                body)

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    for name, fn in [("proxmox", render_proxmox),
                     ("servarr", render_servarr), ("containers", render_containers),
                     ("zigbee", render_zigbee)]:
        out = fn()
        with open(os.path.join(OUTDIR, name + ".html"), "w") as f:
            f.write(out)
        print(f"wrote {name}.html ({len(out)} bytes)")

if __name__ == "__main__":
    main()
