"""Async cookie management system with auto-reload and regeneration."""

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
        self._regen_lock = asyncio.Lock()
        self._reload_task: Optional[asyncio.Task] = None
        self._auto_regen_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start_monitoring(self, check_interval: int = 30, regen_interval: int = 12 * 60 * 60) -> None:
        """Start background task to monitor cookie file changes."""
        if self._reload_task or self._auto_regen_task:
            logger.warning("Cookie monitoring already running")
            return

        self._stop_event = asyncio.Event()
        await self._check_and_reload()

        self._reload_task = asyncio.create_task(
            self._monitor_cookie_file(check_interval)
        )
        self._auto_regen_task = asyncio.create_task(
            self._auto_regen_loop(regen_interval)
        )
        logger.info(
            "Cookie monitoring and auto-regeneration started for %s",
            self.cookie_file,
        )

    async def stop_monitoring(self) -> None:
        """Stop the background monitoring task."""
        self._stop_event.set()
        tasks = [task for task in (self._reload_task, self._auto_regen_task) if task]
        for task in tasks:
            try:
                await task
            except Exception as exc:  # noqa: BLE001
                logger.error("Error stopping cookie manager task: %s", exc)

        self._reload_task = None
        self._auto_regen_task = None
        self._stop_event = asyncio.Event()
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

    async def regenerate_cookies(self) -> None:
        """Regenerate cookies.txt using yt-dlp."""
        # Disabled browser-based cookie regeneration to hard-decouple from live browser
        logger.info("Cookie regeneration from browser is disabled. Use static cookie file instead.")
        return

    async def _auto_regen_loop(self, interval: int) -> None:
        """Background task to periodically regenerate cookies."""
        interval = max(int(interval), 1)
        while not self._stop_event.is_set():
            await self.regenerate_cookies()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
            else:
                break

    def get_cookie_args(self, use_browser_cookies: bool = False) -> list[str]:
        """
        Get appropriate cookie arguments for yt-dlp.

        Args:
            use_browser_cookies: If True, use browser cookies; if False, use file

        Returns:
            List of cookie-related arguments for yt-dlp command
        """
        if self.cookie_file.exists():
            return ["--cookies", str(self.cookie_file)]

        # Browser cookies disabled to hard-decouple from live browser
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
