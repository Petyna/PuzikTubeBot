import asyncio
import shutil
from pathlib import Path

from aiogram import Dispatcher, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import logger, MAX_CONCURRENT_DOWNLOADS_PER_USER
from task_manager import get_task_manager
from progress_helper import ProgressTracker
from downloads import (
    download_audio,
    download_playlist_audio,
    download_instagram_media,
    download_soundcloud_playlist,
    download_soundcloud_track,
    download_tiktok_video,
    download_twitter_video,
    download_tiktok_audio,
    download_twitter_audio,
    download_video,
    download_youtube_playlist_videos,
)
from keyboards import create_main_keyboard
from states import DownloadStates
from utils import (
    get_available_video_qualities,
    get_link_service,
    get_soundcloud_resource_info,
    get_youtube_resource_info,
)


# Task manager is now used instead of _active_users


async def continuous_typing_action(message: Message, stop_event: asyncio.Event) -> None:
    """Send typing action every 4 seconds until stop_event is set."""
    while not stop_event.is_set():
        try:
            await message.bot.send_chat_action(
                chat_id=message.chat.id, 
                action="typing"
            )
        except Exception as exc:
            logger.debug("Chat action failed: %s", exc)
        
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            continue
        else:
            break


async def handle_incoming_url(message: Message, state: FSMContext) -> None:
    url = message.text.strip()

    service = get_link_service(url)

    if not service:
        await message.answer(
            "❌ Unsupported link. Send a URL from YouTube, SoundCloud, Instagram, TikTok, or Twitter."
        )
        return

    task_mgr = get_task_manager()
    user_id = message.from_user.id if message.from_user else None
    
    # Check concurrent downloads limit
    if user_id is not None:
        active_count = await task_mgr.get_active_tasks_count(user_id)
        if active_count >= MAX_CONCURRENT_DOWNLOADS_PER_USER:
            await message.answer(
                f"⏳ You have reached the maximum of {MAX_CONCURRENT_DOWNLOADS_PER_USER} concurrent downloads. "
                "Please wait for one to finish before starting another.",
            )
            return

    if service == "soundcloud":
        await state.clear()

        owner_id = user_id or message.chat.id

        async def process_soundcloud() -> None:
            stop_typing = asyncio.Event()
            typing_task = asyncio.create_task(continuous_typing_action(message, stop_typing))
            progress_msg: Message | None = None
            try:
                progress_msg = await message.answer("⏳ Preparing…")

                sc_info = await get_soundcloud_resource_info(url)
                is_playlist = bool(sc_info and sc_info.get("is_playlist"))

                await progress_msg.edit_text("📥 Downloading…")

                if is_playlist:
                    audio_files = await download_soundcloud_playlist(
                        url,
                        message,
                        status_message=progress_msg,
                    )

                    if audio_files:
                        await progress_msg.edit_text("📤 Sending…")
                        sent_count = 0
                        failed_count = 0

                        for audio_path in audio_files:
                            try:
                                await message.answer_audio(
                                    audio=types.FSInputFile(audio_path, filename=audio_path.name),
                                    caption=f"🎵 {audio_path.stem}\n@PuzikTubeBot",
                                )
                                sent_count += 1
                                await asyncio.sleep(1)
                            except Exception as exc:
                                logger.error("Error sending SoundCloud audio %s: %s", audio_path.name, exc)
                                failed_count += 1

                        if audio_files:
                            shutil.rmtree(audio_files[0].parent, ignore_errors=True)

                        summary = "✅ SoundCloud playlist download complete!\n"
                        summary += f"Sent: {sent_count} tracks"
                        if failed_count > 0:
                            summary += f"\nFailed: {failed_count} tracks"

                        await progress_msg.edit_text("✅ Completed!")
                        await message.answer(f"{summary}\n@PuzikTubeBot")
                    else:
                        await progress_msg.edit_text("❌ Failed to download SoundCloud playlist.")
                else:
                    audio_path = await download_soundcloud_track(
                        url,
                        message,
                        status_message=progress_msg,
                    )

                    if audio_path and audio_path.exists():
                        await progress_msg.edit_text("📤 Sending…")
                        try:
                            await message.answer_audio(
                                audio=types.FSInputFile(audio_path, filename=audio_path.name),
                                caption=f"🎵 {audio_path.stem}\n@PuzikTubeBot",
                            )
                            await progress_msg.edit_text("✅ Completed!")
                        except Exception as exc:
                            logger.error("Error sending SoundCloud audio: %s", exc)
                            await message.answer("❌ Error sending audio. File might be corrupted.")
                            await progress_msg.edit_text("❌ Failed to send audio.")
                        finally:
                            shutil.rmtree(audio_path.parent, ignore_errors=True)
                    else:
                        await progress_msg.edit_text("❌ Failed to download SoundCloud audio.")
            except Exception as exc:
                logger.error("SoundCloud auto-download error: %s", exc, exc_info=True)
                if progress_msg:
                    await progress_msg.edit_text("❌ An error occurred while processing the SoundCloud link.")
                else:
                    await message.answer("❌ An error occurred while processing the SoundCloud link.")
            finally:
                stop_typing.set()
                await typing_task

        await task_mgr.create_task(
            owner_id,
            message.message_id,
            url,
            process_soundcloud(),
        )
        return

    # Save link without running yt-dlp
    await state.update_data(
        pending_url=url,
        service=service,
        metadata_cache=None,
    )
    await state.set_state(DownloadStates.waiting_for_choice)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Download Options", callback_data="show_options")]
    ])

    await message.reply(
        "✅ Link saved! Click below to see download options:",
        reply_markup=keyboard
    )


