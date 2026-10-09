"""Caching system for download results to avoid redundant downloads."""

import asyncio
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from config import logger


@dataclass
class CacheEntry:
    """Represents a cached download result."""
    url: str
    file_path: Optional[Path]
    metadata: Dict[str, Any]
    timestamp: float
    expiry: float


class CacheManager:
    """Manages caching of download results."""

    def __init__(self, cache_ttl: int = 3600):
        """
        Initialize cache manager.
        
        Args:
            cache_ttl: Time-to-live for cache entries in seconds (default 1 hour)
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
        self._cache_ttl = cache_ttl
        self._cleanup_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    def _generate_key(self, url: str, quality: Optional[int] = None, media_type: str = "video") -> str:
        """Generate unique cache key from URL and parameters."""
        key_data = f"{url}:{quality}:{media_type}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    async def get(
        self,
        url: str,
        quality: Optional[int] = None,
        media_type: str = "video"
    ) -> Optional[CacheEntry]:
        """
        Retrieve cached entry if valid.
        
        Args:
            url: Download URL
            quality: Video quality (if applicable)
            media_type: Type of media (video, audio, etc.)
        
        Returns:
            CacheEntry if found and valid, None otherwise
        """
        async with self._lock:
            key = self._generate_key(url, quality, media_type)
            entry = self._cache.get(key)

            if entry is None:
                return None

            # Check if entry has expired
            if time.time() > entry.expiry:
                logger.info("Cache entry expired for key %s", key)
                del self._cache[key]
                return None

            # Check if cached file still exists
            if entry.file_path and not entry.file_path.exists():
                logger.warning("Cached file no longer exists: %s", entry.file_path)
                del self._cache[key]
                return None

            logger.info("Cache hit for URL: %s (quality=%s, type=%s)", url, quality, media_type)
            return entry

    async def set(
        self,
        url: str,
        file_path: Optional[Path],
        metadata: Optional[Dict[str, Any]] = None,
        quality: Optional[int] = None,
        media_type: str = "video",
        ttl: Optional[int] = None,
    ) -> None:
        """
        Store download result in cache.
        
        Args:
            url: Download URL
            file_path: Path to downloaded file
            metadata: Additional metadata about the download
            quality: Video quality (if applicable)
            media_type: Type of media
            ttl: Custom TTL for this entry (overrides default)
        """
        async with self._lock:
            key = self._generate_key(url, quality, media_type)
            expiry_time = time.time() + (ttl or self._cache_ttl)
            
            entry = CacheEntry(
                url=url,
                file_path=file_path,
                metadata=metadata or {},
                timestamp=time.time(),
                expiry=expiry_time,
            )
            
            self._cache[key] = entry
            logger.info(
                "Cached result for URL: %s (quality=%s, type=%s, expires in %ds)",
                url, quality, media_type, ttl or self._cache_ttl
            )

    async def invalidate(
        self,
        url: str,
        quality: Optional[int] = None,
        media_type: str = "video"
    ) -> None:
        """Remove entry from cache."""
        async with self._lock:
            key = self._generate_key(url, quality, media_type)
            if key in self._cache:
                del self._cache[key]
                logger.info("Invalidated cache for URL: %s", url)

    async def clear_expired(self) -> int:
        """Remove all expired entries from cache."""
        async with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, entry in self._cache.items()
                if current_time > entry.expiry or (entry.file_path and not entry.file_path.exists())
            ]
            
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                logger.info("Cleared %d expired cache entries", len(expired_keys))
            
            return len(expired_keys)

    async def start_cleanup(self, interval: int = 600) -> None:
        """Start background task to periodically clean expired entries."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop(interval))
        logger.info("Cache cleanup task started (interval: %ds)", interval)

    async def stop_cleanup(self) -> None:
        """Stop the cleanup background task."""
        self._stop_event.set()
        if self._cleanup_task:
            await self._cleanup_task
        logger.info("Cache cleanup task stopped")

    async def _cleanup_loop(self, interval: int) -> None:
        """Background task to periodically clean cache."""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                await self.clear_expired()
            else:
                break

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        async with self._lock:
            total_entries = len(self._cache)
            valid_entries = sum(
                1 for entry in self._cache.values()
                if time.time() <= entry.expiry and (not entry.file_path or entry.file_path.exists())
            )
            
            return {
                "total_entries": total_entries,
                "valid_entries": valid_entries,
                "expired_entries": total_entries - valid_entries,
            }


# Global cache manager instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager(cache_ttl: int = 3600) -> CacheManager:
    """Get or create the global cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager(cache_ttl)
    return _cache_manager
