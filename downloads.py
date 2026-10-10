import asyncio
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from aiogram.types import Message

from config import DOWNLOAD_DIR, MAX_FILE_SIZE, MAX_VIDEO_SIZE, logger
from utils import get_file_size, run_ytdlp


async def run_gallery_dl(url: str, output_dir: Path) -> tuple[bool, str]:
    """Run gallery-dl command with multiple cookie strategies."""
    
    # Try different cookie strategies
    strategies = [
        {"name": "no_cookies", "args": []},
    ]
    
    last_output = ""
    
    for strat in strategies:
        cmd = [
            "gallery-dl",
            "--dest", str(output_dir),
            "--directory", "",
            "--filename", "{num:>03}_{post_shortcode}.{extension}",
            "--no-part",
        ]
        
        # Add strategy-specific args
        if strat["args"]:
            cmd.extend(strat["args"])
        
        cmd.append(url)
        
        try:
            logger.info("Trying gallery-dl with strategy: %s", strat["name"])
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            output = stdout.decode() + stderr.decode()
            last_output = output
            success = process.returncode == 0
            
            logger.info("gallery-dl (%s) return code: %d", strat["name"], process.returncode)
            if stdout:
                logger.info("gallery-dl STDOUT: %s", stdout.decode())
            if stderr:
                logger.info("gallery-dl STDERR: %s", stderr.decode())
            
            if success:
                return True, output
                
            # If failed, try next strategy
            await asyncio.sleep(0.5)
            
        except Exception as exc:
            logger.error("gallery-dl execution failed: %s", exc)
            last_output = str(exc)
            
    return False, last_output




def _build_format_selectors(max_height: int, enforce_avc: bool) -> tuple[str, str]:
    if enforce_avc:
        format_selector = (
            f"bv*[height<={max_height}][ext=mp4][vcodec^=avc1]+ba[ext=m4a]/"
            f"bv*[height<={max_height}][vcodec^=avc1]+ba/"
            f"bestvideo[height<={max_height}][ext=mp4][vcodec^=avc1]+bestaudio/"
            f"bestvideo[height<={max_height}][vcodec^=avc1]+bestaudio/"
            f"best[height<={max_height}][ext=mp4]/"
            f"best[height<={max_height}]/"
            "best"
        )
        fallback_selector = (
            f"bv*[height<={max_height}][ext=mp4][vcodec^=avc1]+ba/best"
        )
    else:
        format_selector = (
            f"bestvideo[height<={max_height}][ext=mp4]+bestaudio/"
            f"bestvideo[height<={max_height}]+bestaudio/"
            f"best[height<={max_height}][ext=mp4]/"
            f"best[height<={max_height}]/"
            "best"
        )
        fallback_selector = (
            f"bestvideo[height<={max_height}]+bestaudio/best"
        )

    return format_selector, fallback_selector


async def compress_video(input_path: Path, max_size: int) -> Optional[Path]:
    """Compress video with ffmpeg to fit within Telegram size limits."""
    compressed_path = input_path.with_name(f"{input_path.stem}_compressed.mp4")

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        "scale='min(iw,1280)':'min(ih,720)':force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v",
        "libx264",
        "-preset",
        "faster",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(compressed_path),
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error("Video compression failed: %s", stderr.decode("utf-8", "ignore"))
            if compressed_path.exists():
                compressed_path.unlink(missing_ok=True)
            return None

        if get_file_size(compressed_path) <= max_size:
            input_path.unlink(missing_ok=True)
            return compressed_path

        logger.warning(
            "Compressed video still exceeds limit: %s MB",
            get_file_size(compressed_path) // (1024 * 1024),
        )
        compressed_path.unlink(missing_ok=True)
        return None

    except FileNotFoundError:
        logger.error("ffmpeg not found. Install ffmpeg to enable video compression.")
        return None


