"""
Configuration management for sbHome
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # API Keys
    TRAEFIK_HTTP_PROVIDER_URL: str = "http://host-cadre:8081"
    TAUTULLI_URL: str = ""
    TAUTULLI_API_KEY: str = ""
    RADARR_URL: str = ""
    RADARR_API_KEY: str = ""
    SABNZBD_URL: str = ""
    SABNZBD_API_KEY: str = ""
    OVERSEERR_URL: str = ""
    OVERSEERR_API_KEY: str = ""
    UNIFI_URL: str = "https://192.168.86.1"
    UNIFI_USERNAME: str = "claude"
    UNIFI_PASSWORD: str = ""

    # Cache settings
    CACHE_TTL: int = 30  # seconds

    # Development
    DEBUG: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


settings = get_settings()
