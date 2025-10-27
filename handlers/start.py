from aiogram import Dispatcher
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import CallbackQuery, Message

from keyboards import create_back_keyboard, create_help_keyboard, create_main_keyboard


async def start_handler(message: Message) -> None:
    guide_text = (
        "📝 **Bot Guide**\n\n"
        "**Supported platforms**\n"
        "• YouTube – videos (quality selection), audio (MP3), playlists (first 10 tracks)\n"
        "• SoundCloud – single tracks and playlists\n"
        "• Instagram – photos, videos, carousels (uses chrome cookies, 1s delay to avoid rate limits)\n"
        "• TikTok – single videos\n"
        "• Twitter/X – single and multi-video posts\n\n"
        "**How to download**\n"
        "1. Send me a supported link directly.\n"
        "2. Wait for the bot to fetch and deliver the media.\n\n"
        "**File limits**\n"
        "• Videos: up to 2GB (large files are compressed when possible).\n"
        "• Audio: up to 50MB per track.\n"
        "• Playlists: first 10 tracks, 50MB per track.\n\n"
        "**Tips & notes**\n"
        "• Keep chrome logged in for Instagram downloads.\n"
        "• Telegram enforces daily upload limits—wait a bit if you hit rate errors.\n"
        "• Just send me a link to start downloading!"
    )
    await message.answer(
        guide_text,
        
    )


async def help_handler(callback: CallbackQuery) -> None:
    help_text = (
        "📝 **Bot Guide**\n\n"
        "**Supported platforms**\n"
        "• YouTube – videos (quality selection), audio (MP3), playlists (first 10 tracks)\n"
        "• SoundCloud – single tracks and playlists\n"
        "• Instagram – photos, videos, carousels (uses chrome cookies, 1s delay to avoid rate limits)\n"
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
        "• Keep chrome logged in for Instagram downloads or switch the browser in settings.\n"
        "• Telegram enforces daily upload limits—wait a bit if you hit rate errors.\n"
        "• Use the ❌ Cancel button to return to the main menu at any time."
    )
    await callback.message.edit_text(
        help_text,
        reply_markup=create_help_keyboard(),
        
    )
async def back_to_start_handler(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "📝 **Bot Guide**\n\n"
        "**Supported platforms**\n"
        "• YouTube – videos (quality selection), audio (MP3), playlists (first 10 tracks)\n"
        "• SoundCloud – single tracks and playlists\n"
        "• Instagram – photos, videos, carousels (uses chrome cookies, 1s delay to avoid rate limits)\n"
        "• TikTok – single videos\n"
        "• Twitter/X – single and multi-video posts\n\n"
        "**How to download**\n"
        "1. Send me a supported link directly.\n"
        "2. Wait for the bot to fetch and deliver the media.\n\n"
        "**File limits**\n"
        "• Videos: up to 2GB (large files are compressed when possible).\n"
        "• Audio: up to 50MB per track.\n"
        "• Playlists: first 10 tracks, 50MB per track.\n\n"
        "**Tips & notes**\n"
        "• Keep chrome logged in for Instagram downloads.\n"
        "• Telegram enforces daily upload limits—wait a bit if you hit rate errors.\n"
        "• Just send me a link to start downloading!",
        
    )
    await callback.answer()


async def close_help_handler(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "📝 **Bot Guide**\n\n"
        "**Supported platforms**\n"
        "• YouTube – videos (quality selection), audio (MP3), playlists (first 10 tracks)\n"
        "• SoundCloud – single tracks and playlists\n"
        "• Instagram – photos, videos, carousels (uses chrome cookies, 1s delay to avoid rate limits)\n"
        "• TikTok – single videos\n"
        "• Twitter/X – single and multi-video posts\n\n"
        "**How to download**\n"
        "1. Send me a supported link directly.\n"
        "2. Wait for the bot to fetch and deliver the media.\n\n"
        "**File limits**\n"
        "• Videos: up to 2GB (large files are compressed when possible).\n"
        "• Audio: up to 50MB per track.\n"
        "• Playlists: first 10 tracks, 50MB per track.\n\n"
        "**Tips & notes**\n"
        "• Keep chrome logged in for Instagram downloads.\n"
        "• Telegram enforces daily upload limits—wait a bit if you hit rate errors.\n"
        "• Just send me a link to start downloading!",
        
    )
    await callback.answer()


def register_start_handlers(dp: Dispatcher) -> None:
    dp.message.register(start_handler, CommandStart())
    dp.callback_query.register(help_handler, lambda c: c.data == "help")
    dp.callback_query.register(
        close_help_handler,
        lambda c: c.data == "close_help",
    )
    dp.callback_query.register(
        back_to_start_handler,
        StateFilter(None),
        lambda c: c.data == "back_to_menu",
    )