async def download_video(
    url: str,
    message: Message,
    preferred_quality: int | None = None,
    *,
    enforce_avc: bool = True,
    folder_prefix: str = "video",
    start_message: str | None = None,
    use_cookies: bool = True,
    extra_args: List[str] | None = None,
) -> Optional[Path]:
    """Download video, favoring the specified quality when provided."""
    try:
        download_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = DOWNLOAD_DIR / f"{folder_prefix}_{download_id}"
        temp_dir.mkdir(exist_ok=True)

        status_msg = await message.answer(start_message or "📥 Starting video download...")

        output_template = str(temp_dir / "%(title)s.%(ext)s")
        max_height = preferred_quality or 1080
        format_selector, fallback_selector = _build_format_selectors(max_height, enforce_avc)

        extras = extra_args or []

        command = [
            "yt-dlp",
            "--format",
            format_selector,
            "--merge-output-format",
            "mp4",
            "--output",
            output_template,
            "--no-playlist",
            "--max-filesize",
            f"{MAX_VIDEO_SIZE}",
            "--no-check-certificates",
            "--user-agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "--add-header",
            "Accept-Language:en-US,en;q=0.9",
            "--extractor-retries",
            "3",
            "--fragment-retries",
            "3",
            "--retry-sleep",
            "1",
            "--ignore-errors",
            "--no-warnings",
            "--force-ipv4",
            "--geo-bypass",
        ]

        if use_cookies:
            command.extend([
                "--cookies",
                "cookies.txt",
            ])

        command.extend(extras)
        command.append(url)

        success, output = await run_ytdlp(command)

        if not success:
            await status_msg.edit_text("🔄 Trying alternative download method...")
            command_fallback = [
                "yt-dlp",
                "--format",
                fallback_selector,
                "--merge-output-format",
                "mp4",
                "--output",
                output_template,
                "--no-playlist",
                "--max-filesize",
                f"{MAX_VIDEO_SIZE}",
                "--no-check-certificates",
                "--user-agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "--extractor-retries",
                "5",
                "--ignore-errors",
                "--no-warnings",
                "--force-ipv4",
                "--geo-bypass",
            ]

            if use_cookies:
                command_fallback.extend([
                    "--cookies",
                    "cookies.txt",
                ])

            command_fallback.extend(extras)
            command_fallback.append(url)

            success, output = await run_ytdlp(command_fallback)
            if not success:
                await status_msg.edit_text(f"❌ Download failed: {output[:500]}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

        files = list(temp_dir.glob("*"))
        if not files:
            await status_msg.edit_text("❌ No file was downloaded")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        downloaded_file = files[0]
        file_size = get_file_size(downloaded_file)
        if file_size > MAX_VIDEO_SIZE:
            await status_msg.edit_text(
                "⚙️ Video is too large. Compressing to fit Telegram limits..."
            )

            compressed_path = await compress_video(downloaded_file, MAX_VIDEO_SIZE)

            if not compressed_path:
                await status_msg.edit_text(
                    f"❌ File too large even after compression ({file_size // (1024 * 1024)}MB)."
                )
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

            downloaded_file = compressed_path
            file_size = get_file_size(downloaded_file)

        await status_msg.edit_text(
            f"✅ Download complete! Final size: {file_size // (1024 * 1024)}MB. Sending video(s)..."
        )
        return downloaded_file

    except Exception as exc:  # noqa: BLE001
        logger.error("Video download error: %s", exc)
        return None


async def download_youtube_playlist_videos(
    url: str,
    message: Message,
    preferred_quality: int | None = None,
    *,
    enforce_avc: bool = True,
) -> List[Path]:
    """Download YouTube playlist videos, returning processed file paths."""
    try:
        download_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = DOWNLOAD_DIR / f"yt_playlist_{download_id}"
        temp_dir.mkdir(exist_ok=True)

        status_msg = await message.answer("📥 Starting playlist video download...")

        output_template = str(temp_dir / "%(playlist_index)03d - %(title)s.%(ext)s")
        max_height = preferred_quality or 1080
        format_selector, fallback_selector = _build_format_selectors(max_height, enforce_avc)

        base_command = [
            "yt-dlp",
            "--format",
            format_selector,
            "--merge-output-format",
            "mp4",
            "--output",
            output_template,
            "--yes-playlist",
            "--no-check-certificates",
            "--user-agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "--add-header",
            "Accept-Language:en-US,en;q=0.9",
            "--cookies",
            "cookies.txt",
            "--extractor-retries",
            "3",
            "--fragment-retries",
            "3",
            "--retry-sleep",
            "1",
            "--ignore-errors",
            "--no-warnings",
            "--force-ipv4",
            "--geo-bypass",
            url,
        ]

        success, output = await run_ytdlp(base_command)

        if not success:
            await status_msg.edit_text("🔄 Trying alternative playlist video method...")
            fallback_command = [
                "yt-dlp",
                "--format",
                fallback_selector,
                "--merge-output-format",
                "mp4",
                "--output",
                output_template,
                "--yes-playlist",
                "--no-check-certificates",
                "--user-agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "--add-header",
                "Accept-Language:en-US,en;q=0.9",
                "--cookies",
                "cookies.txt",
                "--extractor-retries",
                "5",
                "--ignore-errors",
                "--no-warnings",
                "--force-ipv4",
                "--geo-bypass",
                url,
            ]

            success, output = await run_ytdlp(fallback_command)
            if not success:
                new_message = f"❌ Download failed: {output[:500]}"
                if new_message != current_message_text:
                    await status_msg.edit_text(new_message)
                shutil.rmtree(temp_dir, ignore_errors=True)
                return []

        files = sorted(
            path
            for path in temp_dir.iterdir()
            if path.is_file() and path.suffix.lower() in supported_extensions
        )
        if not files:
            new_message = "❌ No media files were downloaded"
            if new_message != current_message_text:
                await status_msg.edit_text(new_message)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return []

        processed: List[Path] = []
        for video_path in files:
            file_size = get_file_size(video_path)
            if file_size > MAX_VIDEO_SIZE:
                new_message = f"⚙️ Compressing {video_path.stem} to fit Telegram limits..."
                if new_message != current_message_text:
                    await status_msg.edit_text(new_message)
                    current_message_text = new_message
                compressed = await compress_video(video_path, MAX_VIDEO_SIZE)
                if not compressed:
                    logger.warning(
                        "Skipping %s due to size after compression", video_path.name
                    )
                    continue
                video_path = compressed

            processed.append(video_path)

        if not processed:
            new_message = "❌ No videos are within Telegram limits"
            if new_message != current_message_text:
                await status_msg.edit_text(new_message)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return []

        new_message = f"✅ Downloaded {len(processed)} video(s)! Sending..."
        if new_message != current_message_text:
            await status_msg.edit_text(new_message)
        return processed

    except Exception as exc:  # noqa: BLE001
        logger.error("YouTube playlist video download error: %s", exc)
        return []


async def download_social_media_media(
    url: str,
    message: Message,
    *,
    folder_prefix: str,
    start_message: str,
    cookies_from_browser: str | None = None,
    sleep_interval: float | None = None,
    extra_args: list[str] | None = None,
    strip_query: bool = True,
) -> List[Path]:
    video_extensions = {".mp4", ".m4v", ".mov", ".webm", ".mkv"}
    photo_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    supported_extensions = video_extensions | photo_extensions | {".gif"}

    try:
        target_url = url.split("?")[0] if strip_query else url
        download_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = DOWNLOAD_DIR / f"{folder_prefix}_{download_id}"
        temp_dir.mkdir(exist_ok=True)

        status_msg = await message.answer(start_message)

        output_template = str(temp_dir / "%(playlist_index)03d - %(title)s.%(ext)s")
        format_selector, fallback_selector = _build_format_selectors(1080, enforce_avc=False)

        def build_command(format_string: str, include_cookies: bool) -> list[str]:
            command = [
                "yt-dlp",
                "--format",
                format_string,
                "--merge-output-format",
                "mp4",
                "--output",
                output_template,
                "--yes-playlist",
                "--max-filesize",
                f"{MAX_VIDEO_SIZE}",
                "--no-check-certificates",
                "--user-agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "--add-header",
                "Accept-Language:en-US,en;q=0.9",
                "--extractor-retries",
                "3",
                "--fragment-retries",
                "3",
                "--retry-sleep",
                "1",
                "--ignore-errors",
                "--no-warnings",
                target_url,
            ]

            if include_cookies and cookies_from_browser:
                command.extend([
                    "--cookies-from-browser",
                    cookies_from_browser,
                ])

            if sleep_interval:
                command.extend([
                    "--sleep-interval",
                    str(sleep_interval),
                ])

            if extra_args:
                command.extend(extra_args)

            return command

        attempts: list[tuple[str, str, bool]] = [
            ("primary", format_selector, True),
        ]

        if cookies_from_browser:
            attempts.append(("primary_no_cookies", format_selector, False))

        attempts.append(("fallback", fallback_selector, True))

        if cookies_from_browser:
            attempts.append(("fallback_no_cookies", fallback_selector, False))

        success = False
        output = ""
        current_message_text = start_message  # Track current message content

        for label, selector, include_cookies in attempts:
            if label.startswith("fallback") and not success:
                new_message = "🔄 Trying alternative download method..."
                if new_message != current_message_text:
                    await status_msg.edit_text(new_message)
                    current_message_text = new_message
            elif label.endswith("no_cookies") and cookies_from_browser:
                new_message = "🔄 Retrying without browser cookies..."
                if new_message != current_message_text:
                    await status_msg.edit_text(new_message)
                    current_message_text = new_message

            success, output = await run_ytdlp(build_command(selector, include_cookies))
            if success:
                break

        files = sorted(
            path
            for path in temp_dir.iterdir()
            if path.is_file() and path.suffix.lower() in supported_extensions
        )
        
        # Debug: Log what files are found
        all_files = list(temp_dir.iterdir())
        logger.info(f"Temp dir contents: {[p.name for p in all_files if p.is_file()]}")
        logger.info(f"Supported extensions: {supported_extensions}")
        logger.info(f"Files with supported extensions: {[p.name for p in files]}")
        
        if not files:
            await status_msg.edit_text("❌ No media files were downloaded")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return []

        processed_files: List[Path] = []
        for media_path in files:
            suffix = media_path.suffix.lower()
            if suffix in video_extensions:
                file_size = get_file_size(media_path)
                if file_size > MAX_VIDEO_SIZE:
                    new_message = f"⚙️ Compressing {media_path.stem} to fit Telegram limits..."
                    if new_message != current_message_text:
                        await status_msg.edit_text(new_message)
                        current_message_text = new_message
                    compressed = await compress_video(media_path, MAX_VIDEO_SIZE)
                    if not compressed:
                        await status_msg.edit_text(
                            f"❌ {media_path.stem} is too large even after compression."
                        )
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        return []
                    media_path = compressed

            processed_files.append(media_path)

        new_message = f"✅ Downloaded {len(processed_files)} media item(s)! Sending..."
        if new_message != current_message_text:
            await status_msg.edit_text(new_message)
        return processed_files

    except Exception as exc:  # noqa: BLE001
        logger.error("Social media download error: %s", exc)
        return []




async def download_tiktok_video(url: str, message: Message) -> List[Path]:
    return await download_social_media_media(
        url,
        message,
        folder_prefix="tiktok_video",
        start_message="🎬 Starting TikTok download...",
        cookies_from_browser="chrome",
        sleep_interval=0.5,
        strip_query=False,
    )


async def download_twitter_video(url: str, message: Message) -> List[Path]:
    return await download_social_media_media(
        url,
        message,
        folder_prefix="twitter_video",
        start_message="🐦 Starting Twitter download...",
        sleep_interval=0.5,
        strip_query=False,
    )


async def download_audio(url: str, message: Message) -> Optional[Path]:
    """Download audio as MP3."""
    try:
        download_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = DOWNLOAD_DIR / f"audio_{download_id}"
        temp_dir.mkdir(exist_ok=True)

        status_msg = await message.answer("🎵 Starting audio download...")

        output_template = str(temp_dir / "%(title)s.%(ext)s")
        command = [
            "yt-dlp",
            "--update",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "--embed-thumbnail",
            "--add-metadata",
            "--output",
            output_template,
            "--no-playlist",
            "--no-check-certificates",
            "--user-agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "--add-header",
            "Accept-Language:en-US,en;q=0.9",
            "--cookies",
            "cookies.txt",
            "--extractor-retries",
            "3",
            "--fragment-retries",
            "3",
            "--retry-sleep",
            "1",
            "--ignore-errors",
            "--no-warnings",
            "--force-ipv4",
            "--geo-bypass",
            url,
        ]

        success, output = await run_ytdlp(command)

        if not success:
            await status_msg.edit_text("🔄 Trying simplified download...")
            command_fallback = [
                "yt-dlp",
                "--extract-audio",
                "--audio-format",
                "mp3",
                "--audio-quality",
                "5",
                "--output",
                output_template,
                "--no-playlist",
                "--no-check-certificates",
                "--cookies",
                "cookies.txt",
                "--extractor-retries",
                "5",
                "--ignore-errors",
                "--no-warnings",
                "--force-ipv4",
                "--geo-bypass",
                url,
            ]

            success, output = await run_ytdlp(command_fallback)
            if not success:
                await status_msg.edit_text(f"❌ Download failed: {output[:500]}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

        files = list(temp_dir.glob("*.mp3"))
        if not files:
            await status_msg.edit_text("❌ No audio file was downloaded")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        downloaded_file = files[0]
        file_size = get_file_size(downloaded_file)
        if file_size > MAX_FILE_SIZE:
            await status_msg.edit_text(
                f"❌ File too large ({file_size // (1024 * 1024)}MB). Maximum is 50MB."
            )
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        await status_msg.edit_text("✅ Download complete! Sending audio...")
        return downloaded_file

    except Exception as exc:  # noqa: BLE001
        logger.error("Audio download error: %s", exc)
        return None


def _collect_spotify_audio_files(temp_dir: Path) -> list[Path]:
    """Return flattened list of Spotify mp3 files inside temp_dir."""
    audio_files = sorted(temp_dir.rglob("*.mp3"))
    normalized: list[Path] = []

    for audio_path in audio_files:
        target_path = temp_dir / audio_path.name
        if audio_path.parent != temp_dir:
            candidate = target_path
            counter = 1
            while candidate.exists():
                candidate = temp_dir / f"{audio_path.stem}_{counter}{audio_path.suffix}"
                counter += 1
            audio_path.rename(candidate)
            audio_path = candidate
        normalized.append(audio_path)

    return normalized


async def download_spotify_track(url: str, message: Message) -> Optional[Path]:
    """Download a single Spotify resource (track/episode) as MP3 via yt-dlp."""
    temp_dir: Path | None = None
    status_msg: Message | None = None

    try:
        download_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = DOWNLOAD_DIR / f"spotify_track_{download_id}"
        temp_dir.mkdir(exist_ok=True)

        status_msg = await message.answer("🎧 Starting Spotify download...")

        output_template = str(temp_dir / "%(title)s.%(ext)s")
        
        command = [
            "yt-dlp",
            "--format", "bestaudio/best",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "320K",
            "--output", output_template,
            "--no-warnings",
            url,
        ]

        success, output = await run_ytdlp(command)

        if not success:
            if status_msg:
                await status_msg.edit_text(f"❌ Spotify download failed: {output[:500]}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        files = _collect_spotify_audio_files(temp_dir)
        if not files:
            if status_msg:
                await status_msg.edit_text("❌ No Spotify audio file was downloaded")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        track_path = files[0]
        file_size = get_file_size(track_path)
        if file_size > MAX_FILE_SIZE:
            if status_msg:
                await status_msg.edit_text(
                    f"❌ File too large ({file_size // (1024 * 1024)}MB). Maximum is 50MB."
                )
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        if status_msg:
            await status_msg.edit_text("✅ Spotify audio downloaded! Sending...")
        return track_path

    except Exception as exc:  # noqa: BLE001
        logger.error("Spotify track download error: %s", exc, exc_info=True)
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return None


async def download_spotify_playlist(url: str, message: Message) -> List[Path]:
    """Download Spotify playlist/album/artist/show via yt-dlp."""
    temp_dir: Path | None = None
    status_msg: Message | None = None

    try:
        download_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = DOWNLOAD_DIR / f"spotify_playlist_{download_id}"
        temp_dir.mkdir(exist_ok=True)

        status_msg = await message.answer("📝 Starting Spotify collection download...")

        output_template = str(temp_dir / "%(playlist_index)03d - %(title)s.%(ext)s")
        
        command = [
            "yt-dlp",
            "--format", "bestaudio/best",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "320K",
            "--output", output_template,
            "--no-warnings",
            url,
        ]

        success, output = await run_ytdlp(command)

        if not success:
            if status_msg:
                await status_msg.edit_text(f"❌ Spotify download failed: {output[:500]}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return []

        files = _collect_spotify_audio_files(temp_dir)
        if not files:
            if status_msg:
                await status_msg.edit_text("❌ No Spotify audio files were downloaded")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return []

        valid_files = []
        for audio_path in files:
            file_size = get_file_size(audio_path)
            if file_size <= MAX_FILE_SIZE:
                valid_files.append(audio_path)

        if not valid_files:
            if status_msg:
                await status_msg.edit_text("❌ All Spotify tracks are too large to send")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return []

        if status_msg:
            await status_msg.edit_text(
                f"✅ Downloaded {len(valid_files)} Spotify track(s)! Sending..."
            )
        return valid_files

    except Exception as exc:  # noqa: BLE001
        logger.error("Spotify playlist download error: %s", exc, exc_info=True)
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return []


async def download_playlist_audio(url: str, message: Message) -> List[Path]:
    """Download playlist as MP3 files."""
    try:
        download_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = DOWNLOAD_DIR / f"playlist_{download_id}"
        temp_dir.mkdir(exist_ok=True)

        status_msg = await message.answer("📝 Starting playlist download...")

        output_template = str(temp_dir / "%(playlist_index)s - %(title)s.%(ext)s")
        base_command = [
            "yt-dlp",
            "--ignore-errors",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "5",
            "--embed-thumbnail",
            "--add-metadata",
            "--output",
            output_template,
            "--yes-playlist",
            "--no-check-certificates",
            "--user-agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "--cookies",
            "cookies.txt",
            "--extractor-retries",
            "3",
            "--fragment-retries",
            "3",
            "--retry-sleep",
            "1",
            "--no-overwrites",
            "--no-warnings",
            "--force-ipv4",
            "--geo-bypass",
            url,
        ]

        success, output = await run_ytdlp(base_command)
        if not success:
            await status_msg.edit_text("🔄 Trying simplified playlist download...")
            fallback_command = [
                "yt-dlp",
                "--ignore-errors",
                "--extract-audio",
                "--audio-format",
                "mp3",
                "--audio-quality",
                "5",
                "--output",
                output_template,
                "--yes-playlist",
                "--no-check-certificates",
                "--user-agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "--cookies",
                "cookies.txt",
                "--extractor-retries",
                "5",
                "--no-warnings",
                "--force-ipv4",
                "--geo-bypass",
                url,
            ]

            success, output = await run_ytdlp(fallback_command)
            if not success:
                await status_msg.edit_text(f"❌ Download failed: {output[:500]}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return []

        files = list(temp_dir.glob("*.mp3"))
        if not files:
            await status_msg.edit_text("❌ No audio files were downloaded")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return []

        files.sort(key=lambda item: item.name)

        valid_files = [
            file for file in files if get_file_size(file) <= MAX_FILE_SIZE
        ]

        if valid_files:
            await status_msg.edit_text(
                f"✅ Downloaded {len(valid_files)} tracks! Sending..."
            )
        else:
            await status_msg.edit_text("❌ All files are too large to send")
            shutil.rmtree(temp_dir, ignore_errors=True)

        return valid_files

    except Exception as exc:  # noqa: BLE001
        logger.error("Playlist download error: %s", exc)
        return []


async def download_soundcloud_track(
    url: str,
    message: Message,
    *,
    status_message: Message | None = None,
) -> Optional[Path]:
    """Download a single SoundCloud track as MP3."""
    try:
        download_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = DOWNLOAD_DIR / f"sc_track_{download_id}"
        temp_dir.mkdir(exist_ok=True)

        status_msg = status_message or await message.answer("🎧 Starting SoundCloud track download...")

        output_template = str(temp_dir / "%(title)s.%(ext)s")
        command = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "--embed-thumbnail",
            "--add-metadata",
            "--output",
            output_template,
            "--no-playlist",
            "--cookies",
            "cookies.txt",
            "--no-warnings",
            "--retry-sleep",
            "1",
            "--force-ipv4",
            "--geo-bypass",
            url,
        ]

        success, output = await run_ytdlp(command)
        if not success:
            if status_msg:
                await status_msg.edit_text(f"❌ Download failed: {output[:500]}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        files = list(temp_dir.glob("*.mp3"))
        if not files:
            if status_msg:
                await status_msg.edit_text("❌ No audio file was downloaded")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        track_path = files[0]
        if get_file_size(track_path) > MAX_FILE_SIZE:
            if status_msg:
                await status_msg.edit_text(
                    f"❌ File too large ({get_file_size(track_path) // (1024 * 1024)}MB). Maximum is 50MB."
                )
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        if status_msg:
            await status_msg.edit_text("✅ Track downloaded! Sending...")
        return track_path

    except Exception as exc:  # noqa: BLE001
        logger.error("SoundCloud track download error: %s", exc)
        return None


async def download_soundcloud_playlist(
    url: str,
    message: Message,
    *,
    status_message: Message | None = None,
) -> List[Path]:
    """Download SoundCloud playlist as MP3 tracks."""
    try:
        download_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = DOWNLOAD_DIR / f"sc_playlist_{download_id}"
        temp_dir.mkdir(exist_ok=True)

        status_msg = status_message or await message.answer("📝 Starting SoundCloud playlist download...")

        output_template = str(temp_dir / "%(playlist_index)s - %(title)s.%(ext)s")
        command = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "--embed-thumbnail",
            "--add-metadata",
            "--output",
            output_template,
            "--yes-playlist",
            "--playlist-items",
            "1-20",
            "--cookies",
            "cookies.txt",
            "--no-warnings",
            "--retry-sleep",
            "1",
            "--force-ipv4",
            "--geo-bypass",
            url,
        ]

        success, output = await run_ytdlp(command)
        if not success:
            if status_msg:
                await status_msg.edit_text(f"❌ Download failed: {output[:500]}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return []

        files = list(temp_dir.glob("*.mp3"))
        if not files:
            if status_msg:
                await status_msg.edit_text("❌ No audio files were downloaded")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return []

        files.sort(key=lambda item: item.name)
        valid_files = [file for file in files if get_file_size(file) <= MAX_FILE_SIZE]

        if not valid_files:
            if status_msg:
                await status_msg.edit_text("❌ All tracks are too large to send")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return []

        if status_msg:
            await status_msg.edit_text(
                f"✅ Downloaded {len(valid_files)} tracks! Sending..."
            )
        return valid_files

    except Exception as exc:  # noqa: BLE001
        logger.error("SoundCloud playlist download error: %s", exc)
        return []

async def download_tiktok_audio(url: str, message: Message) -> Optional[Path]:
    """Download TikTok audio as MP3."""
    try:
        download_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = DOWNLOAD_DIR / f"tiktok_audio_{download_id}"
        temp_dir.mkdir(exist_ok=True)

        status_msg = await message.answer("🎵 Starting TikTok audio download...")

        output_template = str(temp_dir / "%(title)s.%(ext)s")
        
        # Try with best audio extraction first
        command = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "--embed-thumbnail",
            "--add-metadata",
            "--output",
            output_template,
            "--no-playlist",
            "--no-check-certificates",
            "--user-agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "--extractor-retries",
            "3",
            "--fragment-retries",
            "3",
            "--retry-sleep",
            "1",
            "--ignore-errors",
            url,
        ]

        success, output = await run_ytdlp(command)

        if not success:
            await status_msg.edit_text("🔄 Trying alternative audio extraction...")
            command_fallback = [
                "yt-dlp",
                "--extract-audio",
                "--audio-format",
                "mp3",
                "--audio-quality",
                "5",
                "--output",
                output_template,
                "--no-playlist",
                "--no-check-certificates",
                "--extractor-retries",
                "5",
                "--ignore-errors",
                url,
            ]

            success, output = await run_ytdlp(command_fallback)
            if not success:
                await status_msg.edit_text(f"❌ Audio download failed: {output[:500]}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

        files = list(temp_dir.glob("*.mp3"))
        if not files:
            await status_msg.edit_text("❌ No audio file was downloaded")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        audio_file = files[0]
        file_size = get_file_size(audio_file)
        if file_size > MAX_FILE_SIZE:
            await status_msg.edit_text(
                f"❌ Audio file too large ({file_size // (1024 * 1024)}MB). Maximum is 50MB."
            )
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        await status_msg.edit_text("✅ Audio download complete! Sending...")
        return audio_file

    except Exception as exc:
        logger.error("TikTok audio download error: %s", exc)
        return None


async def download_twitter_audio(url: str, message: Message) -> Optional[Path]:
    """Download Twitter/X audio as MP3."""
    try:
        download_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = DOWNLOAD_DIR / f"twitter_audio_{download_id}"
        temp_dir.mkdir(exist_ok=True)

        status_msg = await message.answer("🎵 Starting Twitter audio download...")

        output_template = str(temp_dir / "%(title)s.%(ext)s")
        
        # Try with best audio extraction first
        command = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "--embed-thumbnail",
            "--add-metadata",
            "--output",
            output_template,
            "--no-playlist",
            "--no-check-certificates",
            "--user-agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "--extractor-retries",
            "3",
            "--fragment-retries",
            "3",
            "--retry-sleep",
            "1",
            "--ignore-errors",
            url,
        ]

        success, output = await run_ytdlp(command)

        if not success:
            await status_msg.edit_text("🔄 Trying alternative audio extraction...")
            command_fallback = [
                "yt-dlp",
                "--extract-audio",
                "--audio-format",
                "mp3",
                "--audio-quality",
                "5",
                "--output",
                output_template,
                "--no-playlist",
                "--no-check-certificates",
                "--extractor-retries",
                "5",
                "--ignore-errors",
                url,
            ]

            success, output = await run_ytdlp(command_fallback)
            if not success:
                await status_msg.edit_text(f"❌ Audio download failed: {output[:500]}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

        files = list(temp_dir.glob("*.mp3"))
        if not files:
            await status_msg.edit_text("❌ No audio file was downloaded")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        audio_file = files[0]
        file_size = get_file_size(audio_file)
        if file_size > MAX_FILE_SIZE:
            await status_msg.edit_text(
                f"❌ Audio file too large ({file_size // (1024 * 1024)}MB). Maximum is 50MB."
            )
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        await status_msg.edit_text("✅ Audio download complete! Sending...")
        return audio_file

    except Exception as exc:
        logger.error("Twitter audio download error: %s", exc)
        return None