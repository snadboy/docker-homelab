"""
Health checking service for all dashboard items
"""
import asyncio
import httpx
from typing import Dict, Any, List
from datetime import datetime
import socket
import traceback

from app.core.cache import cache


class HealthCheckService:
    """Service for checking health of all dashboard items"""

    def __init__(self):
        self.check_interval = 60  # seconds
        self.timeout = 5  # seconds for each check
        self._running = False

    async def start_background_checks(self):
        """Start background health checking loop"""
        if self._running:
            return

        self._running = True
        asyncio.create_task(self._check_loop())

    async def _check_loop(self):
        """Background loop that runs health checks every 60 seconds"""
        while self._running:
            try:
                await self.check_all_health()
            except Exception as e:
                print(f"Health check error: {e}")

            await asyncio.sleep(self.check_interval)

    async def check_all_health(self):
        """Check health of all services and store results"""
        # Import services here to avoid circular imports
        from app.services.traefik_service import traefik_service
        from app.services.kvm_service import kvm_service

        results = {}

        # Check Traefik services
        try:
            services_data = await traefik_service.get_services()
            services = services_data.get("services", [])
            print(f"Health check: Got {len(services)} Traefik services to check")

            # Check each service in parallel (limited concurrency)
            tasks = []
            for service in services:
                tasks.append(self._check_service(service))

            # Run checks with limited concurrency
            sem = asyncio.Semaphore(10)  # Max 10 concurrent checks
            async def bounded_check(task):
                async with sem:
                    return await task

            service_results = await asyncio.gather(
                *[bounded_check(task) for task in tasks],
                return_exceptions=True
            )

            for result in service_results:
                if isinstance(result, dict):
                    results[result["id"]] = result
        except Exception as e:
            print(f"Error checking Traefik services: {e}")
            traceback.print_exc()

        # Check KVM devices
        try:
            kvm_devices = await kvm_service.get_kvm_devices()
            kvm_tasks = [self._check_kvm(device) for device in kvm_devices]
            kvm_results = await asyncio.gather(*kvm_tasks, return_exceptions=True)

            for result in kvm_results:
                if isinstance(result, dict):
                    results[result["id"]] = result
        except Exception as e:
            print(f"Error checking KVM devices: {e}")

        # Store all results in cache
        await cache.set("health_status", results, ttl=120)  # Cache for 2 minutes

        return results

    async def _check_service(self, service: Dict[str, Any]) -> Dict[str, Any]:
        """Check health of a single Traefik service"""
        service_id = f"traefik-{service.get('name', 'unknown')}"
        url = service.get('public_url', '')

        status = await self._check_url(url, allow_redirects=True)

        return {
            "id": service_id,
            "type": "traefik",
            "name": service.get("name"),
            "healthy": status["healthy"],
            "status_code": status.get("status_code"),
            "response_time_ms": status.get("response_time_ms"),
            "last_checked": datetime.utcnow().isoformat()
        }

    async def _check_kvm(self, device: Dict[str, Any]) -> Dict[str, Any]:
        """Check health of a KVM device"""
        device_id = f"kvm-{device.get('location', 'unknown')}"
        url = device.get('url', '')

        # KVM devices may have self-signed certs, so we allow that
        status = await self._check_url(url, allow_redirects=False, verify_ssl=False)

        return {
            "id": device_id,
            "type": "kvm",
            "name": device.get("name"),
            "healthy": status["healthy"],
            "status_code": status.get("status_code"),
            "response_time_ms": status.get("response_time_ms"),
            "last_checked": datetime.utcnow().isoformat()
        }

    async def _check_url(
        self,
        url: str,
        allow_redirects: bool = True,
        verify_ssl: bool = False
    ) -> Dict[str, Any]:
        """Check if a URL is reachable"""
        if not url:
            return {"healthy": False, "error": "No URL provided"}

        try:
            start_time = asyncio.get_event_loop().time()

            async with httpx.AsyncClient(
                timeout=self.timeout,
                verify=verify_ssl,
                follow_redirects=allow_redirects
            ) as client:
                response = await client.get(url)

                end_time = asyncio.get_event_loop().time()
                response_time = int((end_time - start_time) * 1000)

                # Consider 2xx and 3xx as healthy
                healthy = 200 <= response.status_code < 400

                return {
                    "healthy": healthy,
                    "status_code": response.status_code,
                    "response_time_ms": response_time
                }
        except httpx.TimeoutException:
            return {"healthy": False, "error": "Timeout"}
        except httpx.ConnectError:
            return {"healthy": False, "error": "Connection refused"}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def get_health_status(self) -> Dict[str, Any]:
        """Get cached health status for all services"""
        status = await cache.get("health_status")
        if status is None:
            # If no cached status, trigger a check and return empty for now
            asyncio.create_task(self.check_all_health())
            return {}
        return status

    def stop(self):
        """Stop background health checks"""
        self._running = False


# Global instance
health_check_service = HealthCheckService()
