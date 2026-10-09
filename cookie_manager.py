"""Async cookie management system with auto-reload capability."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import logger


class CookieManager:
    """Manages cookie files with automatic reload on file changes."""

    def __init__(self, cookie_file: Path):
        self.cookie_file = cookie_file
        self._last_modified: Optional[float] = None
        self._lock = asyncio.Lock()
        self._reload_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start_monitoring(self, check_interval: int = 30) -> None:
        """Start background task to monitor cookie file changes."""
        self._reload_task = asyncio.create_task(
            self._monitor_cookie_file(check_interval)
        )
        logger.info("Cookie monitoring started for %s", self.cookie_file)

    async def stop_monitoring(self) -> None:
        """Stop the background monitoring task."""
        self._stop_event.set()
        if self._reload_task:
            await self._reload_task
        logger.info("Cookie monitoring stopped")

    async def _monitor_cookie_file(self, check_interval: int) -> None:
        """Background task to check for cookie file updates."""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=check_interval
                )
            except asyncio.TimeoutError:
                await self._check_and_reload()
            else:
                break

    async def _check_and_reload(self) -> None:
        """Check if cookie file has been modified and reload if needed."""
        async with self._lock:
            if not self.cookie_file.exists():
                if self._last_modified is not None:
                    logger.warning("Cookie file %s no longer exists", self.cookie_file)
                    self._last_modified = None
                return

            try:
                current_mtime = self.cookie_file.stat().st_mtime
                if self._last_modified is None:
                    self._last_modified = current_mtime
                    logger.info("Cookie file loaded: %s", self.cookie_file)
                elif current_mtime > self._last_modified:
                    self._last_modified = current_mtime
                    logger.info(
                        "Cookie file %s was updated at %s",
                        self.cookie_file,
                        datetime.fromtimestamp(current_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    )
            except Exception as exc:
                logger.error("Error checking cookie file: %s", exc)

    def get_cookie_args(self, use_browser_cookies: bool = True) -> list[str]:
        """
        Get appropriate cookie arguments for yt-dlp.
        
        Args:
            use_browser_cookies: If True, use browser cookies; if False, use file
        
        Returns:
            List of cookie-related arguments for yt-dlp command
        """
        if use_browser_cookies:
            return ["--cookies-from-browser", "chrome"]
        
        if self.cookie_file.exists():
            return ["--cookies", str(self.cookie_file)]
        
        return []

    async def is_file_valid(self) -> bool:
        """Check if cookie file exists and is readable."""
        async with self._lock:
            return self.cookie_file.exists() and self.cookie_file.is_file()


# Global cookie manager instance
_cookie_manager: Optional[CookieManager] = None


def get_cookie_manager(cookie_file: Path) -> CookieManager:
    """Get or create the global cookie manager instance."""
    global _cookie_manager
    if _cookie_manager is None:
        _cookie_manager = CookieManager(cookie_file)
    return _cookie_manager
