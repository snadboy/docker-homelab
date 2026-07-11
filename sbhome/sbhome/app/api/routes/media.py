"""
Media API routes (Plex, Radarr, SABnzbd, Overseerr)
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any

from app.services.media_service import (
    tautulli_service,
    radarr_service,
    sabnzbd_service,
    overseerr_service
)

router = APIRouter()


@router.get("/streams")
async def get_streams() -> Dict[str, Any]:
    """Get current Plex streams"""
    try:
        return await tautulli_service.get_activity()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/episodes/today")
async def get_todays_episodes() -> List[Dict[str, Any]]:
    """Get today's episodes"""
    try:
        return await tautulli_service.get_recently_added()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/radarr")
async def get_radarr_queue() -> Dict[str, Any]:
    """Get Radarr download queue"""
    try:
        return await radarr_service.get_queue()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/sabnzbd")
async def get_sabnzbd_status() -> Dict[str, Any]:
    """Get SABnzbd queue status"""
    try:
        return await sabnzbd_service.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/requests/overseerr")
async def get_overseerr_counts() -> Dict[str, Any]:
    """Get Overseerr request counts"""
    try:
        return await overseerr_service.get_request_counts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard")
async def get_media_dashboard() -> Dict[str, Any]:
    """Get all media data for dashboard"""
    try:
        streams, episodes, radarr, sabnzbd, overseerr = await asyncio.gather(
            tautulli_service.get_activity(),
            tautulli_service.get_recently_added(),
            radarr_service.get_queue(),
            sabnzbd_service.get_status(),
            overseerr_service.get_request_counts(),
            return_exceptions=True
        )

        return {
            "streams": streams if not isinstance(streams, Exception) else {"stream_count": 0, "sessions": []},
            "todaysEpisodes": episodes if not isinstance(episodes, Exception) else [],
            "radarrQueue": radarr if not isinstance(radarr, Exception) else {"totalRecords": 0, "records": []},
            "sabnzbdStatus": sabnzbd if not isinstance(sabnzbd, Exception) else {"status": "Unknown", "queue_items": "0"},
            "overseerrCounts": overseerr if not isinstance(overseerr, Exception) else {"total": 0, "pending": 0}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
