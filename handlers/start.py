from aiogram import Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from keyboards import create_back_keyboard, create_help_keyboard, create_main_keyboard


async def start_handler(message: Message) -> None:
    welcome_text = (
        "🎬 **YouTube Downloader Bot**\n\n"
        "Welcome! I can help you download videos and audio from YouTube.\n\n"
        "Choose an option from the menu below:"
    )
    await message.answer(
        welcome_text,
        reply_markup=create_main_keyboard(),
        parse_mode="Markdown",
    )


async def help_handler(callback: CallbackQuery) -> None:
    help_text = (
        "📝 **Bot Guide**\n\n"
        "**Supported platforms**\n"
        "• YouTube – videos (quality selection), audio (MP3), playlists (first 10 tracks)\n"
        "• SoundCloud – single tracks and playlists\n"
        "• Instagram – photos, videos, carousels (uses Chrome cookies, 1s delay to avoid rate limits)\n"
        "• TikTok – single videos\n"
        "• Twitter/X – single and multi-video posts\n\n"
        "**How to download**\n"
        "1. Pick an option from the main menu or send a supported link directly.\n"
        "2. Paste the URL when asked.\n"
        "3. Wait for the bot to fetch and deliver the media. Multi-item posts arrive in media groups (max 10 per message).\n\n"
        "**File limits**\n"
        "• Videos: up to 2GB (large files are compressed when possible).\n"
        "• Audio: up to 50MB per track.\n"
        "• Playlists: first 10 tracks, 50MB per track.\n\n"
        "**Tips & notes**\n"
        "• Keep Chrome logged in for Instagram downloads or switch the browser in settings.\n"
        "• Telegram enforces daily upload limits—wait a bit if you hit rate errors.\n"
        "• Use the ❌ Cancel button to return to the main menu at any time."
    )
    await callback.message.edit_text(
        help_text,
        reply_markup=create_help_keyboard(),
        parse_mode="Markdown",
    )
    await callback.answer()


def register_start_handlers(dp: Dispatcher) -> None:
    dp.message.register(start_handler, CommandStart())
    dp.callback_query.register(help_handler, lambda c: c.data == "help")
    dp.callback_query.register(
        close_help_handler,
        lambda c: c.data == "close_help",
    )


async def close_help_handler(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🎬 **YouTube Downloader Bot**\n\nChoose an option from the menu below:",
        reply_markup=create_main_keyboard(),
        parse_mode="Markdown",
    )
    await callback.answer()
