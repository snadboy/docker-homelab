#!/usr/bin/env python3
"""Reconcile Tailscale static serves to /etc/ts-static-serves.txt (name target).
Idempotent: only SETs changed/missing services, CLEARs extras. These advertiser
VMs do ONLY static serves, so any svc: not in the list is removed."""
import json, subprocess

desired = {}
for ln in open("/etc/ts-static-serves.txt"):
    ln = ln.strip()
    if not ln or ln.startswith("#"): continue
    n, t = ln.split()
    desired[n] = t

st = json.loads(subprocess.run(["tailscale","serve","status","--json"],
        capture_output=True, text=True).stdout or "{}")
services = st.get("Services") or {}

def cur_target(svc):
    for host, cfg in (svc.get("Web") or {}).items():
        p = (cfg.get("Handlers") or {}).get("/", {}).get("Proxy")
        if p: return p
    return None

changed = False
for name, target in desired.items():
    key = "svc:" + name
    cur = (cur_target(services.get(key, {})) or "").rstrip("/")
    want = target.rstrip("/")
    if cur != want:
        subprocess.run(["tailscale","serve","--service="+key,"--https=443","--bg",target], check=True)
        print("SET", key, target); changed = True

for key in list(services.keys()):
    if key.split(":",1)[1] not in desired:
        subprocess.run(["tailscale","serve","clear",key], check=True)
        print("CLEAR", key); changed = True

print("CHANGED" if changed else "OK")
