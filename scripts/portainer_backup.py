#!/usr/bin/env python3
"""
Portainer Stack Backup

Exports all Portainer stacks (docker-compose files) to a local backup directory.
Includes automatic backup retention to manage disk space.

Environment variables (from /mnt/shareables/.claude/.env):
- PORTAINER_URL
- PORTAINER_API_KEY
"""

import os
import sys
import json
import shutil
import requests
from datetime import datetime
from pathlib import Path

# Suppress SSL warnings for self-signed certs
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
SCRIPTS_DIR = Path("/app/scripts")
BACKUP_DIR = Path("/mnt/shareables/backups/portainer")
RETENTION_DAYS = 30  # Keep backups for this many days
MAX_BACKUPS = 10     # Maximum number of backups to keep (regardless of age)

def load_env():
    """Load environment variables from config file"""
    # Try local config first, then shared mount
    env_files = [
        SCRIPTS_DIR / "portainer_config.env",
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

def get_portainer_stacks():
    """Fetch all stacks from Portainer API"""
    url = os.environ.get("PORTAINER_URL")
    api_key = os.environ.get("PORTAINER_API_KEY")

    if not url or not api_key:
        print("ERROR: PORTAINER_URL or PORTAINER_API_KEY not set")
        sys.exit(1)

    headers = {"X-API-Key": api_key}

    # Get all stacks
    response = requests.get(f"{url}/api/stacks", headers=headers, verify=False)
    response.raise_for_status()
    stacks = response.json()

    print(f"Found {len(stacks)} stacks")

    # Get stack file content for each stack
    stack_data = []
    for stack in stacks:
        stack_id = stack["Id"]
        stack_name = stack["Name"]
        endpoint_id = stack["EndpointId"]

        # Get the compose file content
        file_response = requests.get(
            f"{url}/api/stacks/{stack_id}/file",
            headers=headers,
            verify=False
        )

        if file_response.ok:
            file_content = file_response.json().get("StackFileContent", "")
        else:
            file_content = ""
            print(f"  WARNING: Could not get file content for {stack_name}")

        stack_data.append({
            "id": stack_id,
            "name": stack_name,
            "endpoint_id": endpoint_id,
            "status": stack.get("Status"),
            "type": stack.get("Type"),
            "git_config": stack.get("GitConfig"),
            "compose_content": file_content
        })
        print(f"  - {stack_name} (endpoint {endpoint_id})")

    return stack_data

def create_backup(stacks):
    """Create backup files"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"portainer_backup_{timestamp}"
    backup_path = BACKUP_DIR / backup_name
    backup_path.mkdir(exist_ok=True)

    # Save full JSON backup
    json_file = backup_path / "stacks_full.json"
    with open(json_file, "w") as f:
        json.dump(stacks, f, indent=2, default=str)
    print(f"\nSaved full backup to {json_file}")

    # Save individual compose files
    compose_dir = backup_path / "compose_files"
    compose_dir.mkdir(exist_ok=True)

    for stack in stacks:
        if stack["compose_content"]:
            filename = f"{stack['name']}.yml"
            filepath = compose_dir / filename
            with open(filepath, "w") as f:
                f.write(stack["compose_content"])

    print(f"Saved {len(stacks)} compose files to {compose_dir}")

    # Create summary
    summary_file = backup_path / "summary.txt"
    with open(summary_file, "w") as f:
        f.write(f"Portainer Backup - {datetime.now().isoformat()}\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Total stacks: {len(stacks)}\n\n")
        f.write("Stacks by endpoint:\n")

        by_endpoint = {}
        for stack in stacks:
            eid = stack["endpoint_id"]
            if eid not in by_endpoint:
                by_endpoint[eid] = []
            by_endpoint[eid].append(stack["name"])

        for eid, names in sorted(by_endpoint.items()):
            f.write(f"\n  Endpoint {eid}:\n")
            for name in sorted(names):
                f.write(f"    - {name}\n")

    return backup_path

def cleanup_old_backups():
    """Remove old backups based on retention policy"""
    if not BACKUP_DIR.exists():
        return

    # Get all backup directories (they start with 'portainer_backup_')
    backups = sorted(
        [d for d in BACKUP_DIR.iterdir() if d.is_dir() and d.name.startswith("portainer_backup_")],
        key=lambda x: x.stat().st_mtime,
        reverse=True  # Newest first
    )

    if not backups:
        return

    now = datetime.now()
    removed_count = 0

    for i, backup in enumerate(backups):
        # Always keep at least the newest backup
        if i == 0:
            continue

        # Check if we've exceeded max backups
        if i >= MAX_BACKUPS:
            print(f"  Removing (max backups exceeded): {backup.name}")
            shutil.rmtree(backup)
            removed_count += 1
            continue

        # Check age
        backup_time = datetime.fromtimestamp(backup.stat().st_mtime)
        age_days = (now - backup_time).days

        if age_days > RETENTION_DAYS:
            print(f"  Removing (older than {RETENTION_DAYS} days): {backup.name}")
            shutil.rmtree(backup)
            removed_count += 1

    if removed_count > 0:
        print(f"Cleaned up {removed_count} old backup(s)")
    else:
        print("No old backups to clean up")

def main():
    print("=" * 50)
    print("Portainer Stack Backup")
    print("=" * 50)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Backup location: {BACKUP_DIR}\n")

    # Load environment
    load_env()

    # Get stacks from Portainer
    print("Fetching stacks from Portainer...")
    stacks = get_portainer_stacks()

    if not stacks:
        print("No stacks found!")
        return 1

    # Create backup
    print("\nCreating backup...")
    backup_path = create_backup(stacks)

    # Cleanup old backups
    print("\nChecking backup retention...")
    cleanup_old_backups()

    # Summary
    print("\n" + "=" * 50)
    print("Backup completed successfully!")
    print(f"Location: {backup_path}")
    print(f"Retention: {RETENTION_DAYS} days / max {MAX_BACKUPS} backups")
    print("=" * 50)

    return 0

if __name__ == "__main__":
    sys.exit(main())
