import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from cookie_manager import get_cookie_manager
from config import COOKIE_FILE, YTDLP_PROXY


URL_REGEX = re.compile(r"(https?://[^\s]+)", re.IGNORECASE)


def clean_filename(filename: str) -> str:
    """Clean filename for safe file system usage."""
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200] + ext
    return filename


def get_file_size(filepath: Path) -> int:
    """Get file size in bytes."""
    return filepath.stat().st_size if filepath.exists() else 0


async def run_ytdlp(
    command: list,
    cwd: Path | None = None,
    *,
    _allow_cookie_retry: bool = True,
    use_cookie_file: bool = False,
) -> Tuple[bool, str]:
    """Run a yt-dlp command asynchronously with optional cookie fallback."""
    try:
        command = list(command)
        if (
            command
            and command[0] == "yt-dlp"
            and YTDLP_PROXY
            and "--proxy" not in command
        ):
            command[1:1] = ["--proxy", YTDLP_PROXY]

        raw_command = list(command)
        if command and command[0] == "yt-dlp":
            command = [sys.executable, "-m", "yt_dlp", *command[1:]]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await process.communicate()

        # Debug: Log command and outputs
        from config import logger
        logger.info(f"Running yt-dlp command: {' '.join(command)}")
        logger.info(f"Return code: {process.returncode}")
        if stdout:
            logger.info(f"STDOUT: {stdout.decode('utf-8', errors='replace')[:500]}")
        if stderr:
            logger.info(f"STDERR: {stderr.decode('utf-8', errors='replace')[:500]}")

        if process.returncode == 0:
            return True, stdout.decode("utf-8", errors="replace")

        error_output = stderr.decode("utf-8", errors="replace")

        # Try fallback strategies
        if _allow_cookie_retry:
            # Strategy 1: DPAPI error - retry without browser cookies
            if "--cookies-from-browser" in raw_command and "Failed to decrypt with DPAPI" in error_output:
                logger.warning("DPAPI cookie decryption failed; retrying with cookie file")
                
                # Try with cookie file if available
                cookie_mgr = get_cookie_manager(COOKIE_FILE)
                if await cookie_mgr.is_file_valid():
                    cleaned_command = []
                    skip_next = False
                    for part in raw_command:
                        if skip_next:
                            skip_next = False
                            continue
                        if part == "--cookies-from-browser":
                            skip_next = True
                            continue
                        cleaned_command.append(part)
                    
                    # Add cookie file args
                    cookie_args = cookie_mgr.get_cookie_args(use_browser_cookies=False)
                    cleaned_command.extend(cookie_args)
                    
                    success, retry_output = await run_ytdlp(
                        cleaned_command,
                        cwd=cwd,
                        _allow_cookie_retry=False,
                    )
                    if success:
                        return True, retry_output

        return False, error_output
    except Exception as exc:  # noqa: BLE001
        from config import logger
        logger.error(f"yt-dlp execution error: {exc}")
        return False, str(exc)


def is_youtube_url(url: str) -> bool:
    """Validate if URL is from YouTube."""
    youtube_regex = r"(https?://)?([a-zA-Z0-9-]+\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)/.+"
    return bool(re.match(youtube_regex, url))


def is_soundcloud_url(url: str) -> bool:
    """Validate if URL is from SoundCloud."""
    soundcloud_regex = r"(https?://)?([a-zA-Z0-9-]+\.)?soundcloud\.com/.+"
    return bool(re.match(soundcloud_regex, url))


def is_spotify_url(url: str) -> bool:
    """Validate if URL is from Spotify."""
    spotify_regex = r"(https?://)?open\.spotify\.com/.+"
    return bool(re.match(spotify_regex, url))


def is_instagram_url(url: str) -> bool:
    """Validate if URL is from Instagram."""
    instagram_regex = r"(https?://)?([a-zA-Z0-9-]+\.)?(instagram\.com|instagr\.am)/.+"
    return bool(re.match(instagram_regex, url))


def is_tiktok_url(url: str) -> bool:
    """Validate if URL is from TikTok."""
    tiktok_regex = r"(https?://)?([a-zA-Z0-9-]+\.)?tiktok\.com/.+"
    return bool(re.match(tiktok_regex, url))


