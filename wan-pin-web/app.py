"""
wan-pin-web: tiny FastAPI app for selecting which WAN a UniFi-managed
client egresses through. Wraps the UniFi controller's Traffic Routes API.

Routes follow naming convention 'wan-pin:<device>:wan<n>' (matches the
CLI tool at docker-homelab/tools/wan-pin). Exactly one is enabled at a
time per device; kill_switch=true on all of them.
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
from fastapi.responses import HTMLResponse, JSONResponse
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

    def list_routes(self):
        return self._req("GET", "/proxy/network/v2/api/site/default/trafficroutes") or []

    def update_route(self, route_id: str, body: dict):
        return self._req("PUT", f"/proxy/network/v2/api/site/default/trafficroutes/{route_id}", body)


def get_unifi() -> UniFi:
    return UniFi()


def parse_managed_routes(routes):
    """Group routes by device, returning {friendly: {wan_n: route}}."""
    by_device: dict[str, dict[str, dict]] = {}
    for r in routes:
        desc = r.get("description") or ""
        if not desc.startswith(ROUTE_PREFIX):
            continue
        # wan-pin:<device>:wan<n>
        m = re.fullmatch(rf"{re.escape(ROUTE_PREFIX)}(.+):wan([0-9]+)", desc)
        if not m:
            continue
        device, n = m.group(1), m.group(2)
        by_device.setdefault(device, {})[n] = r
    return by_device


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    u = get_unifi()
    by_device = parse_managed_routes(u.list_routes())
    devices = []
    for name in sorted(by_device):
        routes = by_device[name]
        # Identify the active WAN (if any)
        active = next((n for n, r in routes.items() if r.get("enabled")), None)
        # Pull one MAC from any route for display
        mac = ""
        for r in routes.values():
            td = (r.get("target_devices") or [])
            if td and td[0].get("client_mac"):
                mac = td[0]["client_mac"]
                break
        devices.append({
            "name": name,
            "mac": mac,
            "active": active,
            "wans": [{"n": n, "label": WAN_NAMES.get(n, f"WAN{n}"), "id": routes[n]["_id"]} for n in sorted(routes)],
        })
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "devices": devices, "wan_names": WAN_NAMES},
    )


@app.post("/api/switch")
def api_switch(device: str = Form(...), wan: str = Form(...)):
    if wan not in WAN_NAMES and wan != "off":
        raise HTTPException(status_code=400, detail=f"invalid wan '{wan}'")
    u = get_unifi()
    by_device = parse_managed_routes(u.list_routes())
    if device not in by_device:
        raise HTTPException(status_code=404, detail=f"no wan-pin routes for '{device}'")
    routes = by_device[device]
    changes = []
    for n, r in routes.items():
        want = (wan == n)
        if r.get("enabled") != want:
            u.update_route(r["_id"], {**r, "enabled": want})
            changes.append({"wan": n, "enabled": want})
    return {"device": device, "wan": wan, "changes": changes, "active": wan}


@app.get("/api/devices")
def api_devices():
    u = get_unifi()
    by_device = parse_managed_routes(u.list_routes())
    return [
        {
            "name": name,
            "active": next((n for n, r in routes.items() if r.get("enabled")), None),
            "wans": {n: {"label": WAN_NAMES.get(n, f"WAN{n}"), "enabled": r.get("enabled", False)} for n, r in routes.items()},
        }
        for name, routes in by_device.items()
    ]


@app.get("/healthz")
def healthz():
    return {"ok": True}