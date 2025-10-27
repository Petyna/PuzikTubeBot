import asyncio
import shutil
import subprocess
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import (
    BOT_TOKEN,
    CACHE_CLEANUP_INTERVAL,
    CACHE_ENABLED,
    CACHE_TTL,
    COOKIE_FILE,
    COOKIE_MONITOR_INTERVAL,
    DOWNLOAD_DIR,
    logger,
)
from cache_manager import get_cache_manager
from cookie_manager import get_cookie_manager
from task_manager import get_task_manager
from handlers import register_handlers


def ensure_yt_dlp() -> None:
    try:
        logger.info("Updating yt-dlp...")
        update_result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--update"],
            capture_output=True,
            text=True,
            check=False,
        )
        logger.info("yt-dlp update: %s", update_result.stdout.strip())

        version_result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        logger.info("yt-dlp version: %s", version_result.stdout.strip())
    except FileNotFoundError as exc:
        logger.error("yt-dlp not found! Please install it: pip install yt-dlp")
        raise SystemExit(1) from exc


async def run_bot() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Initialize managers
    cookie_mgr = get_cookie_manager(COOKIE_FILE)
    cache_mgr = get_cache_manager(CACHE_TTL) if CACHE_ENABLED else None
    task_mgr = get_task_manager()

    # Start cookie monitoring
    await cookie_mgr.start_monitoring(COOKIE_MONITOR_INTERVAL)
    logger.info("Cookie manager initialized")

    # Start cache cleanup if enabled
    if cache_mgr:
        await cache_mgr.start_cleanup(CACHE_CLEANUP_INTERVAL)
        logger.info("Cache manager initialized")

    register_handlers(dp)

    logger.info("Bot starting...")
    try:
        await dp.start_polling(bot)
    finally:
        # Cleanup
        await cookie_mgr.stop_monitoring()
        if cache_mgr:
            await cache_mgr.stop_cleanup()
        await task_mgr.cleanup()
        await bot.session.close()
        shutil.rmtree(DOWNLOAD_DIR, ignore_errors=True)
        logger.info("Bot stopped and cleaned up")


async def main() -> None:
    ensure_yt_dlp()
    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
