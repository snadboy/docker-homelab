#!/usr/bin/env python3
"""Generate static hub (mini-homepage) HTML for Tailscale Services.
Runs on a ts-advertiser VM; gathers live workload maps via Tailscale SSH to the
PVE/PBS nodes (advertiser has tag:ssh). Writes self-contained HTML to OUTDIR.
Served by `tailscale serve --service=svc:<hub> --https=443 <file>`."""
import subprocess, html, os, datetime, sys

TS = "swallow-spectrum.ts.net"
OUTDIR = "/var/lib/ts-hubs"

PVE_NODES = [
    ("euler",   "pve-euler"),
    ("gauss",   "pve-gauss"),
    ("maxwell", "pve-maxwell"),
]
PBS_NODES = [
    ("alexandria", "pbs-alexandria"),
    ("svalbard",   "pbs-svalbard"),
]
SERVARR = [
    ("Indexers",   [("Prowlarr", "prowlarr")]),
    ("Managers",   [("Sonarr", "sonarr"), ("Radarr", "radarr"),
                    ("Bazarr", "bazarr"), ("Agregarr", "agregarr")]),
    ("Requests",   [("Overseerr", "overseerr")]),
    ("Download",   [("SABnzbd", "sabnzbd")]),
    ("Monitoring", [("Tautulli", "tautulli"), ("Tracearr", "tracearr")]),
]

def ssh(host, cmd):
    try:
        r = subprocess.run(["ssh", "-o", "StrictHostKeyChecking=accept-new",
                            "-o", "ConnectTimeout=8", "root@" + host, cmd],
                           capture_output=True, text=True, timeout=20)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None

def pve_guests(host):
    """Return (reachable, [ (kind, vmid, name, status) ]) for a PVE node."""
    out = ssh(host, "qm list 2>/dev/null; echo ===; pct list 2>/dev/null")
    if out is None:
        return False, []
    guests, section = [], "VM"
    for ln in out.splitlines():
        if ln.strip() == "===":
            section = "CT"; continue
        p = ln.split()
        if not p or p[0] in ("VMID",):
            continue
        if section == "VM" and len(p) >= 3:
            guests.append(("VM", p[0], p[1], p[2]))
        elif section == "CT" and len(p) >= 3:
            guests.append(("CT", p[0], p[2], p[1]))
    return True, guests

def pbs_datastores(host):
    out = ssh(host, "proxmox-backup-manager datastore list --output-format json 2>/dev/null")
    if out is None:
        return False, []
    try:
        import json
        return True, [d.get("name", "?") for d in json.loads(out)]
    except Exception:
        return True, []

CSS = """
:root{--bg:#0f1216;--card:#171c22;--edge:#232b34;--fg:#e6edf3;--dim:#8b98a5;
--accent:#c9a227;--ok:#3fb950;--off:#f85149;--link:#58a6ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:2rem}
.wrap{max-width:1000px;margin:0 auto}
h1{font-size:1.5rem;margin:0 0 .25rem;letter-spacing:.5px}
.sub{color:var(--dim);margin:0 0 1.75rem;font-size:.85rem}
.grid{display:grid;gap:1rem;grid-template-columns:repeat(auto-fill,minmax(280px,1fr))}
.card{background:var(--card);border:1px solid var(--edge);border-radius:12px;padding:1.1rem 1.25rem}
.card h2{margin:0 0 .1rem;font-size:1.05rem}
.card h2 a{color:var(--link);text-decoration:none}.card h2 a:hover{text-decoration:underline}
.meta{color:var(--dim);font-size:.78rem;margin:0 0 .75rem}
ul{list-style:none;margin:.5rem 0 0;padding:0}
li{display:flex;align-items:center;gap:.5rem;padding:.2rem 0;font-size:.9rem}
.badge{font-size:.62rem;font-weight:700;padding:.05rem .35rem;border-radius:4px;
background:var(--edge);color:var(--dim)}
.dot{width:8px;height:8px;border-radius:50%;flex:0 0 auto}
.dot.on{background:var(--ok)}.dot.off{background:var(--off)}
.gname{flex:1}.gid{color:var(--dim);font-size:.72rem}
.groups .card{padding-bottom:.5rem}
.foot{color:var(--dim);font-size:.72rem;margin-top:2rem;text-align:center}
a.svc{color:var(--link);text-decoration:none}a.svc:hover{text-decoration:underline}
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

def render_pve():
    cards = []
    for name, host in PVE_NODES:
        ok, guests = pve_guests(host)
        url = f"https://{name}.{TS}"
        rows = ""
        for kind, vmid, gname, status in sorted(guests, key=lambda g: (g[0], g[2].lower())):
            on = "on" if status == "running" else "off"
            rows += (f'<li><span class="dot {on}"></span>'
                     f'<span class="badge">{kind}</span>'
                     f'<span class="gname">{html.escape(gname)}</span>'
                     f'<span class="gid">{vmid}</span></li>')
        state = f"{len(guests)} guests" if ok else '<span style="color:var(--off)">unreachable</span>'
        cards.append(f'<div class="card"><h2><a href="{url}">{html.escape(name)}</a></h2>'
                     f'<p class="meta">Proxmox VE · {state}</p><ul>{rows}</ul></div>')
    return page("Proxmox VE Cluster", "Nodes and the guests they host — click a node for its web UI.",
                '<div class="grid">' + "".join(cards) + "</div>")

def render_pbs():
    cards = []
    for name, host in PBS_NODES:
        ok, stores = pbs_datastores(host)
        url = f"https://{name}.{TS}"
        rows = "".join(f'<li><span class="badge">DS</span><span class="gname">{html.escape(s)}</span></li>'
                       for s in stores)
        state = (f"{len(stores)} datastores" if ok else
                 '<span style="color:var(--off)">unreachable</span>')
        cards.append(f'<div class="card"><h2><a href="{url}">{html.escape(name)}</a></h2>'
                     f'<p class="meta">Proxmox Backup Server · {state}</p><ul>{rows}</ul></div>')
    return page("Proxmox Backup Servers", "Backup servers and their datastores — click for the web UI.",
                '<div class="grid">' + "".join(cards) + "</div>")

def render_servarr():
    cards = []
    for heading, items in SERVARR:
        links = "".join(f'<li><a class="svc" href="https://{svc}.{TS}">{html.escape(label)}</a></li>'
                        for label, svc in items)
        cards.append(f'<div class="card"><h2>{html.escape(heading)}</h2><ul>{links}</ul></div>')
    return page("Media Automation", "The Servarr media stack — click any service to open it.",
                '<div class="grid groups">' + "".join(cards) + "</div>")

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    for name, fn in [("pve", render_pve), ("pbs", render_pbs), ("servarr", render_servarr)]:
        html_out = fn()
        with open(os.path.join(OUTDIR, name + ".html"), "w") as f:
            f.write(html_out)
        print(f"wrote {name}.html ({len(html_out)} bytes)")

if __name__ == "__main__":
    main()
