"""
UniFi Network service
"""
import httpx
from typing import List, Dict, Any

from app.core.config import settings
from app.core.cache import cache


class UnifiService:
    """UniFi Network controller service"""

    def __init__(self):
        self.base_url = settings.UNIFI_URL
        self.username = settings.UNIFI_USERNAME
        self.password = settings.UNIFI_PASSWORD
        self._csrf_token = None
        self._cookies = None

    async def _authenticate(self):
        """Authenticate with UniFi controller"""
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            # Login
            login_data = {
                "username": self.username,
                "password": self.password
            }
            response = await client.post(
                f"{self.base_url}/api/auth/login",
                json=login_data
            )
            response.raise_for_status()

            # Save cookies and CSRF token
            self._cookies = response.cookies
            self._csrf_token = response.headers.get("x-csrf-token")

    async def _make_request(self, endpoint: str) -> Dict[str, Any]:
        """Make authenticated request to UniFi API"""
        # Ensure we're authenticated
        if not self._csrf_token:
            await self._authenticate()

        url = f"{self.base_url}/proxy/network/api/s/default/{endpoint}"
        headers = {"X-Csrf-Token": self._csrf_token}

        async with httpx.AsyncClient(verify=False, timeout=10.0, cookies=self._cookies) as client:
            response = await client.get(url, headers=headers)

            # Re-authenticate if token expired
            if response.status_code == 401:
                await self._authenticate()
                headers = {"X-Csrf-Token": self._csrf_token}
                response = await client.get(url, headers=headers)

            response.raise_for_status()
            return response.json()

    async def get_devices(self) -> List[Dict[str, Any]]:
        """Get all UniFi devices"""
        cache_key = "unifi:devices"
        cached = await cache.get(cache_key)
        if cached:
            return cached

        data = await self._make_request("stat/device")

        devices = [
            {
                "name": d.get("name"),
                "ip": d.get("ip"),
                "type": d.get("type"),
                "model": d.get("model"),
                "mac": d.get("mac"),
                "num_sta": d.get("num_sta", 0),
                "user_num_sta": d.get("user-num_sta", 0),
                "guest_num_sta": d.get("guest-num_sta", 0),
                "uptime": d.get("uptime", 0),
                "state": d.get("state", 0),
                "cpu": d.get("system-stats", {}).get("cpu", 0),
                "mem": d.get("system-stats", {}).get("mem", 0)
            }
            for d in data.get("data", [])
        ]

        await cache.set(cache_key, devices, ttl=300)  # 5 minutes
        return devices

    async def get_gateway_stats(self) -> Dict[str, Any]:
        """Get gateway statistics"""
        cache_key = "unifi:gateway_stats"
        cached = await cache.get(cache_key)
        if cached:
            return cached

        data = await self._make_request("stat/device")

        # Find gateway device
        gateway = None
        for device in data.get("data", []):
            if device.get("type") in ["udm", "uxg", "ugw", "usg"]:
                gateway = device
                break

        if not gateway:
            return {}

        result = {
            "name": gateway.get("name", "Unknown"),
            "model": gateway.get("model", "Unknown"),
            "cpu": gateway.get("system-stats", {}).get("cpu", 0),
            "mem": gateway.get("system-stats", {}).get("mem", 0),
            "uptime": gateway.get("uptime", 0),
            "wan_ip": gateway.get("wan1", {}).get("ip", "N/A"),
            "version": gateway.get("version", "Unknown"),
            "speedtest_status": gateway.get("speedtest-status", {}),
            "wan_uptime": gateway.get("uptime", 0)
        }

        await cache.set(cache_key, result, ttl=30)
        return result

    async def get_clients(self) -> List[Dict[str, Any]]:
        """Get all connected clients"""
        cache_key = "unifi:clients"
        cached = await cache.get(cache_key)
        if cached:
            return cached

        data = await self._make_request("stat/sta")

        clients = []
        for client in data.get("data", []):
            clients.append({
                "mac": client.get("mac", ""),
                "name": client.get("name") or client.get("hostname") or client.get("mac", "Unknown"),
                "ip": client.get("ip", "N/A"),
                "is_wired": client.get("is_wired", False),
                "is_guest": client.get("is_guest", False),
                "ap_mac": client.get("ap_mac"),
                "network": client.get("network", "Unknown"),
                "rx_bytes": client.get("rx_bytes", 0),
                "tx_bytes": client.get("tx_bytes", 0),
                "signal": client.get("signal", 0),
                "channel": client.get("channel", 0),
                "radio": client.get("radio", ""),
                "essid": client.get("essid", "")
            })

        await cache.set(cache_key, clients, ttl=10)
        return clients

    async def get_network_stats(self) -> Dict[str, Any]:
        """Get aggregated network statistics"""
        cache_key = "unifi:network_stats"
        cached = await cache.get(cache_key)
        if cached:
            return cached

        # Fetch all data
        clients = await self.get_clients()
        devices = await self.get_devices()
        gateway = await self.get_gateway_stats()

        # Count clients by type
        wired_clients = sum(1 for c in clients if c["is_wired"])
        wireless_clients = len(clients) - wired_clients

        # Filter devices
        aps = [d for d in devices if d["type"] == "uap"]
        switches = [d for d in devices if d["type"] == "usw"]

        # Sort clients by total bandwidth
        clients_with_total = []
        for client in clients:
            total_bytes = client["rx_bytes"] + client["tx_bytes"]
            clients_with_total.append({**client, "total_bytes": total_bytes})

        top_clients = sorted(clients_with_total, key=lambda x: x["total_bytes"], reverse=True)[:10]

        # Group clients by band
        band_2g = sum(1 for c in clients if not c["is_wired"] and c["radio"] == "ng")
        band_5g = sum(1 for c in clients if not c["is_wired"] and c["radio"] == "na")
        band_6g = sum(1 for c in clients if not c["is_wired"] and c["radio"] == "6e")

        # Group clients by SSID
        ssid_counts = {}
        for client in clients:
            if not client["is_wired"]:
                ssid = client.get("essid", "Unknown")
                ssid_counts[ssid] = ssid_counts.get(ssid, 0) + 1

        # Add "Wired" to SSID distribution
        if wired_clients > 0:
            ssid_counts["Wired"] = wired_clients

        result = {
            "gateway": gateway,
            "total_clients": len(clients),
            "wired_clients": wired_clients,
            "wireless_clients": wireless_clients,
            "total_devices": len(devices),
            "aps": len(aps),
            "switches": len(switches),
            "ap_details": aps,
            "switch_details": switches,
            "top_clients": top_clients,
            "band_distribution": {
                "2g": band_2g,
                "5g": band_5g,
                "6g": band_6g,
                "wired": wired_clients
            },
            "ssid_distribution": ssid_counts
        }

        await cache.set(cache_key, result, ttl=10)
        return result


unifi_service = UnifiService()