async def show_options_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Show download options after user clicks Download Options button."""
    data = await state.get_data()
    url = data.get("pending_url")
    service = data.get("service")
    
    if not url or not service:
        await callback.message.edit_text("❌ No link found. Please send a new link.")
        await state.clear()
        await callback.answer()
        return
    
    await callback.message.edit_text("⏳ Preparing options...")
    
    # Fetch metadata only once
    metadata_cache = data.get("metadata_cache")
    soundcloud_playlist = None
    youtube_playlist = None
    youtube_playlist_count = None
    qualities = []
    
    if service == "youtube":
        if not metadata_cache:
            yt_info = await get_youtube_resource_info(url)
            youtube_playlist = bool(yt_info and yt_info.get("is_playlist"))
            youtube_playlist_count = yt_info.get("entry_count") if yt_info else None
            
            if not youtube_playlist:
                qualities = await get_available_video_qualities(url)
            
            metadata_cache = {
                "is_playlist": youtube_playlist,
                "entry_count": youtube_playlist_count,
                "qualities": qualities
            }
            await state.update_data(metadata_cache=metadata_cache)
        else:
            youtube_playlist = metadata_cache.get("is_playlist")
            youtube_playlist_count = metadata_cache.get("entry_count")
            qualities = metadata_cache.get("qualities", [])
        
        # Update state with metadata
        await state.update_data(
            qualities=qualities,
            is_youtube_playlist=youtube_playlist,
            youtube_playlist_count=youtube_playlist_count,
        )
        
        if youtube_playlist:
            keyboard = create_main_keyboard(service="youtube", include_playlist=True)
        else:
            keyboard = create_main_keyboard(service="youtube", qualities=qualities, include_playlist=False)
    
    elif service == "soundcloud":
        if not metadata_cache:
            sc_info = await get_soundcloud_resource_info(url)
            soundcloud_playlist = bool(sc_info and sc_info.get("is_playlist"))
            
            metadata_cache = {
                "is_playlist": soundcloud_playlist
            }
            await state.update_data(metadata_cache=metadata_cache)
        else:
            soundcloud_playlist = metadata_cache.get("is_playlist")
        
        await state.update_data(
            is_soundcloud_playlist=soundcloud_playlist,
        )
        keyboard = create_main_keyboard(service="soundcloud", include_playlist=False)
    
    elif service in {"instagram", "tiktok", "twitter"}:
        keyboard = create_main_keyboard(service=service)
    else:
        await callback.message.edit_text("❌ Unsupported service.")
        await state.clear()
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "📥 Choose what you want to download:",
        reply_markup=keyboard
    )
    await callback.answer()


async def back_to_menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "Send me a link to start a download.",
    )
    await callback.answer()


async def _require_pending_data(
    callback: CallbackQuery, state: FSMContext
) -> tuple[str, dict] | None:
    data = await state.get_data()
    url = data.get("pending_url")

    if not url:
        await callback.answer("Send a link first.", show_alert=True)
        return None

    return url, data


async def download_video_handler(callback: CallbackQuery, state: FSMContext) -> None:
    pending = await _require_pending_data(callback, state)
    if not pending:
        return
    url, data = pending
    qualities = data.get("qualities") or []
    service = data.get("service", "youtube")
    is_youtube_playlist = bool(data.get("is_youtube_playlist"))
    youtube_playlist_count = data.get("youtube_playlist_count")
    force_playlist_video = bool(
        callback.data and callback.data.startswith("download_playlist_video")
    )

    await callback.answer()
    message = callback.message

    # Start continuous typing action
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(continuous_typing_action(message, stop_typing))

    try:
        if service == "youtube":
            quality_token = "best"
            if callback.data and ":" in callback.data:
                _, quality_token = callback.data.split(":", maxsplit=1)

            selected_quality: int | None = None
            if quality_token.isdigit():
                selected_quality = int(quality_token)
                if qualities and selected_quality not in qualities:
                    selected_quality = max(qualities)
            elif quality_token == "best" and qualities:
                selected_quality = max(qualities)

            quality_label = (
                f"{selected_quality}p" if selected_quality else "best available"
            )

            if force_playlist_video:
                is_youtube_playlist = True

            if is_youtube_playlist:
                playlist_note = (
                    f" ({youtube_playlist_count} item(s))" if youtube_playlist_count else ""
                )
                await message.edit_text(f"⏳ Preparing playlist download{playlist_note}...")
                await asyncio.sleep(0.5)
                await message.edit_text(
                    f"📥 Downloading playlist videos{playlist_note} ({quality_label})...",
                )
                video_path = await download_youtube_playlist_videos(
                    url,
                    message,
                    selected_quality,
                )
            else:
                await message.edit_text("⏳ Preparing download...")
                await asyncio.sleep(0.5)
                await message.edit_text(
                    f"📥 Downloading video ({quality_label})...",
                )
                video_path = await download_video(url, message, selected_quality)

        else:
            service_map = {
                "instagram": (
                    "📸 Downloading Instagram media...",
                    download_instagram_media,
                ),
                "tiktok": (
                    "🎬 Downloading TikTok video...",
                    download_tiktok_video,
                ),
                "twitter": (
                    "🐦 Downloading Twitter video...",
                    download_twitter_video,
                ),
            }

            if service not in service_map:
                await message.edit_text(
                    "❌ Video downloads are not supported for this service.",
                    
                )
                await state.clear()
                return

            status_text, downloader = service_map[service]
            await message.edit_text("⏳ Preparing download...")
            await asyncio.sleep(0.5)
            await message.edit_text(status_text)
            video_path = await downloader(url, message)

        media_paths: list[Path] = []
        cleanup_dirs: set[Path] = set()

        if isinstance(video_path, list):
            media_paths = [path for path in video_path if path]
        elif video_path:
            media_paths = [video_path]

        if media_paths:
            cleanup_dirs.update(path.parent for path in media_paths)

        photo_exts = {".jpg", ".jpeg", ".png", ".webp"}
        gif_exts = {".gif"}
        video_exts = {".mp4", ".m4v", ".mov", ".webm", ".mkv"}

        if media_paths:
            total = len(media_paths)
            sent_count = 0
            failed_count = 0
            
            await message.edit_text("📤 Sending files...")

            for index, path in enumerate(media_paths, start=1):
                suffix = path.suffix.lower()
                caption = f"✅ {path.stem} ({index}/{total})\n@PuzikTubeBot"

                try:
                    fs_file = types.FSInputFile(path, filename=path.name)

                    if suffix in photo_exts:
                        await message.answer_photo(
                            photo=fs_file,
                            caption=caption,
                        )
                    elif suffix in gif_exts:
                        await message.answer_animation(
                            animation=fs_file,
                            caption=caption,
                        )
                    elif suffix in video_exts:
                        await message.answer_video(
                            video=fs_file,
                            caption=caption,
                            supports_streaming=True,
                        )
                    else:
                        await message.answer(
                            caption,
                        )

                    sent_count += 1
                    if total > 1:
                        await asyncio.sleep(1)
                except Exception as exc:
                    logger.error("Error sending media %s: %s", path.name, exc)
                    failed_count += 1

            if total > 1:
                summary = f"📊 Sent {sent_count}/{total} media item(s)"
                if failed_count:
                    summary += f"\n❌ Failed: {failed_count}"
                summary += "\n@PuzikTubeBot"
                await message.answer(summary)

            await state.clear()

            for directory in cleanup_dirs:
                shutil.rmtree(directory, ignore_errors=True)
        else:
            await message.answer(
                "Failed to download video. This might be due to YouTube restrictions or the video being unavailable.",
            )
            await state.clear()
    
    finally:
        # Stop typing action
        stop_typing.set()
        await typing_task


async def download_audio_handler(callback: CallbackQuery, state: FSMContext) -> None:
    pending = await _require_pending_data(callback, state)
    if not pending:
        return
    url, data = pending
    service = data.get("service", "youtube")

    await callback.answer()
    message = callback.message

    # Start continuous typing action
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(continuous_typing_action(message, stop_typing))

    try:
        await message.edit_text("⏳ Preparing audio download...")
        await asyncio.sleep(0.5)
        await message.edit_text("📥 Downloading audio...")

        if service == "soundcloud":
            is_playlist = data.get("is_soundcloud_playlist")
            if is_playlist:
                audio_files = await download_soundcloud_playlist(url, message)
                if audio_files:
                    sent_count = 0
                    failed_count = 0
                    
                    await message.edit_text("📤 Sending audio files...")

                    for audio_path in audio_files:
                        try:
                            await message.answer_audio(
                                audio=types.FSInputFile(audio_path, filename=audio_path.name),
                                caption=f"🎵 {audio_path.stem}\n@PuzikTubeBot",
                            )
                            sent_count += 1
                            await asyncio.sleep(1)
                        except Exception as exc:
                            logger.error("Error sending audio %s: %s", audio_path.name, exc)
                            failed_count += 1

                    if audio_files:
                        shutil.rmtree(audio_files[0].parent, ignore_errors=True)

                    summary = "✅ SoundCloud playlist download complete!\n"
                    summary += f"Sent: {sent_count} tracks"
                    if failed_count > 0:
                        summary += f"\nFailed: {failed_count} tracks"

                    await message.answer(f"{summary}\n@PuzikTubeBot")
                    await state.clear()
                else:
                    await state.clear()
                return

            track_path = await download_soundcloud_track(url, message)
            audio_path = track_path
        elif service == "youtube":
            audio_path = await download_audio(url, message)
        else:
            await message.edit_text(
                "❌ Audio download is not available for this platform.",
                
            )
            await state.clear()
            return

        if audio_path:
            await message.edit_text("📤 Sending audio...")
            try:
                await message.answer_audio(
                    audio=types.FSInputFile(audio_path, filename=audio_path.name),
                    caption=f"🎵 {audio_path.stem}\n@PuzikTubeBot",
                )

                shutil.rmtree(audio_path.parent, ignore_errors=True)

                await state.clear()
            except Exception as exc:
                logger.error("Error sending audio: %s", exc)
                await message.answer(
                    "❌ Error sending audio. File might be corrupted.",
                )
                shutil.rmtree(audio_path.parent, ignore_errors=True)
                await state.clear()
        else:
            await message.answer(
                "Failed to download audio. This might be due to YouTube restrictions or the video being unavailable.",
            )
            await state.clear()
    
    finally:
        # Stop typing action
        stop_typing.set()
        await typing_task


async def _handle_audio_download(callback: CallbackQuery, state: FSMContext, download_func, service_name: str) -> None:
    """Handle audio download for different services."""
    pending = await _require_pending_data(callback, state)
    if not pending:
        return
    
    url, _ = pending
    message = callback.message
    
    # Start continuous typing action
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(continuous_typing_action(message, stop_typing))
    
    try:
        await message.edit_text("⏳ Preparing download...")
        await asyncio.sleep(0.5)
        await message.edit_text(f"📥 Downloading {service_name} audio...")
        
        # Call the appropriate download function
        audio_path = await download_func(url, message)
        
        if audio_path and audio_path.exists():
            await message.edit_text("📤 Sending audio...")
            try:
                await message.answer_audio(
                    audio=types.FSInputFile(audio_path, filename=audio_path.name),
                    caption=f"🎵 {audio_path.stem}\n@PuzikTubeBot",
                )
                shutil.rmtree(audio_path.parent, ignore_errors=True)
                await state.clear()
            except Exception as exc:
                logger.error("Error sending audio: %s", exc)
                await message.answer("❌ Error sending audio. The file might be too large or corrupted.")
                shutil.rmtree(audio_path.parent, ignore_errors=True)
                await state.clear()
        else:
            await message.answer("❌ Failed to download audio. The content might not be available or accessible.")
            await state.clear()
            
    except Exception as exc:
        logger.error("%s audio download error: %s", service_name, exc, exc_info=True)
        await message.answer(f"❌ An error occurred while downloading {service_name} audio. Please try again later.")
    finally:
        # Stop typing action
        stop_typing.set()
        await typing_task


async def download_tiktok_audio_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle TikTok audio download."""
    await _handle_audio_download(callback, state, download_tiktok_audio, "TikTok")


