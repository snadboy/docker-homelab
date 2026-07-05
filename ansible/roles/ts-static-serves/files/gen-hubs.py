#!/usr/bin/env python3
"""Generate static hub (mini-homepage) HTML for Tailscale Services.
Runs on a ts-advertiser VM; gathers live data via Tailscale SSH to the nodes
(advertiser has tag:ssh). Writes self-contained HTML to OUTDIR.
Hubs: pve (guest map), pbs (datastore usage), servarr (icons), containers."""
import subprocess, html, os, datetime, json, urllib.request, urllib.parse

TS = "swallow-spectrum.ts.net"
DOCKHAND = f"https://dockhand.{TS}/containers?search="  # + urlencoded container name
OUTDIR = "/var/lib/ts-hubs"
ICONDIR = os.path.join(OUTDIR, "icons")
ICON_CDN = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/{}.svg"

PVE_NODES = [("euler", "pve-euler"), ("gauss", "pve-gauss"), ("maxwell", "pve-maxwell")]
PBS_NODES = [("alexandria", "pbs-alexandria"), ("svalbard", "pbs-svalbard")]

# Servarr: (label, svc-name, icon-slug on dashboard-icons)
SERVARR = [
    ("Indexers",   [("Prowlarr", "prowlarr", "prowlarr")]),
    ("Managers",   [("Sonarr", "sonarr", "sonarr"), ("Radarr", "radarr", "radarr"),
                    ("Bazarr", "bazarr", "bazarr"), ("Agregarr", "agregarr", None)]),
    ("Requests",   [("Overseerr", "overseerr", "overseerr")]),
    ("Download",   [("SABnzbd", "sabnzbd", "sabnzbd")]),
    ("Monitoring", [("Tautulli", "tautulli", "tautulli"), ("Tracearr", "tracearr", None)]),
]

# Docker hosts: (host, node-or-None, access) access = ("ssh",user,host) | ("pct",pvehost,vmid)
DOCKER_HOSTS = [
    ("utilities", "euler",   ("ssh", "snadboy", "utilities")),
    ("arr",       "gauss",   ("ssh", "snadboy", "arr")),
    ("fetch",     "gauss",   ("ssh", "snadboy", "fetch")),
    ("cadre",     "maxwell", ("ssh", "snadboy", "cadre")),
    ("bedrock",   "maxwell", ("ssh", "snadboy", "bedrock")),
    ("plex-lxc",  "euler",   ("pct", "pve-euler", "107")),
    ("sdevs",     None,      ("ssh", "snadboy", "sdevs")),
]

def ssh(host, cmd, user="root", timeout=20):
    try:
        r = subprocess.run(["ssh", "-o", "StrictHostKeyChecking=accept-new",
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
a.svc{color:var(--link);text-decoration:none;display:flex;align-items:center;gap:.55rem}
a.svc:hover{text-decoration:underline}
.ico{width:22px;height:22px;flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center}
.ico svg{width:22px;height:22px}
.badge-ico{background:var(--edge);color:var(--fg);border-radius:5px;font-size:.7rem;font-weight:700}
.bar{height:7px;border-radius:4px;background:var(--edge);overflow:hidden;margin:.35rem 0 .1rem}
.bar > span{display:block;height:100%}
.bar-lo>span{background:var(--ok)}.bar-mid>span{background:var(--warn)}.bar-hi>span{background:var(--off)}
.usage{font-size:.78rem;color:var(--dim)}
.search{display:flex;align-items:center;gap:.75rem;margin:-.5rem 0 1.5rem}
.search input{flex:0 1 360px;background:var(--card);border:1px solid var(--edge);
border-radius:8px;color:var(--fg);padding:.55rem .8rem;font-size:.9rem;outline:none}
.search input:focus{border-color:var(--link)}
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

def render_pve():
    cards = []
    for name, host in PVE_NODES:
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
    return page("Proxmox VE Cluster", "Nodes and the guests they host — click a node for its web UI.",
                '<div class="grid">' + "".join(cards) + "</div>")

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

def render_pbs():
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
    return page("Proxmox Backup Servers", "Backup servers and datastore usage — click for the web UI.",
                '<div class="grid">' + "".join(cards) + "</div>")

# ---------- servarr ----------
def render_servarr():
    cards = []
    for heading, items in SERVARR:
        links = ""
        for label, svc, slug in items:
            links += (f'<li><a class="svc" href="https://{svc}.{TS}">'
                      f'{icon_or_badge(label, slug)}<span>{html.escape(label)}</span></a></li>')
        cards.append(f'<div class="card"><h2>{html.escape(heading)}</h2><ul>{links}</ul></div>')
    return page("Media Automation", "The Servarr media stack — click any service to open it.",
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
              'autocomplete="off" autofocus><span id="cnt" class="usage"></span></div>')
    return page("Docker Containers",
                f"All containers across the fleet — {running_total} running of {total} total, grouped by host with "
                f"its PVE node. Green = running, amber = unhealthy, grey = stopped. Click a container to open it in Dockhand.",
                search + '<div class="grid">' + "".join(cards) + "</div>" + SEARCH_JS)

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    for name, fn in [("pve", render_pve), ("pbs", render_pbs),
                     ("servarr", render_servarr), ("containers", render_containers)]:
        out = fn()
        with open(os.path.join(OUTDIR, name + ".html"), "w") as f:
            f.write(out)
        print(f"wrote {name}.html ({len(out)} bytes)")

if __name__ == "__main__":
    main()
