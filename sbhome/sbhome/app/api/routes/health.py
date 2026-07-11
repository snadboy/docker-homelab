"""
Health check API routes
"""
from fastapi import APIRouter
from typing import Dict, Any
from app.core.cache import cache
from app.services.health_check_service import health_check_service

router = APIRouter()


@router.get("")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "cache_size": cache.size()
    }


@router.get("/status")
async def get_health_status() -> Dict[str, Any]:
    """Get health status of all monitored services"""
    return await health_check_service.get_health_status()
