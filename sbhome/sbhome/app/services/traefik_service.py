"""
Traefik HTTP Provider service
"""
import httpx
from typing import List, Dict, Any

from app.core.config import settings
from app.core.cache import cache


class TraefikService:
    """Service for interacting with Traefik HTTP Provider"""

    def __init__(self):
        self.base_url = settings.TRAEFIK_HTTP_PROVIDER_URL

    async def get_services(self) -> Dict[str, Any]:
        """Get all services from Traefik HTTP Provider"""
        cache_key = "traefik:services"
        cached = await cache.get(cache_key)
        if cached:
            return cached

        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            response = await client.get(f"{self.base_url}/services")
            response.raise_for_status()
            data = response.json()

        await cache.set(cache_key, data, ttl=30)
        return data

    async def get_routes(self) -> List[Dict[str, Any]]:
        """Get all routes"""
        services = await self.get_services()
        return services.get("services", [])

    async def get_docker_routes(self) -> List[Dict[str, Any]]:
        """Get Docker container routes only"""
        routes = await self.get_routes()
        return [r for r in routes if not r.get("is_static", False)]

    async def get_static_routes(self) -> List[Dict[str, Any]]:
        """Get static routes only"""
        routes = await self.get_routes()
        return [r for r in routes if r.get("is_static", False)]


traefik_service = TraefikService()