async def download_twitter_audio_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle Twitter audio download."""
    await _handle_audio_download(callback, state, download_twitter_audio, "Twitter")


async def download_playlist_handler(callback: CallbackQuery, state: FSMContext) -> None:
    pending = await _require_pending_data(callback, state)
    if not pending:
        return
    url, data = pending
    service = data.get("service", "youtube")

    await callback.answer()
    message = callback.message

    # Start continuous typing action
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(continuous_typing_action(message, stop_typing))

    try:
        await message.edit_text("⏳ Preparing playlist download...")
        await asyncio.sleep(0.5)
        await message.edit_text("📥 Downloading playlist...")

        if service == "soundcloud":
            audio_files = await download_soundcloud_playlist(url, message)
        elif service == "youtube":
            audio_files = await download_playlist_audio(url, message)
        else:
            await message.edit_text(
                "❌ Playlist download is not available for this platform.",
                
            )
            await state.clear()
            return
        
        if audio_files:
            sent_count = 0
            failed_count = 0
            
            await message.edit_text("📤 Sending audio files...")

            for audio_path in audio_files:
                try:
                    await message.answer_audio(
                        audio=types.FSInputFile(audio_path, filename=audio_path.name),
                        caption=f"🎵 {audio_path.stem}\n@PuzikTubeBot",
                    )
                    sent_count += 1
                    await asyncio.sleep(1)
                except Exception as exc:
                    logger.error("Error sending audio %s: %s", audio_path.name, exc)
                    failed_count += 1

            if audio_files:
                shutil.rmtree(audio_files[0].parent, ignore_errors=True)

            summary = "✅ Playlist download complete!\n"
            summary += f"Sent: {sent_count} tracks"
            if failed_count > 0:
                summary += f"\nFailed: {failed_count} tracks"

            await message.answer(
                f"{summary}\n@PuzikTubeBot",
            )
            await state.clear()
        else:
            await message.answer(
                "Failed to download playlist. This might be due to YouTube restrictions or unavailable videos.",
            )
            await state.clear()
    
    finally:
        # Stop typing action
        stop_typing.set()
        await typing_task


def register_download_handlers(dp: Dispatcher) -> None:
    dp.callback_query.register(
        show_options_handler,
        DownloadStates.waiting_for_choice,
        F.data == "show_options",
    )
    dp.callback_query.register(
        back_to_menu_handler,
        DownloadStates.waiting_for_choice,
        F.data == "back_to_menu",
    )
    dp.callback_query.register(
        download_video_handler,
        DownloadStates.waiting_for_choice,
        F.data.startswith("download_video"),
    )
    dp.callback_query.register(
        download_video_handler,
        DownloadStates.waiting_for_choice,
        F.data.startswith("download_playlist_video"),
    )
    dp.callback_query.register(
        download_audio_handler,
        DownloadStates.waiting_for_choice,
        F.data == "download_audio",
    )
    dp.callback_query.register(
        download_playlist_handler,
        DownloadStates.waiting_for_choice,
        (F.data == "download_playlist") | (F.data == "download_sc_playlist"),
    )
    dp.callback_query.register(
        download_tiktok_audio_handler,
        DownloadStates.waiting_for_choice,
        F.data == "download_tiktok_audio",
    )
    dp.callback_query.register(
        download_twitter_audio_handler,
        DownloadStates.waiting_for_choice,
        F.data == "download_twitter_audio",
    )

    dp.message.register(
        handle_incoming_url,
        StateFilter(None),
        F.text,
    )
    dp.message.register(
        handle_incoming_url,
        DownloadStates.waiting_for_choice,
        F.text,
    )