"""
Traefik API routes
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any

from app.services.traefik_service import traefik_service

router = APIRouter()


@router.get("/services")
async def get_services() -> Dict[str, Any]:
    """Get all Traefik services"""
    try:
        return await traefik_service.get_services()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/routes")
async def get_routes() -> List[Dict[str, Any]]:
    """Get all routes"""
    try:
        return await traefik_service.get_routes()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/routes/docker")
async def get_docker_routes() -> List[Dict[str, Any]]:
    """Get Docker container routes only"""
    try:
        return await traefik_service.get_docker_routes()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/routes/static")
async def get_static_routes() -> List[Dict[str, Any]]:
    """Get static routes only"""
    try:
        return await traefik_service.get_static_routes()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
