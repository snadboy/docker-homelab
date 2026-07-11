"""
Media services (Tautulli, Radarr, SABnzbd, Overseerr)
"""
import httpx
from typing import List, Dict, Any
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.cache import cache


class TautulliService:
    """Tautulli/Plex statistics service"""

    async def get_activity(self) -> Dict[str, Any]:
        """Get current Plex activity"""
        cache_key = "tautulli:activity"
        cached = await cache.get(cache_key)
        if cached:
            return cached

        url = f"{settings.TAUTULLI_URL}/api/v2"
        params = {
            "apikey": settings.TAUTULLI_API_KEY,
            "cmd": "get_activity"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        result = {
            "stream_count": data.get("response", {}).get("data", {}).get("stream_count", 0),
            "sessions": data.get("response", {}).get("data", {}).get("sessions", [])
        }

        await cache.set(cache_key, result, ttl=10)
        return result

    async def get_recently_added(self, count: int = 50) -> List[Dict[str, Any]]:
        """Get recently added episodes from today"""
        cache_key = f"tautulli:recently_added:{count}"
        cached = await cache.get(cache_key)
        if cached:
            return cached

        url = f"{settings.TAUTULLI_URL}/api/v2"
        params = {
            "apikey": settings.TAUTULLI_API_KEY,
            "cmd": "get_recently_added",
            "count": count
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        # Filter for today's episodes
        yesterday_timestamp = int((datetime.now() - timedelta(days=1)).timestamp())
        episodes = []

        for item in data.get("response", {}).get("data", {}).get("recently_added", []):
            if item.get("media_type") == "episode" and item.get("added_at", 0) >= yesterday_timestamp:
                episodes.append({
                    "title": item.get("grandparent_title"),
                    "episode_title": item.get("title"),
                    "season": item.get("parent_media_index"),
                    "episode": item.get("media_index"),
                    "season_episode": f"S{str(item.get('parent_media_index', 0)).zfill(2)}E{str(item.get('media_index', 0)).zfill(2)}"
                })

        await cache.set(cache_key, episodes, ttl=300)  # 5 minutes
        return episodes


class RadarrService:
    """Radarr movie management service"""

    async def get_queue(self) -> Dict[str, Any]:
        """Get Radarr download queue"""
        cache_key = "radarr:queue"
        cached = await cache.get(cache_key)
        if cached:
            return cached

        url = f"{settings.RADARR_URL}/api/v3/queue"
        headers = {"X-Api-Key": settings.RADARR_API_KEY}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

        result = {
            "totalRecords": data.get("totalRecords", 0),
            "records": [
                {
                    "title": r.get("title"),
                    "status": r.get("status"),
                    "timeleft": r.get("timeleft"),
                    "sizeleft": r.get("sizeleft"),
                    "size": r.get("size")
                }
                for r in data.get("records", [])
            ]
        }

        await cache.set(cache_key, result, ttl=15)
        return result


class SabnzbdService:
    """SABnzbd download service"""

    async def get_status(self) -> Dict[str, Any]:
        """Get SABnzbd queue status"""
        cache_key = "sabnzbd:status"
        cached = await cache.get(cache_key)
        if cached:
            return cached

        url = f"{settings.SABNZBD_URL}/api"
        params = {
            "mode": "queue",
            "apikey": settings.SABNZBD_API_KEY,
            "output": "json"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        queue = data.get("queue", {})
        result = {
            "status": queue.get("status", "Unknown"),
            "paused": queue.get("paused", False),
            "speed": queue.get("speed", "0"),
            "queue_items": queue.get("noofslots", "0"),
            "timeleft": queue.get("timeleft", ""),
            "mb_left": queue.get("mbleft", "")
        }

        await cache.set(cache_key, result, ttl=10)
        return result


class OverseerrService:
    """Overseerr media request service"""

    async def get_request_counts(self) -> Dict[str, Any]:
        """Get Overseerr request counts"""
        cache_key = "overseerr:counts"
        cached = await cache.get(cache_key)
        if cached:
            return cached

        url = f"{settings.OVERSEERR_URL}/api/v1/request/count"
        headers = {"X-Api-Key": settings.OVERSEERR_API_KEY}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

        await cache.set(cache_key, data, ttl=60)
        return data


# Service instances
tautulli_service = TautulliService()
radarr_service = RadarrService()
sabnzbd_service = SabnzbdService()
overseerr_service = OverseerrService()
