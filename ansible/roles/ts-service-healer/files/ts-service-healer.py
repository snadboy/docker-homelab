#!/usr/bin/env python3
"""Detect and heal Tailscale services that are dark despite a healthy backend.

THE FAULT THIS FIXES
--------------------
DockTail advertises a service, tailscaled writes it to AdvertiseServices and the
serve config, the control plane records the service definition -- but the host is
never registered as a host for it. The node believes it succeeded and NOTHING EVER
RETRIES, so the service stays dark silently and indefinitely until the daemon next
re-registers. Observed three times: wizarr on arr (~17 h, ended by an unrelated
reboot), gpu-benchmark on arr (~6.5 h), sabnzbd on fetch (~22 h -- Gotify alerted
and nobody acted). Only a tailscaled restart clears it.

WHAT IT WILL AND WILL NOT DO
----------------------------
Restarting tailscaled briefly drops EVERY service on that host, so acting wrongly
is expensive. The gates, in order:

  1. Service is dark      -- no HTTP response at all from https://<svc>/ .
                             Any status code (even 404/500) counts as serving.
  2. Backend IS healthy   -- checked ON the host against the serve config's own
                             proxy target. A dark service with a dead backend is a
                             REAL OUTAGE, not a desync; restarting would not fix it
                             and would disturb the host's other services. Report only.
  3. Confirmed repeatedly -- FAIL_THRESHOLD consecutive runs, so a transient blip
                             or a container restarting never triggers a daemon restart.
  4. Host off cooldown    -- COOLDOWN_S since that host was last restarted, so a
                             host that stays broken cannot become a restart loop.
  5. One host per run     -- never restart the whole fleet in a single pass.

STATIC (ADVERTISER) SERVICES
----------------------------
Also covered, with one honest limitation. Static services live in
/etc/ts-static-serves.txt (proxies) and /etc/ts-static-serves-hubs.txt (hub pages)
on BOTH advertisers, which serve them as an HA pair.

What is detected: the service is dark, i.e. BOTH advertisers have stopped serving
it. Remediation restarts one advertiser per run; the cooldown means the second is
tried on a later run if the first did not fix it.

What is NOT detected: one advertiser of the pair desyncing while the other still
serves. Tailscale only exposes the PRIMARY route holder for a VIP -- verified from
two separate vantage points, every static service lists only tsvc-baker -- so a
standby is invisible whether it is healthy or broken. There is no API, netmap or
CapMap field that distinguishes the two ("service-host" is a tailnet-wide grant,
not a per-host registration). A half-broken pair therefore looks perfectly healthy
until the primary also fails. Detecting that would need a deliberate failover test,
which is too invasive to run on a timer.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TAILNET = os.environ.get("TAILNET", "swallow-spectrum.ts.net")
HOSTS = [h for h in os.environ.get("DOCKTAIL_HOSTS", "arr,fetch,bedrock,utilities").split(",") if h]
ADVERTISERS = [h for h in os.environ.get("ADVERTISER_HOSTS", "tsvc-able,tsvc-baker").split(",") if h]
SSH_USER = os.environ.get("SSH_USER", "snadboy")
STATE_FILE = os.environ.get("STATE_FILE", "/var/lib/ts-service-healer/state.json")
FAIL_THRESHOLD = int(os.environ.get("FAIL_THRESHOLD", "3"))
COOLDOWN_S = int(os.environ.get("COOLDOWN_S", "5400"))       # 90 min
PROBE_TIMEOUT = float(os.environ.get("PROBE_TIMEOUT", "12"))
PROBE_RETRY_DELAY = float(os.environ.get("PROBE_RETRY_DELAY", "3"))
GOTIFY_URL = os.environ.get("GOTIFY_URL", "")
GOTIFY_TOKEN = os.environ.get("GOTIFY_TOKEN", "")
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1" or "--dry-run" in sys.argv

SSH = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
       "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes"]


def log(msg):
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}", flush=True)


def ssh(host, cmd, timeout=25):
    """Run cmd on host. Returns stdout, or None if the host is unreachable/failed.
    Host keys are not pinned: the transport is the ACL-gated tailnet and homelab
    VMs get rebuilt often enough that strict checking would hard-fail this job."""
    try:
        r = subprocess.run(SSH + [f"{SSH_USER}@{host}", cmd],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def host_services(host):
    """{svc_name: proxy_target} that this host's docktail currently advertises.

    Read from tailscaled itself, not from docker labels: the labels say what SHOULD
    be advertised, and the whole failure mode is a gap between intent and reality.
    AdvertiseServices is what the node actually claims."""
    out = ssh(host, "docker exec docktail tailscale debug prefs 2>/dev/null")
    if not out:
        return None
    try:
        advertised = json.loads(out).get("AdvertiseServices") or []
    except Exception:
        return None

    out = ssh(host, "docker exec docktail tailscale serve status --json 2>/dev/null")
    targets = {}
    if out:
        try:
            for svc, cfg in (json.loads(out).get("Services") or {}).items():
                for _hostport, web in (cfg.get("Web") or {}).items():
                    proxy = ((web.get("Handlers") or {}).get("/") or {}).get("Proxy")
                    if proxy:
                        targets[svc] = proxy
                        break
        except Exception:
            pass
    return {s.removeprefix("svc:"): targets.get(s) for s in advertised}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects — see _OPENER."""
    def redirect_request(self, *args, **kwargs):
        return None


