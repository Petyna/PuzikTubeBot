"""Helper for managing download progress updates."""

import asyncio
from typing import Optional

from aiogram.types import Message
from config import logger, PROGRESS_UPDATE_INTERVAL


class ProgressTracker:
    """Tracks and updates progress for long-running operations."""

    def __init__(self, message: Message, initial_text: str = "⏳ Starting..."):
        self.message = message
        self.current_text = initial_text
        self._last_update_time = 0
        self._update_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Initialize progress tracker with initial message."""
        try:
            self.message = await self.message.answer(self.current_text)
            logger.info("Progress tracker started")
        except Exception as exc:
            logger.error("Failed to start progress tracker: %s", exc)

    async def update(self, text: str, force: bool = False) -> None:
        """
        Update progress message.
        
        Args:
            text: New progress text
            force: If True, update immediately regardless of rate limit
        """
        import time
        
        async with self._lock:
            # Avoid duplicate updates
            if text == self.current_text and not force:
                return
            
            current_time = time.time()
            time_since_last = current_time - self._last_update_time
            
            # Rate limiting - don't update too frequently
            if not force and time_since_last < PROGRESS_UPDATE_INTERVAL:
                return
            
            try:
                await self.message.edit_text(text)
                self.current_text = text
                self._last_update_time = current_time
            except Exception as exc:
                # Silently handle message edit errors (too old, deleted, etc.)
                logger.debug("Progress update failed: %s", exc)

    async def finish(self, final_text: Optional[str] = None) -> None:
        """Finish progress tracking with optional final message."""
        if final_text:
            await self.update(final_text, force=True)
        logger.info("Progress tracker finished")

    async def error(self, error_text: str) -> None:
        """Update with error message."""
        await self.update(f"❌ {error_text}", force=True)


async def send_with_progress(
    message: Message,
    file_method,
    file_path,
    caption: str,
    **kwargs
) -> bool:
    """
    Send file with progress updates for large files.
    
    Args:
        message: Message to reply to
        file_method: Method to call (e.g., message.answer_video)
        file_path: Path to file
        caption: Caption for the file
        **kwargs: Additional arguments for file_method
    
    Returns:
        True if successful, False otherwise
    """
    from pathlib import Path
    from aiogram.types import FSInputFile
    from config import MAX_FILE_SIZE
    from utils import get_file_size
    
    try:
        file_size = get_file_size(Path(file_path))
        
        # Create FSInputFile
        fs_file = FSInputFile(file_path, filename=Path(file_path).name)
        
        # Send file
        await file_method(
            fs_file,
            caption=caption,
            **kwargs
        )
        
        return True
        
    except Exception as exc:
        logger.error("Error sending file %s: %s", file_path, exc)
        return False
