#!/usr/bin/env python3
"""
ARR Services Health Monitor

Monitors SABnzbd, Sonarr, Radarr, Prowlarr, Overseerr, and Agregarr for health issues.
Auto-remediates SABnzbd pause states when safe (disk space adequate).
Sends notifications via Gotify.

Environment variables (from /mnt/shareables/.claude/.env):
- SABNZBD_URL, SABNZBD_API_KEY
- SONARR_URL, SONARR_API_KEY
- RADARR_URL, RADARR_API_KEY
- PROWLARR_URL, PROWLARR_API_KEY
- OVERSEERR_URL, OVERSEERR_API_KEY
- AGREGARR_URL
- GOTIFY_URL, GOTIFY_TOKEN

Schedule: Every 5 minutes via Script Server
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# Suppress SSL warnings for self-signed certs
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
SCRIPTS_DIR = Path("/app/scripts")
STATE_FILE = SCRIPTS_DIR / ".arr_monitor_state.json"
MIN_DISK_SPACE_GB = 10  # Minimum disk space to allow SABnzbd resume
NOTIFY_COOLDOWN_HOURS = 1  # Re-notify after this many hours if issue persists
REQUEST_TIMEOUT = 10  # Seconds


def load_env():
    """Load environment variables from config file"""
    env_files = [
        SCRIPTS_DIR / ".claude" / ".env",
        Path("/mnt/shareables/.claude/.env")
    ]

    for env_file in env_files:
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key] = value.strip('"').strip("'")
            print(f"Loaded config from {env_file}")
            return

    print("WARNING: No config file found")


class GotifyNotifier:
    """Send notifications via Gotify"""

    def __init__(self, url: str, token: str):
        self.url = url.rstrip('/')
        self.token = token

    def send(self, title: str, message: str, priority: int = 5) -> bool:
        """Send a notification. Returns True on success."""
        if not self.url or not self.token:
            print("WARNING: Gotify not configured, skipping notification")
            return False

        try:
            response = requests.post(
                f"{self.url}/message",
                headers={"X-Gotify-Key": self.token},
                json={"title": title, "message": message, "priority": priority},
                timeout=REQUEST_TIMEOUT,
                verify=False
            )
            response.raise_for_status()
            print(f"  Notification sent: {title}")
            return True
        except Exception as e:
            print(f"  ERROR sending notification: {e}")
            return False


class StateManager:
    """Track service states to prevent notification spam"""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state = self._load()

    def _load(self) -> dict:
        """Load or initialize state"""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except Exception as e:
                print(f"WARNING: Could not load state file: {e}")
        return {
            "services": {},
            "last_daily_summary": None
        }

    def save(self):
        """Persist state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2, default=str)
        except Exception as e:
            print(f"WARNING: Could not save state file: {e}")

    def should_notify(self, service: str, issue_key: str, has_issue: bool) -> bool:
        """
        Return True if notification should be sent.
        Based on state change or cooldown expiry.
        """
        now = datetime.now()
        service_state = self.state.get("services", {}).get(service, {})
        prev_issue = service_state.get(issue_key, {})

        was_issue = prev_issue.get("active", False)
        last_notified = prev_issue.get("last_notified")

        # State change: notify
        if has_issue != was_issue:
            return True

        # Issue persists: check cooldown
        if has_issue and last_notified:
            try:
                last_time = datetime.fromisoformat(last_notified)
                if now - last_time > timedelta(hours=NOTIFY_COOLDOWN_HOURS):
                    return True
            except:
                pass

        return False

    def update_issue(self, service: str, issue_key: str, has_issue: bool, notified: bool = False):
        """Update issue state"""
        if "services" not in self.state:
            self.state["services"] = {}
        if service not in self.state["services"]:
            self.state["services"][service] = {}

        now = datetime.now().isoformat()

        if has_issue:
            self.state["services"][service][issue_key] = {
                "active": True,
                "since": self.state["services"][service].get(issue_key, {}).get("since", now),
                "last_notified": now if notified else self.state["services"][service].get(issue_key, {}).get("last_notified")
            }
        else:
            # Clear the issue
            if issue_key in self.state["services"][service]:
                del self.state["services"][service][issue_key]

    def should_send_daily_summary(self) -> bool:
        """Check if we should send a daily summary"""
        now = datetime.now()
        last_summary = self.state.get("last_daily_summary")

        if not last_summary:
            return True

        try:
            last_time = datetime.fromisoformat(last_summary)
            # Send if last summary was on a different day
            return last_time.date() < now.date()
        except:
            return True

    def mark_daily_summary_sent(self):
        """Mark that daily summary was sent"""
        self.state["last_daily_summary"] = datetime.now().isoformat()