# MUST not follow redirects. The question is only "did the VIP answer", and several
# services 303 to a location that is unreachable from off-host (tautulli redirects
# somewhere that refuses the connection). Following it turned a perfectly healthy
# service into a 12s timeout and a false 'dark' strike — three of those would have
# restarted tailscaled on arr and dropped all 10 of its services for nothing.
_OPENER = urllib.request.build_opener(_NoRedirect)


def _probe_once(url):
    try:
        _OPENER.open(urllib.request.Request(url, method="GET"), timeout=PROBE_TIMEOUT)
        return True
    except urllib.error.HTTPError:
        return True                      # any HTTP status (incl. 3xx) means it is serving
    except Exception:
        return False


def static_services(host):
    """{svc: target} the advertiser is configured to serve.

    Read from the reconciler's own managed lists rather than from tailscaled: these
    files ARE the desired state (the reconcile script clears anything not in them),
    so they say what should be served even when the daemon has lost it.
    Hub entries are local HTML files; their 'target' is the path, marked with a
    file:// scheme so backend_up knows to stat it instead of curling it."""
    out = ssh(host, "cat /etc/ts-static-serves.txt 2>/dev/null")
    hubs = ssh(host, "cat /etc/ts-static-serves-hubs.txt 2>/dev/null")
    if out is None and hubs is None:
        return None
    svcs = {}
    for line in (out or "").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and len(line.split(None, 1)) == 2:
            name, target = line.split(None, 1)
            svcs[name] = target.strip()
    for line in (hubs or "").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and len(line.split(None, 1)) == 2:
            name, path = line.split(None, 1)
            svcs[name] = "file://" + path.strip()
    return svcs


def service_up(svc):
    """True if the VIP answers at all; only a connection failure/timeout is dark.

    Retried once after a short pause: a single slow response is common (observed on
    tautulli during testing) and should not burn a strike. A genuinely desynced
    service fails every probe, forever, so the retry costs nothing there."""
    url = f"https://{svc}.{TAILNET}/"
    if _probe_once(url):
        return True
    time.sleep(PROBE_RETRY_DELAY)
    return _probe_once(url)


def backend_up(host, target):
    """Check the serve config's own proxy target, from the host. This is the gate
    that separates 'tailscaled lost the advertisement' from 'the app is down'.

    Handles the three target shapes in play:
      file://PATH            hub pages — a local HTML file, so stat it
      https+insecure://...   PVE/PBS/UniFi/Synology self-signed — needs curl -k
      http(s)://...          everything else
    """
    if not target:
        return None                      # unknown -> caller treats as inconclusive

    if target.startswith("file://"):
        out = ssh(host, f"test -s '{target[7:]}' && echo yes || echo no")
        return None if out is None else out.strip() == "yes"

    insecure = ""
    url = target
    if target.startswith("https+insecure://"):
        insecure = "-k "
        url = "https://" + target[len("https+insecure://"):]
    out = ssh(host, f"curl -s {insecure}-o /dev/null -m 8 -w '%{{http_code}}' '{url}' 2>/dev/null")
    if out is None:
        return None
    code = out.strip()
    return bool(code) and code != "000"


