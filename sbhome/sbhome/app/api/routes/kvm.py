"""
KVM API routes
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any

from app.services.kvm_service import kvm_service

router = APIRouter()


@router.get("/devices")
async def get_kvm_devices() -> List[Dict[str, Any]]:
    """Get all KVM devices"""
    try:
        return await kvm_service.get_kvm_devices()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
