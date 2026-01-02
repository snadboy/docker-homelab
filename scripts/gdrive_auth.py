#!/usr/bin/env python3
"""
Google Drive OAuth Authentication Helper

Run this script LOCALLY (not in Docker) to generate the OAuth token.
Then copy the token file to the Script Server container.

Usage:
  1. Run locally: python gdrive_auth.py
  2. Browser will open for Google sign-in
  3. Copy the generated token to container:
     docker cp gdrive_token.json script-server:/app/scripts/
"""

import sys
from pathlib import Path

try:
    from pydrive2.auth import GoogleAuth
    from pydrive2.drive import GoogleDrive
except ImportError:
    print("PyDrive2 not installed. Install with: pip install pydrive2")
    sys.exit(1)

# Look for credentials in common locations
CREDENTIALS_LOCATIONS = [
    Path("gdrive_credentials.json"),
    Path("client_secret_gdrive.json"),
    Path.home() / ".claude" / "client_secret_gdrive.json",
    Path("/app/scripts/gdrive_credentials.json"),
]

def find_credentials():
    for path in CREDENTIALS_LOCATIONS:
        if path.exists():
            return path
    return None

def main():
    print("=" * 50)
    print("Google Drive OAuth Authentication")
    print("=" * 50)

    creds_file = find_credentials()
    if not creds_file:
        print("\nERROR: Could not find credentials file.")
        print("Searched locations:")
        for loc in CREDENTIALS_LOCATIONS:
            print(f"  - {loc}")
        print("\nDownload OAuth credentials from Google Cloud Console")
        print("and save as 'gdrive_credentials.json' in the current directory.")
        return 1

    print(f"\nUsing credentials: {creds_file}")

    # Setup auth
    gauth = GoogleAuth()
    gauth.settings['client_config_file'] = str(creds_file)

    # This will open a browser
    print("\nOpening browser for Google sign-in...")
    print("(If browser doesn't open, check the console for a URL)")
    gauth.LocalWebserverAuth()

    # Save the token
    token_file = Path("gdrive_token.json")
    gauth.SaveCredentialsFile(str(token_file))

    print(f"\nToken saved to: {token_file.absolute()}")
    print("\nNext steps:")
    print("  1. Copy token to container:")
    print(f"     scp {token_file} snadboy@arr:/tmp/")
    print("     ssh snadboy@arr 'docker cp /tmp/gdrive_token.json script-server:/app/scripts/'")
    print("\n  2. Test the backup script in Script Server")

    # Quick test
    print("\nTesting connection...")
    drive = GoogleDrive(gauth)
    about = drive.GetAbout()
    print(f"Connected as: {about['user']['displayName']} ({about['user']['emailAddress']})")
    print(f"Storage used: {int(about['quotaBytesUsed']) / 1024 / 1024:.1f} MB")

    return 0

if __name__ == "__main__":
    sys.exit(main())
