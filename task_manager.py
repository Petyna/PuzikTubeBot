"""Task manager for handling concurrent downloads without conflicts."""

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Dict, Optional

from config import logger


@dataclass
class TaskInfo:
    """Information about a running task."""
    task: asyncio.Task
    url: str
    user_id: int
    message_id: int
    created_at: float


class TaskManager:
    """Manages concurrent download tasks to prevent conflicts."""

    def __init__(self):
        self._tasks: Dict[str, TaskInfo] = {}
        self._lock = asyncio.Lock()

    def _generate_task_key(self, user_id: int, message_id: int) -> str:
        """Generate unique key for task tracking."""
        return f"{user_id}:{message_id}"

    async def create_task(
        self,
        user_id: int,
        message_id: int,
        url: str,
        coro: Coroutine[Any, Any, Any],
    ) -> asyncio.Task:
        """
        Create and track a new download task.
        
        Args:
            user_id: Telegram user ID
            message_id: Message ID associated with this task
            url: URL being downloaded
            coro: Coroutine to execute
        
        Returns:
            Created asyncio Task
        """
        import time
        
        async with self._lock:
            task_key = self._generate_task_key(user_id, message_id)
            
            # Cancel existing task with same key if it exists
            if task_key in self._tasks:
                old_task = self._tasks[task_key].task
                if not old_task.done():
                    logger.info("Cancelling existing task for user=%d, msg=%d", user_id, message_id)
                    old_task.cancel()
                    try:
                        await old_task
                    except asyncio.CancelledError:
                        pass

            # Create new task
            task = asyncio.create_task(coro)
            
            task_info = TaskInfo(
                task=task,
                url=url,
                user_id=user_id,
                message_id=message_id,
                created_at=time.time(),
            )
            
            self._tasks[task_key] = task_info
            
            # Add callback to remove task when done
            task.add_done_callback(
                lambda t: asyncio.create_task(self._remove_task(task_key))
            )
            
            logger.info(
                "Created task for user=%d, msg=%d, URL=%s",
                user_id, message_id, url[:50]
            )
            
            return task

    async def _remove_task(self, task_key: str) -> None:
        """Remove completed task from tracking."""
        async with self._lock:
            if task_key in self._tasks:
                task_info = self._tasks[task_key]
                logger.info(
                    "Task completed for user=%d, msg=%d",
                    task_info.user_id, task_info.message_id
                )
                del self._tasks[task_key]

    async def cancel_user_tasks(self, user_id: int) -> int:
        """
        Cancel all tasks for a specific user.
        
        Args:
            user_id: User ID whose tasks to cancel
        
        Returns:
            Number of tasks cancelled
        """
        async with self._lock:
            cancelled_count = 0
            keys_to_remove = []
            
            for task_key, task_info in self._tasks.items():
                if task_info.user_id == user_id:
                    if not task_info.task.done():
                        task_info.task.cancel()
                        cancelled_count += 1
                    keys_to_remove.append(task_key)
            
            for key in keys_to_remove:
                del self._tasks[key]
            
            if cancelled_count > 0:
                logger.info("Cancelled %d tasks for user %d", cancelled_count, user_id)
            
            return cancelled_count

    async def get_active_tasks_count(self, user_id: Optional[int] = None) -> int:
        """
        Get count of active tasks.
        
        Args:
            user_id: If provided, count only tasks for this user
        
        Returns:
            Number of active tasks
        """
        async with self._lock:
            if user_id is None:
                return len([t for t in self._tasks.values() if not t.task.done()])
            
            return len([
                t for t in self._tasks.values()
                if t.user_id == user_id and not t.task.done()
            ])

    async def has_active_task(self, user_id: int, message_id: int) -> bool:
        """Check if a specific task is active."""
        async with self._lock:
            task_key = self._generate_task_key(user_id, message_id)
            if task_key in self._tasks:
                return not self._tasks[task_key].task.done()
            return False

    async def cleanup(self) -> None:
        """Cancel all active tasks."""
        async with self._lock:
            for task_info in self._tasks.values():
                if not task_info.task.done():
                    task_info.task.cancel()
            
            # Wait for all tasks to complete
            await asyncio.gather(*[t.task for t in self._tasks.values()], return_exceptions=True)
            
            self._tasks.clear()
            logger.info("All tasks cleaned up")


# Global task manager instance
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """Get or create the global task manager instance."""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
