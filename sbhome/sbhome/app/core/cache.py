"""
Simple in-memory cache with TTL
"""
from datetime import datetime, timedelta
from typing import Any, Optional
import asyncio


class SimpleCache:
    """Simple in-memory cache with TTL support"""

    def __init__(self):
        self._cache = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired"""
        async with self._lock:
            if key in self._cache:
                value, expires_at = self._cache[key]
                if datetime.now() < expires_at:
                    return value
                else:
                    # Expired, remove it
                    del self._cache[key]
            return None

    async def set(self, key: str, value: Any, ttl: int = 30):
        """Set cached value with TTL in seconds"""
        async with self._lock:
            expires_at = datetime.now() + timedelta(seconds=ttl)
            self._cache[key] = (value, expires_at)

    async def clear(self):
        """Clear all cached values"""
        async with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """Get number of cached items"""
        return len(self._cache)


# Global cache instance
cache = SimpleCache()
