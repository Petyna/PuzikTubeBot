import asyncio
import re
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
        update_output = (update_result.stdout or "") + (update_result.stderr or "")
        logger.info("yt-dlp update: %s", update_output.strip())

        current_version = None
        latest_version = None
        current_match = re.search(r"Current version:\s*(\S+)", update_output)
        latest_match = re.search(r"Latest version:\s*(\S+)", update_output)
        if current_match:
            current_version = current_match.group(1)
        if latest_match:
            latest_version = latest_match.group(1)

        needs_pip_upgrade = update_result.returncode != 0
        if not needs_pip_upgrade and current_version and latest_version:
            needs_pip_upgrade = current_version != latest_version

        if needs_pip_upgrade:
            logger.info(
                "Upgrading yt-dlp via pip%s...",
                f" to {latest_version}" if latest_version else "",
            )
            pip_result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                capture_output=True,
                text=True,
                check=False,
            )
            if pip_result.stdout:
                logger.info("pip stdout: %s", pip_result.stdout.strip())
            if pip_result.stderr:
                logger.warning("pip stderr: %s", pip_result.stderr.strip())
            if pip_result.returncode != 0:
                logger.warning("pip upgrade exited with code %s", pip_result.returncode)

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
