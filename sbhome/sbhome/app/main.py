"""
sbHome FastAPI Backend
Main application entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.api.routes import traefik, media, network, health, kvm
from app.core.config import settings
from app.services.health_check_service import health_check_service

app = FastAPI(
    title="sbHome API",
    description="Homelab infrastructure dashboard backend",
    version="1.0.0"
)

# Startup event to begin background health checks
@app.on_event("startup")
async def startup_event():
    """Start background services on application startup"""
    await health_check_service.start_background_checks()
    print("Background health checks started")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop background services on application shutdown"""
    health_check_service.stop()
    print("Background health checks stopped")

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(traefik.router, prefix="/api/traefik", tags=["traefik"])
app.include_router(media.router, prefix="/api/media", tags=["media"])
app.include_router(network.router, prefix="/api/network", tags=["network"])
app.include_router(kvm.router, prefix="/api/kvm", tags=["kvm"])
app.include_router(health.router, prefix="/api/health", tags=["health"])

# Serve static files (frontend)
if os.path.exists("public"):
    # Mount assets only if directory exists
    if os.path.exists("public/assets"):
        app.mount("/assets", StaticFiles(directory="public/assets"), name="assets")

    # Mount data directory for JSON files
    if os.path.exists("public/data"):
        app.mount("/data", StaticFiles(directory="public/data"), name="data")

    @app.get("/")
    async def read_index():
        return FileResponse("public/index.html")

@app.get("/api")
async def api_root():
    return {
        "message": "sbHome API",
        "version": "1.0.0",
        "endpoints": {
            "docs": "/docs",
            "traefik": "/api/traefik",
            "media": "/api/media",
            "network": "/api/network",
            "health": "/api/health"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
