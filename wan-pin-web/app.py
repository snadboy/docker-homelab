"""
wan-pin-web v2: lists all UniFi clients in a table, with WAN-pin buttons
per row. Click a WAN to pin a device; click Default to remove the pin.

Routes follow naming convention 'wan-pin:<friendly>:wan<n>' (matches the
docker-homelab/tools/wan-pin CLI). When you click a WAN button on a
client that isn't yet managed, the server creates the three routes
automatically before enabling the chosen WAN.
"""
from __future__ import annotations
import json
import os
import re
import ssl
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

WAN_NAMES = {
    "1": os.environ.get("WAN1_NAME", "Internet 1"),
    "2": os.environ.get("WAN2_NAME", "Internet 2"),
    "3": os.environ.get("WAN3_NAME", "UniFi 5G A"),
}
ROUTE_PREFIX = "wan-pin:"

UNIFI_URL = os.environ.get("UNIFI_URL", "https://192.168.86.1").rstrip("/")
UNIFI_USER = os.environ["UNIFI_USER"]
UNIFI_PASSWORD = os.environ["UNIFI_PASSWORD"]

app = FastAPI(title="wan-pin", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory="/app/templates")


class UniFi:
    def __init__(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ctx),
            urllib.request.HTTPCookieProcessor(self.jar),
        )
        self.csrf: Optional[str] = None
        self._login()

    def _login(self):
        body = json.dumps({"username": UNIFI_USER, "password": UNIFI_PASSWORD}).encode()
        req = urllib.request.Request(
            f"{UNIFI_URL}/api/auth/login", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with self.opener.open(req) as r:
            self.csrf = r.headers.get("X-CSRF-Token") or r.headers.get("x-csrf-token")
            r.read()
        if not self.csrf:
            with self.opener.open(f"{UNIFI_URL}/proxy/network/api/s/default/self") as r:
                self.csrf = r.headers.get("X-CSRF-Token") or r.headers.get("x-csrf-token")
                r.read()

    def _req(self, method: str, path: str, body=None):
        headers = {"Accept": "application/json"}
        if self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(UNIFI_URL + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req) as r:
                self.csrf = r.headers.get("X-CSRF-Token") or self.csrf
                txt = r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", errors="replace")
            raise HTTPException(status_code=502, detail=f"UniFi API {e.code}: {txt[:300]}")
        if not txt:
            return None
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            return txt

    def list_routes(self) -> list:
        d = self._req("GET", "/proxy/network/v2/api/site/default/trafficroutes")
        return d if isinstance(d, list) else []

    def list_wan_networks(self) -> list:
        d = (self._req("GET", "/proxy/network/api/s/default/rest/networkconf") or {}).get("data", [])
        return [n for n in d if (n.get("purpose") or "").lower() == "wan"]

    def wan_id_for(self, n: str) -> str:
        target = WAN_NAMES.get(n)
        if not target:
            raise HTTPException(status_code=400, detail=f"unknown WAN '{n}'")
        for net in self.list_wan_networks():
            if net.get("name") == target:
                return net["_id"]
        raise HTTPException(status_code=500, detail=f"UniFi has no WAN named '{target}'")

    def list_clients(self) -> list[dict]:
        active = (self._req("GET", "/proxy/network/api/s/default/stat/sta") or {}).get("data", [])
        users = (self._req("GET", "/proxy/network/api/s/default/rest/user") or {}).get("data", [])
        by_mac: dict[str, dict] = {}
        for u in users:
            mac = (u.get("mac") or "").lower()
            if not mac:
                continue
            by_mac[mac] = {
                "mac": mac,
                "name": u.get("name"),
                "hostname": u.get("hostname"),
                "ip": u.get("fixed_ip") or u.get("last_ip"),
                "is_wired": bool(u.get("is_wired")),
                "is_active": False,
                "last_seen": u.get("last_seen"),
                "oui": u.get("oui"),
            }
        for a in active:
            mac = (a.get("mac") or "").lower()
            if not mac:
                continue
            c = by_mac.setdefault(mac, {
                "mac": mac, "name": None, "hostname": None, "ip": None,
                "is_wired": False, "is_active": False, "last_seen": None, "oui": None,
            })
            c["ip"] = a.get("ip") or c["ip"]
            if not c.get("name"):
                c["name"] = a.get("name") or a.get("hostname")
            if not c.get("hostname"):
                c["hostname"] = a.get("hostname")
            c["is_wired"] = bool(a.get("is_wired", c.get("is_wired")))
            c["is_active"] = True
            c["last_seen"] = a.get("last_seen") or c["last_seen"]
            c["oui"] = a.get("oui") or c.get("oui")
        return list(by_mac.values())


def parse_managed_routes(routes):
    by_device: dict[str, dict[str, dict]] = {}
    for r in routes:
        desc = r.get("description") or ""
        if not desc.startswith(ROUTE_PREFIX):
            continue
        m = re.fullmatch(rf"{re.escape(ROUTE_PREFIX)}(.+):wan([0-9]+)", desc)
        if not m:
            continue
        by_device.setdefault(m.group(1), {})[m.group(2)] = r
    return by_device


def routes_by_mac(routes):
    out = {}
    for friendly, by_wan in parse_managed_routes(routes).items():
        any_route = next(iter(by_wan.values()))
        td = (any_route.get("target_devices") or [])
        if not td:
            continue
        mac = (td[0].get("client_mac") or "").lower()
        if mac:
            out[mac] = (friendly, by_wan)
    return out


def derive_friendly(client: dict) -> str:
    for key in ("name", "hostname"):
        v = (client.get(key) or "").strip()
        if v:
            slug = re.sub(r"[^a-z0-9-]+", "-", v.lower()).strip("-")
            if slug:
                return slug
    return client["mac"].replace(":", "")


def create_routes_for(u: UniFi, client: dict, friendly: str):
    mac = client["mac"]
    for n in WAN_NAMES:
        body = {
            "description": f"{ROUTE_PREFIX}{friendly}:wan{n}",
            "enabled": False,
            "kill_switch_enabled": True,
            "matching_target": "INTERNET",
            "network_id": u.wan_id_for(n),
            "target_devices": [{"client_mac": mac, "type": "CLIENT"}],
            "ip_addresses": [], "ip_ranges": [], "domains": [], "regions": [],
        }
        u._req("POST", "/proxy/network/v2/api/site/default/trafficroutes", body)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, show_all: bool = False):
    u = UniFi()
    clients = u.list_clients()
    pin_by_mac = routes_by_mac(u.list_routes())

    for c in clients:
        friendly, by_wan = pin_by_mac.get(c["mac"], (None, {}))
        c["friendly"] = friendly
        c["pin_active"] = next((n for n, r in by_wan.items() if r.get("enabled")), None)
        c["managed"] = friendly is not None
        c["display_name"] = c.get("name") or c.get("hostname") or "(unnamed)"

    # Always require: active + has an IP. Wired-only unless show_all.
    clients = [c for c in clients if c.get("is_active") and c.get("ip")]
    if not show_all:
        clients = [c for c in clients if c.get("is_wired")]

    clients.sort(key=lambda c: (
        0 if c.get("managed") else 1,
        (c.get("display_name") or "").lower(),
    ))

    return templates.TemplateResponse(request, "index.html", {
        "clients": clients,
        "wan_names": WAN_NAMES,
        "show_all": show_all,
    })


