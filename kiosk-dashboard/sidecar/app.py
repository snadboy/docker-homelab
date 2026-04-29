"""Kiosk-dashboard sidecar — exposes /api/extras/* aggregated from UniFi, Proxmox, HA.

Reads secrets from env at boot, fails fast if missing. Uses 5-second TTL caches
so the dashboard frontend can poll cheaply without hammering upstreams.
"""
from __future__ import annotations

import logging
import os
import time
from threading import Lock

import requests
import urllib3
from cachetools import TTLCache
from flask import Flask, jsonify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
app.logger.setLevel(logging.WARNING)

UNIFI_HOST = os.environ.get("UNIFI_HOST", "https://192.168.86.1")
UNIFI_USERNAME = os.environ["UNIFI_USERNAME"]
UNIFI_PASSWORD = os.environ["UNIFI_PASSWORD"]
UNIFI_SITE = os.environ.get("UNIFI_SITE", "default")

PVE_HOST = os.environ.get("PVE_HOST", "https://colossus.isnadboy.com")
PVE_TOKEN_ID = os.environ["PVE_TOKEN_ID"]
PVE_TOKEN_SECRET = os.environ["PVE_TOKEN_SECRET"]

HASS_SERVER = os.environ.get("HASS_SERVER", "http://192.168.86.224:8123")
HASS_TOKEN = os.environ["HASS_TOKEN"]
HASS_WEATHER_ENTITY = os.environ.get("HASS_WEATHER_ENTITY", "")  # optional override

CACHE_TTL = 5
wifi_cache = TTLCache(maxsize=1, ttl=CACHE_TTL)
pve_cache = TTLCache(maxsize=1, ttl=CACHE_TTL)
weather_cache = TTLCache(maxsize=1, ttl=60)

unifi_session_lock = Lock()
unifi_session: requests.Session | None = None
unifi_csrf: str | None = None
unifi_last_login_failure = 0.0
unifi_backoff_seconds = 60.0  # grows exponentially on repeat failures
UNIFI_BACKOFF_MAX = 600.0


def _unifi_login() -> tuple[requests.Session, str]:
    global unifi_session, unifi_csrf, unifi_last_login_failure, unifi_backoff_seconds
    elapsed = time.time() - unifi_last_login_failure
    if elapsed < unifi_backoff_seconds:
        wait = int(unifi_backoff_seconds - elapsed)
        raise RuntimeError(f"unifi: in login backoff ({wait}s left)")
    s = requests.Session()
    s.verify = False
    r = s.post(
        f"{UNIFI_HOST}/api/auth/login",
        json={"username": UNIFI_USERNAME, "password": UNIFI_PASSWORD},
        timeout=8,
    )
    if r.status_code != 200:
        unifi_last_login_failure = time.time()
        unifi_backoff_seconds = min(unifi_backoff_seconds * 2, UNIFI_BACKOFF_MAX)
        raise RuntimeError(f"unifi login HTTP {r.status_code} (next retry in ~{int(unifi_backoff_seconds)}s)")
    csrf = r.headers.get("X-Csrf-Token") or r.headers.get("X-CSRF-Token") or ""
    unifi_session = s
    unifi_csrf = csrf
    unifi_backoff_seconds = 60.0  # reset on success
    return s, csrf


def _unifi_get(path: str):
    global unifi_session, unifi_csrf
    with unifi_session_lock:
        if unifi_session is None:
            _unifi_login()
        s, csrf = unifi_session, unifi_csrf
        for attempt in range(2):
            try:
                r = s.get(
                    f"{UNIFI_HOST}{path}",
                    headers={"X-Csrf-Token": csrf} if csrf else {},
                    timeout=8,
                )
                if r.status_code == 401 and attempt == 0:
                    s, csrf = _unifi_login()
                    continue
                r.raise_for_status()
                return r.json()
            except (requests.RequestException, ValueError) as e:
                if attempt == 0:
                    s, csrf = _unifi_login()
                    continue
                raise


