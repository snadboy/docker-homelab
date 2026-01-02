#!/usr/bin/env python3
"""
Portainer Stack Backup to Google Drive

Exports all Portainer stacks (docker-compose files) and uploads to Google Drive.
Uses PyDrive2 for Google Drive integration.

Setup:
1. Go to Google Cloud Console: https://console.cloud.google.com/
2. Create a new project (or use existing)
3. Enable Google Drive API
4. Create OAuth 2.0 credentials (Desktop app)
5. Download credentials and save as /app/scripts/gdrive_credentials.json
6. First run will open browser for authentication (creates token)

Environment variables (from /mnt/shareables/.claude/.env):
- PORTAINER_URL
- PORTAINER_API_KEY
"""

import os
import sys
import json
import requests
from datetime import datetime
from pathlib import Path

# Suppress SSL warnings for self-signed certs
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
SCRIPTS_DIR = Path("/app/scripts")
BACKUP_DIR = SCRIPTS_DIR / "backups"
GDRIVE_FOLDER = "Portainer-Backups"  # Folder name in Google Drive
CREDENTIALS_FILE = SCRIPTS_DIR / "gdrive_credentials.json"
TOKEN_FILE = SCRIPTS_DIR / "gdrive_token.json"

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

def upload_to_gdrive(backup_path):
    """Upload backup folder to Google Drive using PyDrive2"""
    try:
        from pydrive2.auth import GoogleAuth
        from pydrive2.drive import GoogleDrive
    except ImportError:
        print("\nERROR: PyDrive2 not installed. Install with:")
        print("  pip install pydrive2")
        return False

    if not CREDENTIALS_FILE.exists():
        print(f"\nERROR: Google Drive credentials not found at {CREDENTIALS_FILE}")
        print("\nSetup instructions:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create/select a project")
        print("3. Enable Google Drive API")
        print("4. Go to Credentials > Create Credentials > OAuth client ID")
        print("5. Choose 'Desktop app'")
        print("6. Download JSON and save as:")
        print(f"   {CREDENTIALS_FILE}")
        return False

    # Authenticate
    gauth = GoogleAuth()
    gauth.settings['client_config_file'] = str(CREDENTIALS_FILE)

    # Try to load saved credentials
    if TOKEN_FILE.exists():
        gauth.LoadCredentialsFile(str(TOKEN_FILE))

    if gauth.credentials is None:
        # First time - need browser auth
        print("\nFirst-time authentication required.")
        print("This will open a browser window for Google sign-in.")
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        gauth.Refresh()
    else:
        gauth.Authorize()

    # Save credentials for next time
    gauth.SaveCredentialsFile(str(TOKEN_FILE))

    drive = GoogleDrive(gauth)

    # Find or create backup folder
    folder_query = f"title='{GDRIVE_FOLDER}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    folder_list = drive.ListFile({'q': folder_query}).GetList()

    if folder_list:
        folder_id = folder_list[0]['id']
        print(f"\nUsing existing Google Drive folder: {GDRIVE_FOLDER}")
    else:
        folder_metadata = {
            'title': GDRIVE_FOLDER,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = drive.CreateFile(folder_metadata)
        folder.Upload()
        folder_id = folder['id']
        print(f"\nCreated Google Drive folder: {GDRIVE_FOLDER}")

    # Create subfolder for this backup
    backup_folder_name = backup_path.name
    subfolder_metadata = {
        'title': backup_folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [{'id': folder_id}]
    }
    subfolder = drive.CreateFile(subfolder_metadata)
    subfolder.Upload()
    subfolder_id = subfolder['id']

    # Upload all files
    uploaded_count = 0
    for filepath in backup_path.rglob("*"):
        if filepath.is_file():
            relative_path = filepath.relative_to(backup_path)

            # Determine parent folder
            if len(relative_path.parts) > 1:
                # Create intermediate folder if needed
                parent_name = relative_path.parts[0]
                parent_query = f"title='{parent_name}' and '{subfolder_id}' in parents and trashed=false"
                parent_list = drive.ListFile({'q': parent_query}).GetList()

                if parent_list:
                    parent_id = parent_list[0]['id']
                else:
                    parent_meta = {
                        'title': parent_name,
                        'mimeType': 'application/vnd.google-apps.folder',
                        'parents': [{'id': subfolder_id}]
                    }
                    parent_folder = drive.CreateFile(parent_meta)
                    parent_folder.Upload()
                    parent_id = parent_folder['id']
            else:
                parent_id = subfolder_id

            # Upload file
            file_metadata = {
                'title': filepath.name,
                'parents': [{'id': parent_id}]
            }
            gfile = drive.CreateFile(file_metadata)
            gfile.SetContentFile(str(filepath))
            gfile.Upload()
            uploaded_count += 1
            print(f"  Uploaded: {relative_path}")

    print(f"\nUploaded {uploaded_count} files to Google Drive/{GDRIVE_FOLDER}/{backup_folder_name}/")
    return True

def main():
    print("=" * 50)
    print("Portainer Stack Backup")
    print("=" * 50)
    print(f"Timestamp: {datetime.now().isoformat()}\n")

    # Load environment
    load_env()

    # Get stacks from Portainer
    print("Fetching stacks from Portainer...")
    stacks = get_portainer_stacks()

    if not stacks:
        print("No stacks found!")
        return 1

    # Create local backup
    print("\nCreating local backup...")
    backup_path = create_backup(stacks)

    # Upload to Google Drive
    print("\nUploading to Google Drive...")
    if upload_to_gdrive(backup_path):
        print("\n" + "=" * 50)
        print("Backup completed successfully!")
        print("=" * 50)
    else:
        print("\n" + "=" * 50)
        print("Local backup created, but Google Drive upload failed.")
        print(f"Backup location: {backup_path}")
        print("=" * 50)
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
