"""
KVM device discovery service
"""
import socket
import subprocess
from typing import List, Dict, Any

from app.core.cache import cache


class KVMService:
    """Service for discovering KVM devices via DNS"""

    KVM_LOCATIONS = ["office", "family-room", "laundry", "garage"]
    DNS_DOMAIN = "isnadboy.com"

    async def get_kvm_devices(self) -> List[Dict[str, Any]]:
        """Get all KVM devices from DNS"""
        cache_key = "kvm:devices"
        cached = await cache.get(cache_key)
        if cached:
            return cached

        devices = []
        for location in self.KVM_LOCATIONS:
            hostname = f"host-kvm-{location}.{self.DNS_DOMAIN}"

            try:
                # Get IP address
                ip = socket.gethostbyname(hostname)

                # Try to get CNAME (actual target)
                try:
                    result = subprocess.run(
                        ["dig", "+short", hostname, "CNAME"],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    cname = result.stdout.strip().rstrip('.') if result.returncode == 0 else None
                except:
                    cname = None

                devices.append({
                    "name": f"KVM - {location.replace('-', ' ').title()}",
                    "hostname": hostname,
                    "ip": ip,
                    "cname": cname,
                    "location": location,
                    "url": f"https://{hostname}"
                })
            except socket.gaierror:
                # DNS lookup failed - device doesn't exist
                continue
            except Exception as e:
                # Other error - log but continue
                print(f"Error resolving {hostname}: {e}")
                continue

        await cache.set(cache_key, devices, ttl=300)  # Cache for 5 minutes
        return devices


kvm_service = KVMService()