class SABnzbdMonitor:
    """Monitor and remediate SABnzbd"""

    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip('/')
        self.api_key = api_key
        self.name = "SABnzbd"

    def check_health(self) -> Dict[str, Any]:
        """Returns health status dict"""
        result = {
            "reachable": False,
            "paused": False,
            "status": "unknown",
            "disk_space_gb": 0,
            "disk_space_ok": False,
            "queue_count": 0,
            "warnings": []
        }

        if not self.url or not self.api_key:
            result["warnings"].append("Not configured")
            return result

        try:
            # Get queue status
            response = requests.get(
                f"{self.url}/api",
                params={"mode": "queue", "apikey": self.api_key, "output": "json"},
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            queue = data.get("queue", {})
            result["reachable"] = True
            result["paused"] = queue.get("paused", False)
            result["status"] = queue.get("status", "unknown")
            result["queue_count"] = int(queue.get("noofslots", 0))

            # Disk space (reported in GB as string)
            try:
                disk_gb = float(queue.get("diskspace1", 0))
                result["disk_space_gb"] = disk_gb
                result["disk_space_ok"] = disk_gb >= MIN_DISK_SPACE_GB
            except:
                pass

        except requests.exceptions.RequestException as e:
            result["warnings"].append(f"Connection error: {e}")
        except Exception as e:
            result["warnings"].append(f"Error: {e}")

        return result

    def resume_queue(self) -> bool:
        """Resume queue if paused. Returns success."""
        try:
            response = requests.get(
                f"{self.url}/api",
                params={"mode": "resume", "apikey": self.api_key},
                timeout=REQUEST_TIMEOUT
            )
            return response.ok
        except Exception as e:
            print(f"  ERROR resuming SABnzbd: {e}")
            return False


class ArrServiceMonitor:
    """Monitor *arr services (Sonarr, Radarr, Prowlarr)"""

    def __init__(self, name: str, url: str, api_key: str, api_version: str = "v3"):
        self.name = name
        self.url = url.rstrip('/')
        self.api_key = api_key
        self.api_version = api_version

    def check_health(self) -> Dict[str, Any]:
        """Returns health status dict"""
        result = {
            "reachable": False,
            "health_issues": [],
            "version": None
        }

        if not self.url or not self.api_key:
            result["health_issues"].append("Not configured")
            return result

        headers = {"X-Api-Key": self.api_key}

        try:
            # Check system status (reachability)
            status_response = requests.get(
                f"{self.url}/api/{self.api_version}/system/status",
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )
            status_response.raise_for_status()
            status_data = status_response.json()
            result["reachable"] = True
            result["version"] = status_data.get("version")

            # Check health endpoint
            health_response = requests.get(
                f"{self.url}/api/{self.api_version}/health",
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )
            health_response.raise_for_status()
            health_data = health_response.json()

            # Health returns empty list when healthy
            if health_data:
                for issue in health_data:
                    msg = f"[{issue.get('type', 'unknown')}] {issue.get('message', 'Unknown issue')}"
                    result["health_issues"].append(msg)

        except requests.exceptions.RequestException as e:
            result["health_issues"].append(f"Connection error: {e}")
        except Exception as e:
            result["health_issues"].append(f"Error: {e}")

        return result


class OverseerrMonitor:
    """Monitor Overseerr"""

    def __init__(self, url: str, api_key: str):
        self.name = "Overseerr"
        self.url = url.rstrip('/')
        self.api_key = api_key

    def check_health(self) -> Dict[str, Any]:
        """Returns health status dict"""
        result = {
            "reachable": False,
            "health_issues": [],
            "version": None
        }

        if not self.url or not self.api_key:
            result["health_issues"].append("Not configured")
            return result

        headers = {"X-Api-Key": self.api_key}

        try:
            response = requests.get(
                f"{self.url}/api/v1/status",
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
            result["reachable"] = True
            result["version"] = data.get("version")

        except requests.exceptions.RequestException as e:
            result["health_issues"].append(f"Connection error: {e}")
        except Exception as e:
            result["health_issues"].append(f"Error: {e}")

        return result


class AgregarrMonitor:
    """Monitor Agregarr (basic connectivity only)"""

    def __init__(self, url: str):
        self.name = "Agregarr"
        self.url = url.rstrip('/')

    def check_health(self) -> Dict[str, Any]:
        """Returns health status dict"""
        result = {
            "reachable": False,
            "health_issues": []
        }

        if not self.url:
            result["health_issues"].append("Not configured")
            return result

        try:
            response = requests.get(
                self.url,
                timeout=REQUEST_TIMEOUT
            )
            # Just check if we get any response
            result["reachable"] = response.status_code < 500

        except requests.exceptions.RequestException as e:
            result["health_issues"].append(f"Connection error: {e}")
        except Exception as e:
            result["health_issues"].append(f"Error: {e}")

        return result


def main():
    print("=" * 60)
    print("ARR Services Health Monitor")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()

    # Load environment
    load_env()

    # Initialize components
    notifier = GotifyNotifier(
        os.environ.get("GOTIFY_URL", ""),
        os.environ.get("GOTIFY_TOKEN", "")
    )
    state = StateManager(STATE_FILE)

    # Initialize service monitors
    monitors = {
        "sabnzbd": SABnzbdMonitor(
            os.environ.get("SABNZBD_URL", ""),
            os.environ.get("SABNZBD_API_KEY", "")
        ),
        "sonarr": ArrServiceMonitor(
            "Sonarr",
            os.environ.get("SONARR_URL", ""),
            os.environ.get("SONARR_API_KEY", ""),
            api_version="v3"
        ),
        "radarr": ArrServiceMonitor(
            "Radarr",
            os.environ.get("RADARR_URL", ""),
            os.environ.get("RADARR_API_KEY", ""),
            api_version="v3"
        ),
        "prowlarr": ArrServiceMonitor(
            "Prowlarr",
            os.environ.get("PROWLARR_URL", ""),
            os.environ.get("PROWLARR_API_KEY", ""),
            api_version="v1"
        ),
        "overseerr": OverseerrMonitor(
            os.environ.get("OVERSEERR_URL", ""),
            os.environ.get("OVERSEERR_API_KEY", "")
        ),
        "agregarr": AgregarrMonitor(
            os.environ.get("AGREGARR_URL", "")
        )
    }

    # Track overall status for summary
    all_healthy = True
    issues_found = []
    actions_taken = []

    # Check SABnzbd with auto-remediation
    print("Checking SABnzbd...")
    sab = monitors["sabnzbd"]
    sab_health = sab.check_health()

    if not sab_health["reachable"]:
        all_healthy = False
        issues_found.append("SABnzbd: Unreachable")
        if state.should_notify("sabnzbd", "unreachable", True):
            notifier.send(
                "SABnzbd Unreachable",
                "SABnzbd is not responding. Container may need restart.",
                priority=8
            )
            state.update_issue("sabnzbd", "unreachable", True, notified=True)
        else:
            state.update_issue("sabnzbd", "unreachable", True)
        print(f"  UNREACHABLE")
    else:
        state.update_issue("sabnzbd", "unreachable", False)
        print(f"  Status: {sab_health['status']}, Queue: {sab_health['queue_count']} items")
        print(f"  Disk Space: {sab_health['disk_space_gb']:.1f} GB")

        if sab_health["paused"]:
            if sab_health["disk_space_ok"]:
                # Auto-resume
                print(f"  PAUSED - Attempting auto-resume (disk space OK)...")
                if sab.resume_queue():
                    actions_taken.append("SABnzbd: Auto-resumed")
                    if state.should_notify("sabnzbd", "paused", True):
                        notifier.send(
                            "SABnzbd Auto-Resumed",
                            f"SABnzbd was paused and has been automatically resumed. "
                            f"Disk space: {sab_health['disk_space_gb']:.1f} GB",
                            priority=5
                        )
                        state.update_issue("sabnzbd", "paused", False, notified=True)
                    else:
                        state.update_issue("sabnzbd", "paused", False)
                    print(f"  Successfully resumed!")
                else:
                    all_healthy = False
                    issues_found.append("SABnzbd: Paused (resume failed)")
                    print(f"  Resume FAILED")
            else:
                # Low disk space - notify but don't resume
                all_healthy = False
                issues_found.append(f"SABnzbd: Paused (low disk: {sab_health['disk_space_gb']:.1f} GB)")
                if state.should_notify("sabnzbd", "paused_low_disk", True):
                    notifier.send(
                        "SABnzbd Paused - Low Disk Space",
                        f"SABnzbd is paused due to low disk space ({sab_health['disk_space_gb']:.1f} GB). "
                        f"Manual intervention required.",
                        priority=7
                    )
                    state.update_issue("sabnzbd", "paused_low_disk", True, notified=True)
                else:
                    state.update_issue("sabnzbd", "paused_low_disk", True)
                print(f"  PAUSED - Low disk space, NOT resuming")
        else:
            state.update_issue("sabnzbd", "paused", False)
            state.update_issue("sabnzbd", "paused_low_disk", False)

    # Check *arr services
    for key in ["sonarr", "radarr", "prowlarr", "overseerr", "agregarr"]:
        monitor = monitors[key]
        print(f"\nChecking {monitor.name}...")
        health = monitor.check_health()

        if not health["reachable"]:
            all_healthy = False
            issues_found.append(f"{monitor.name}: Unreachable")
            if state.should_notify(key, "unreachable", True):
                notifier.send(
                    f"{monitor.name} Unreachable",
                    f"{monitor.name} is not responding. Container may need restart.",
                    priority=8
                )
                state.update_issue(key, "unreachable", True, notified=True)
            else:
                state.update_issue(key, "unreachable", True)
            print(f"  UNREACHABLE")
        else:
            state.update_issue(key, "unreachable", False)
            version = health.get("version", "unknown")
            print(f"  OK (version: {version})")

            # Check for health issues (only for services that have health endpoint)
            if health.get("health_issues"):
                all_healthy = False
                for issue in health["health_issues"]:
                    issues_found.append(f"{monitor.name}: {issue}")
                    print(f"  Issue: {issue}")

                if state.should_notify(key, "health_issues", True):
                    notifier.send(
                        f"{monitor.name} Health Issues",
                        "\n".join(health["health_issues"]),
                        priority=6
                    )
                    state.update_issue(key, "health_issues", True, notified=True)
                else:
                    state.update_issue(key, "health_issues", True)
            else:
                state.update_issue(key, "health_issues", False)

    # Daily summary
    print("\n" + "-" * 60)
    if state.should_send_daily_summary():
        if all_healthy:
            notifier.send(
                "ARR Services Daily Summary",
                "All services are healthy:\n"
                "- SABnzbd: OK\n"
                "- Sonarr: OK\n"
                "- Radarr: OK\n"
                "- Prowlarr: OK\n"
                "- Overseerr: OK\n"
                "- Agregarr: OK",
                priority=3
            )
        else:
            summary_msg = "Issues detected:\n" + "\n".join(f"- {i}" for i in issues_found)
            if actions_taken:
                summary_msg += "\n\nActions taken:\n" + "\n".join(f"- {a}" for a in actions_taken)
            notifier.send(
                "ARR Services Daily Summary",
                summary_msg,
                priority=5
            )
        state.mark_daily_summary_sent()
        print("Daily summary sent")

    # Save state
    state.save()

    # Print summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    if all_healthy:
        print("All services healthy!")
    else:
        print("Issues found:")
        for issue in issues_found:
            print(f"  - {issue}")
    if actions_taken:
        print("Actions taken:")
        for action in actions_taken:
            print(f"  - {action}")
    print("=" * 60)

    return 0 if all_healthy else 1


if __name__ == "__main__":
    sys.exit(main())
