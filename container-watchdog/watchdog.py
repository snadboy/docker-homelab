"""Container watchdog: poll revp inventory, push aggregate health to Uptime Kuma.

Polls revp's /api/containers and /api/hosts every POLL_INTERVAL seconds.
For each tick, classifies every container as ok / unhealthy / down / missing
and every host as ok / disconnected. Reports a single aggregate heartbeat to
the Uptime Kuma push URL: status=up when everything is healthy, status=down
with msg listing the offenders otherwise.

Per-container/per-host transitions (e.g., sonarr went unhealthy, host arr
disconnected) are logged on stdout for the journal/docker logs.
"""

from __future__ import annotations

import logging
import os
import sys
import time
import urllib.parse
from dataclasses import dataclass

import requests

LOG = logging.getLogger("watchdog")


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        LOG.error("missing required env %s", name)
        sys.exit(1)
    return val or ""


REVP_URL = env("REVP_URL", "https://sb-traefik.isnadboy.com").rstrip("/")
PUSH_URL = env("PUSH_URL", required=True).rstrip("/")
POLL_INTERVAL = int(env("POLL_INTERVAL", "60"))
HTTP_TIMEOUT = int(env("HTTP_TIMEOUT", "10"))
IGNORE_CONTAINERS = {x.strip() for x in env("IGNORE_CONTAINERS", "").split(",") if x.strip()}


@dataclass
class Issue:
    kind: str  # "container" | "host"
    target: str  # "name@host" or hostname
    detail: str

    def __str__(self) -> str:
        return f"{self.target} ({self.detail})"


def classify_container(c: dict) -> Issue | None:
    name = c.get("Name") or "?"
    host = c.get("host") or "?"
    if name in IGNORE_CONTAINERS:
        return None
    state = (c.get("State") or "").lower()
    status = c.get("Status") or ""
    target = f"{name}@{host}"
    if state != "running":
        return Issue("container", target, f"state={state or 'unknown'}")
    if "(unhealthy)" in status.lower():
        return Issue("container", target, "unhealthy")
    return None


def classify_host(h: dict) -> Issue | None:
    name = h.get("hostname") or "?"
    status = (h.get("status") or "").lower()
    if status == "connected":
        return None
    err = (h.get("last_error") or "").splitlines()[0][:120] if h.get("last_error") else "no error detail"
    return Issue("host", name, f"status={status} | {err}")


def fetch(path: str) -> dict | list:
    r = requests.get(f"{REVP_URL}{path}", timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def push(status: str, msg: str) -> None:
    qs = urllib.parse.urlencode({"status": status, "msg": msg, "ping": ""})
    try:
        r = requests.get(f"{PUSH_URL}?{qs}", timeout=HTTP_TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as exc:
        LOG.error("push failed: %s", exc)


def collect() -> list[Issue]:
    """Returns the current set of issues across all containers and hosts.

    Uses revp's /api/containers/all which returns the raw `docker ps -a`
    inventory — every container Docker knows about, running or not. This
    means a stopped container is visible (State="exited") rather than
    vanishing from the response, so the classifier sees the bad state
    directly without needing to track a baseline.
    """
    issues: list[Issue] = []
    try:
        data = fetch("/api/containers/all")
    except Exception as exc:
        return [Issue("revp", "containers", f"fetch failed: {exc}")]
    containers = data.get("containers") if isinstance(data, dict) else data
    for c in containers or []:
        if (i := classify_container(c)):
            issues.append(i)
    try:
        data = fetch("/api/hosts")
    except Exception as exc:
        issues.insert(0, Issue("revp", "hosts", f"fetch failed: {exc}"))
        return issues
    hosts = data.get("hosts") if isinstance(data, dict) and "hosts" in data else data
    for _, h in (hosts or {}).items():
        if (i := classify_host(h)):
            issues.append(i)
    return issues


def diff(prev: set[str], curr: set[str]) -> tuple[list[str], list[str]]:
    return sorted(curr - prev), sorted(prev - curr)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    LOG.info("starting; revp=%s interval=%ss ignore=%s", REVP_URL, POLL_INTERVAL, sorted(IGNORE_CONTAINERS) or "[]")
    prev: dict[str, str] = {}  # key -> detail
    bootstrap = True
    while True:
        issues = collect()
        curr = {f"{i.kind}:{i.target}": str(i) for i in issues}
        added, cleared = diff(set(prev), set(curr))
        if bootstrap:
            if curr:
                LOG.warning("baseline (already-bad): %s", ", ".join(curr.values()))
            else:
                LOG.info("baseline clean")
            bootstrap = False
        else:
            for k in added:
                LOG.warning("DOWN  %s", curr[k])
            for k in cleared:
                LOG.info("UP    %s recovered", k.split(":", 1)[1])
        if curr:
            msg = " | ".join(sorted(curr.values()))[:1000]
            push("down", msg)
        else:
            push("up", "ok")
        prev = curr
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
