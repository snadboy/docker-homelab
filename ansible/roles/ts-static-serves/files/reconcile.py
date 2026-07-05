#!/usr/bin/env python3
"""Reconcile Tailscale serves on a ts-advertiser VM. Manages two kinds:
  - PROXY serves from /etc/ts-static-serves.txt   (lines: "name target")
  - HUB file serves from /etc/ts-static-serves-hubs.txt (lines: "name /path.html")
Idempotent: only SETs changed/missing, CLEARs any svc not in either list."""
import json, subprocess

def load(path, default_map=lambda n, v: v):
    d = {}
    try:
        for ln in open(path):
            ln = ln.strip()
            if not ln or ln.startswith("#"): continue
            n, v = ln.split(None, 1)
            d[n] = v
    except FileNotFoundError:
        pass
    return d

proxies = load("/etc/ts-static-serves.txt")
hubs = load("/etc/ts-static-serves-hubs.txt")
desired = set(proxies) | set(hubs)

st = json.loads(subprocess.run(["tailscale", "serve", "status", "--json"],
        capture_output=True, text=True).stdout or "{}")
services = st.get("Services") or {}

def handler(svc, field):
    for host, cfg in (svc.get("Web") or {}).items():
        v = (cfg.get("Handlers") or {}).get("/", {}).get(field)
        if v: return v
    return None

changed = False
for name, target in proxies.items():
    key = "svc:" + name
    cur = (handler(services.get(key, {}), "Proxy") or "").rstrip("/")
    if cur != target.rstrip("/"):
        subprocess.run(["tailscale", "serve", "--service=" + key, "--https=443", "--bg", target], check=True)
        print("SET", key, target); changed = True

for name, path in hubs.items():
    key = "svc:" + name
    cur = handler(services.get(key, {}), "Path")
    if cur != path:
        subprocess.run(["tailscale", "serve", "--service=" + key, "--https=443", "--bg", path], check=True)
        print("SET-HUB", key, path); changed = True

for key in list(services.keys()):
    if key.split(":", 1)[1] not in desired:
        subprocess.run(["tailscale", "serve", "clear", key], check=True)
        print("CLEAR", key); changed = True

print("CHANGED" if changed else "OK")