def _build_wifi_payload():
    devices = _unifi_get(f"/proxy/network/api/s/{UNIFI_SITE}/stat/device").get("data", [])
    wlans_cfg = _unifi_get(f"/proxy/network/api/s/{UNIFI_SITE}/rest/wlanconf").get("data", [])
    cfg_by_essid = {w["name"]: w for w in wlans_cfg}

    agg: dict[str, dict] = {}
    for dev in devices:
        if dev.get("type") != "uap":
            continue
        ap_name = dev.get("name") or dev.get("hostname") or dev.get("mac")
        radios = {r["name"]: r for r in dev.get("radio_table_stats", [])}
        for vap in dev.get("vap_table", []) or []:
            ssid = vap.get("essid")
            if not ssid:
                continue
            entry = agg.setdefault(ssid, {
                "ssid": ssid,
                "num_clients": 0,
                "tx_bytes_per_sec": 0,
                "rx_bytes_per_sec": 0,
                "aps": [],
                "satisfaction": [],
                "channel_utilization": [],
            })
            entry["num_clients"] += int(vap.get("num_sta") or 0)
            # tx/rx_bytes-r are bytes/sec (recent), per UniFi schema; fall back to *_packets if missing
            tx_bps = vap.get("tx_bytes-r") or 0
            rx_bps = vap.get("rx_bytes-r") or 0
            entry["tx_bytes_per_sec"] += tx_bps
            entry["rx_bytes_per_sec"] += rx_bps
            sat = vap.get("satisfaction")
            if sat is not None and sat >= 0:
                entry["satisfaction"].append(sat)
            radio = radios.get(vap.get("radio_name") or "")
            cu = (radio or {}).get("cu_total")
            if cu is not None:
                entry["channel_utilization"].append(cu)
            entry["aps"].append({
                "name": ap_name,
                "radio": vap.get("radio"),
                "channel": vap.get("channel"),
                "num_sta": vap.get("num_sta") or 0,
            })
    wlans = []
    for ssid, e in agg.items():
        cfg = cfg_by_essid.get(ssid, {})
        e["enabled"] = bool(cfg.get("enabled", True))
        e["band"] = cfg.get("wlan_band", "both")
        e["security"] = cfg.get("security", "")
        if e["satisfaction"]:
            e["satisfaction_pct"] = round(sum(e["satisfaction"]) / len(e["satisfaction"]))
        else:
            e["satisfaction_pct"] = None
        e.pop("satisfaction", None)
        if e["channel_utilization"]:
            e["channel_utilization_pct"] = round(sum(e["channel_utilization"]) / len(e["channel_utilization"]))
        else:
            e["channel_utilization_pct"] = None
        e.pop("channel_utilization", None)
        wlans.append(e)
    wlans.sort(key=lambda w: -w["num_clients"])
    return {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "wlans": wlans,
    }


@app.route("/api/extras/wifi")
def wifi():
    if "v" in wifi_cache:
        return jsonify(wifi_cache["v"])
    try:
        payload = _build_wifi_payload()
        wifi_cache["v"] = payload
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e), "wlans": []}), 502


def _pve_headers():
    return {"Authorization": f"PVEAPIToken={PVE_TOKEN_ID}={PVE_TOKEN_SECRET}"}


def _build_proxmox_payload():
    r = requests.get(
        f"{PVE_HOST}/api2/json/cluster/resources",
        params={"type": "node"},
        headers=_pve_headers(),
        verify=False,
        timeout=8,
    )
    r.raise_for_status()
    cluster_status = requests.get(
        f"{PVE_HOST}/api2/json/cluster/status",
        headers=_pve_headers(),
        verify=False,
        timeout=8,
    ).json().get("data", [])
    cluster_name = next((c["name"] for c in cluster_status if c.get("type") == "cluster"), "")
    nodes = []
    for n in r.json().get("data", []):
        nodes.append({
            "name": n.get("node"),
            "status": n.get("status"),
            "cpu_pct": round((n.get("cpu") or 0) * 100, 1),
            "mem_pct": round((n.get("mem") or 0) / (n.get("maxmem") or 1) * 100, 1) if n.get("maxmem") else None,
            "mem_used_bytes": n.get("mem"),
            "mem_total_bytes": n.get("maxmem"),
            "uptime_seconds": n.get("uptime", 0),
        })
    nodes.sort(key=lambda x: x["name"] or "")
    return {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cluster": cluster_name,
        "nodes": nodes,
    }


@app.route("/api/extras/proxmox")
def proxmox():
    if "v" in pve_cache:
        return jsonify(pve_cache["v"])
    try:
        payload = _build_proxmox_payload()
        pve_cache["v"] = payload
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e), "nodes": []}), 502


def _find_outside_temp():
    if HASS_WEATHER_ENTITY:
        r = requests.get(
            f"{HASS_SERVER}/api/states/{HASS_WEATHER_ENTITY}",
            headers={"Authorization": f"Bearer {HASS_TOKEN}"},
            timeout=6,
        )
        r.raise_for_status()
        st = r.json()
        if st.get("attributes", {}).get("unit_of_measurement", "").lower() in ("°f", "f", "fahrenheit"):
            return float(st["state"])
        if st.get("attributes", {}).get("temperature") is not None:
            return float(st["attributes"]["temperature"])
        return float(st["state"])
    # Fallback: scan for an outdoor weather entity
    r = requests.get(
        f"{HASS_SERVER}/api/states",
        headers={"Authorization": f"Bearer {HASS_TOKEN}"},
        timeout=8,
    )
    r.raise_for_status()
    states = r.json()
    candidates = [s for s in states if s["entity_id"].startswith("weather.")]
    if not candidates:
        return None
    primary = next((s for s in candidates if "home" in s["entity_id"] or "outside" in s["entity_id"]), candidates[0])
    temp = primary.get("attributes", {}).get("temperature")
    unit = primary.get("attributes", {}).get("temperature_unit") or "°F"
    if temp is None:
        return None
    if "C" in unit.upper():
        temp = temp * 9 / 5 + 32
    return float(temp)


@app.route("/api/extras/weather")
def weather():
    if "v" in weather_cache:
        return jsonify(weather_cache["v"])
    try:
        temp_f = _find_outside_temp()
        payload = {"updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "temp_f": temp_f}
        weather_cache["v"] = payload
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e), "temp_f": None}), 502


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True})