def notify(title, message, priority=5):
    if not (GOTIFY_URL and GOTIFY_TOKEN):
        return
    try:
        data = urllib.parse.urlencode({"title": title, "message": message,
                                       "priority": priority}).encode()
        urllib.request.urlopen(
            urllib.request.Request(f"{GOTIFY_URL}/message?token={GOTIFY_TOKEN}",
                                   data=data, method="POST"), timeout=10)
    except Exception as e:
        log(f"gotify notify failed: {e}")


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"dark_counts": {}, "last_restart": {}}


def save_state(st):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(st, f, indent=1)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        log(f"could not persist state: {e}")


def main():
    st = load_state()
    dark_counts = st.setdefault("dark_counts", {})
    last_restart = st.setdefault("last_restart", {})
    now = time.time()

    candidates = {}        # host -> [svc,...] dark WITH a healthy backend
    seen = set()

    # A static service is served by BOTH advertisers, so it is checked once and any
    # remediation is attributed to whichever advertiser we pick — never both at once
    # (the cooldown enforces that, since a restart drops all 19 static services).
    # Ordered least-recently-restarted first: static services are attributed to the
    # first advertiser that still has them, so consecutive incidents alternate
    # between the pair instead of always hammering the same one. Which of the two is
    # actually at fault is unknowable (only the primary is visible), so alternating
    # is the fairest available strategy.
    static_seen = {}
    for adv in sorted(ADVERTISERS, key=lambda a: last_restart.get(a, 0)):
        s = static_services(adv)
        if s is None:
            log(f"{adv}: unreachable — cannot read static serve list")
            continue
        static_seen[adv] = s

    work = [(h, host_services(h), "docktail") for h in HOSTS]
    work += [(a, s, "static") for a, s in static_seen.items()]

    checked_static = set()
    for host, svcs, kind in work:
        if svcs is None:
            log(f"{host}: unreachable or no docktail — skipping")
            continue
        log(f"{host}: {kind}, {len(svcs)} service(s)")
        for svc, target in svcs.items():
            if kind == "static":
                if svc in checked_static:
                    continue             # HA pair: probe the VIP once, not per advertiser
                checked_static.add(svc)
            seen.add(svc)
            if service_up(svc):
                if dark_counts.pop(svc, None):
                    log(f"  {svc}: recovered")
                continue

            be = backend_up(host, target)
            if be is False:
                dark_counts.pop(svc, None)
                log(f"  {svc}: DARK but backend {target} is also down — real outage, "
                    f"not a desync; not restarting")
                continue
            if be is None:
                log(f"  {svc}: DARK, backend state unknown ({target}) — not acting")
                continue

            n = dark_counts.get(svc, 0) + 1
            dark_counts[svc] = n
            log(f"  {svc}: DARK with healthy backend ({target}) — strike {n}/{FAIL_THRESHOLD}")
            if n >= FAIL_THRESHOLD:
                candidates.setdefault(host, []).append(svc)

    # forget services that no longer exist anywhere
    for svc in list(dark_counts):
        if svc not in seen:
            dark_counts.pop(svc, None)

    acted = False
    for host, svcs in sorted(candidates.items(), key=lambda kv: -len(kv[1])):
        since = now - last_restart.get(host, 0)
        if since < COOLDOWN_S:
            log(f"{host}: {len(svcs)} dark service(s) but restarted "
                f"{int(since / 60)}m ago (cooldown {COOLDOWN_S // 60}m) — holding off")
            notify("TS healer: still dark, in cooldown",
                   f"{host}: {', '.join(svcs)} dark; last restart {int(since/60)}m ago. "
                   f"Manual look needed if this persists.", priority=7)
            continue

        msg = (f"{host}: {', '.join(svcs)} advertised + backend healthy but dark for "
               f"{FAIL_THRESHOLD} consecutive checks. Restarting tailscaled "
               f"(briefly drops all services on {host}).")
        log(msg)
        if DRY_RUN:
            log(f"[DRY RUN] would restart tailscaled on {host}")
        else:
            # detached: restarting the daemon kills this very SSH session
            out = ssh(host, "sudo systemd-run --on-active=3 --unit=ts-heal-restart "
                            "--collect systemctl restart tailscaled")
            if out is None:
                log(f"{host}: restart command FAILED")
                notify("TS healer: restart failed", msg, priority=8)
                continue
            last_restart[host] = now
            for svc in svcs:
                dark_counts.pop(svc, None)
            notify("TS healer: restarted tailscaled", msg, priority=6)
        acted = True
        break                                  # at most one host per run

    if not candidates and not acted:
        log("all advertised services reachable (or already excluded)")
    save_state(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
