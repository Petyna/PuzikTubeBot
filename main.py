import asyncio
import shutil
import subprocess

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, DOWNLOAD_DIR, logger
from handlers import register_handlers


def ensure_yt_dlp() -> None:
    try:
        logger.info("Updating yt-dlp...")
        update_result = subprocess.run(
            ["yt-dlp", "--update"], capture_output=True, text=True, check=False
        )
        logger.info("yt-dlp update: %s", update_result.stdout.strip())

        version_result = subprocess.run(
            ["yt-dlp", "--version"], capture_output=True, text=True, check=False
        )
        logger.info("yt-dlp version: %s", version_result.stdout.strip())
    except FileNotFoundError as exc:
        logger.error("yt-dlp not found! Please install it: pip install yt-dlp")
        raise SystemExit(1) from exc


async def run_bot() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    register_handlers(dp)

    logger.info("Bot starting...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        shutil.rmtree(DOWNLOAD_DIR, ignore_errors=True)


async def main() -> None:
    ensure_yt_dlp()
    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
