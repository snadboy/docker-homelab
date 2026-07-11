"""
Network API routes (UniFi)
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any

from app.services.unifi_service import unifi_service

router = APIRouter()


@router.get("/unifi/devices")
async def get_unifi_devices() -> List[Dict[str, Any]]:
    """Get all UniFi network devices"""
    try:
        return await unifi_service.get_devices()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unifi/gateway")
async def get_unifi_gateway() -> Dict[str, Any]:
    """Get gateway statistics"""
    try:
        return await unifi_service.get_gateway_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unifi/clients")
async def get_unifi_clients() -> List[Dict[str, Any]]:
    """Get all connected clients"""
    try:
        return await unifi_service.get_clients()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unifi/stats")
async def get_network_stats() -> Dict[str, Any]:
    """Get aggregated network statistics"""
    try:
        return await unifi_service.get_network_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