def is_twitter_url(url: str) -> bool:
    """Validate if URL is from Twitter/X."""
    twitter_regex = r"(https?://)?([a-zA-Z0-9-]+\.)?(twitter\.com|x\.com)/.+"
    return bool(re.match(twitter_regex, url))


def get_link_service(url: str) -> Optional[str]:
    """Return service identifier for the provided URL."""
    if is_youtube_url(url):
        return "youtube"
    if is_soundcloud_url(url):
        return "soundcloud"
    if is_spotify_url(url):
        return "spotify"
    if is_instagram_url(url):
        return "instagram"
    if is_tiktok_url(url):
        return "tiktok"
    if is_twitter_url(url):
        return "twitter"
    return None


def get_spotify_resource_type(url: str) -> Optional[str]:
    """Return Spotify resource type based on URL path."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        return None

    resource_type = path_parts[0]
    valid_types = {
        "track",
        "playlist",
        "album",
        "artist",
        "show",
        "episode",
    }

    if resource_type == "embed" and len(path_parts) > 1:
        resource_type = path_parts[1]

    return resource_type if resource_type in valid_types else None


def extract_first_url(text: str) -> Optional[str]:
    """Extract the first URL-like substring from arbitrary text."""
    if not text:
        return None

    match = URL_REGEX.search(text)
    if not match:
        return None

    url = match.group(1)
    trailing_chars = ".,!?:;)\"'[]"
    return url.rstrip(trailing_chars)


async def get_available_video_qualities(url: str) -> List[int]:
    """Return list of available AVC heights (e.g., 1080, 720) for the given video."""
    base = [
        "yt-dlp",
        "--skip-download",
        "--no-warnings",
        "--dump-json",
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
        "--force-ipv4",
        "--geo-bypass",
    ]

    with_cookies = base + ["--cookies", "cookies.txt", url]
    without_cookies = base + [url]

    success, output = await run_ytdlp(with_cookies)
    if not success or not output:
        success, output = await run_ytdlp(without_cookies)
    if not success or not output:
        return []

    json_lines = [line for line in output.splitlines() if line.strip()]
    if not json_lines:
        return []

    try:
        info = json.loads(json_lines[-1])
    except json.JSONDecodeError:
        return []

    heights: set[int] = set()
    for fmt in info.get("formats", []):
        height = fmt.get("height")
        vcodec = fmt.get("vcodec") or ""

        if not height or vcodec == "none":
            continue

        if "avc1" in vcodec:
            if height >= 1080:
                heights.add(1080)
            elif height >= 720:
                heights.add(720)

    return sorted(heights, reverse=True)


async def get_youtube_resource_info(url: str) -> Dict[str, Any] | None:
    """Return metadata describing whether a YouTube URL is a single video or playlist."""
    base = [
        "yt-dlp",
        "--skip-download",
        "--no-warnings",
        "--dump-single-json",
        "--flat-playlist",
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
        "--force-ipv4",
        "--geo-bypass",
    ]

    with_cookies = base + ["--cookies", "cookies.txt", url]
    without_cookies = base + [url]

    success, output = await run_ytdlp(with_cookies)
    if not success or not output:
        success, output = await run_ytdlp(without_cookies)
    if not success or not output:
        return None

    try:
        info = json.loads(output)
    except json.JSONDecodeError:
        return None

    entries = info.get("entries") or []
    is_playlist = bool(entries) or info.get("_type") == "playlist"
    entry_count = len(entries)

    return {
        "is_playlist": is_playlist,
        "entry_count": entry_count if is_playlist else (1 if info else 0),
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
    }


async def get_soundcloud_resource_info(url: str) -> Dict[str, Any] | None:
    """Return metadata describing whether SoundCloud URL is track or playlist."""
    command = [
        "yt-dlp",
        "--skip-download",
        "--no-warnings",
        "--dump-single-json",
        url,
    ]

    success, output = await run_ytdlp(command)
    if not success or not output:
        return None

    try:
        info = json.loads(output)
    except json.JSONDecodeError:
        return None

    is_playlist = bool(info.get("entries")) or info.get("_type") == "playlist"
    entry_count = len(info.get("entries", []) or [])

    return {
        "is_playlist": is_playlist,
        "entry_count": entry_count,
        "title": info.get("title"),
        "uploader": info.get("uploader"),
    }