@app.get("/api/clients")
def api_clients(show_all: bool = False):
    u = UniFi()
    clients = u.list_clients()
    pin_by_mac = routes_by_mac(u.list_routes())
    out = []
    for c in clients:
        if not (c.get("is_active") and c.get("ip")):
            continue
        if not show_all and not c.get("is_wired"):
            continue
        friendly, by_wan = pin_by_mac.get(c["mac"], (None, {}))
        out.append({
            **c,
            "friendly": friendly,
            "managed": friendly is not None,
            "pin_active": next((n for n, r in by_wan.items() if r.get("enabled")), None),
        })
    out.sort(key=lambda c: (0 if c["managed"] else 1, (c.get("name") or "").lower()))
    return out


@app.post("/api/switch")
def api_switch(mac: str = Form(...), wan: str = Form(...)):
    mac = mac.lower()
    if wan == "off":
        wan = "default"
    if wan not in WAN_NAMES and wan != "default":
        raise HTTPException(status_code=400, detail=f"invalid wan '{wan}'")
    u = UniFi()
    pin_by_mac = routes_by_mac(u.list_routes())

    if mac not in pin_by_mac:
        if wan == "default":
            return {"mac": mac, "wan": "default", "managed": False, "changes": []}
        clients = u.list_clients()
        client = next((c for c in clients if c["mac"] == mac), None)
        if not client:
            raise HTTPException(status_code=404, detail=f"UniFi has no client with MAC '{mac}'")
        friendly = derive_friendly(client)
        create_routes_for(u, client, friendly)
        pin_by_mac = routes_by_mac(u.list_routes())
        if mac not in pin_by_mac:
            raise HTTPException(status_code=500, detail="route creation failed")

    friendly, by_wan = pin_by_mac[mac]
    changes = []
    for n, r in by_wan.items():
        want = (wan == n)
        if r.get("enabled") != want:
            u._req("PUT", f"/proxy/network/v2/api/site/default/trafficroutes/{r['_id']}", {**r, "enabled": want})
            changes.append({"wan": n, "enabled": want})
    return {"mac": mac, "friendly": friendly, "wan": wan, "managed": True, "changes": changes}


@app.get("/healthz")
def healthz():
    return {"ok": True}
