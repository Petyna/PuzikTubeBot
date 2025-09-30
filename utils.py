import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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


async def run_ytdlp(command: list, cwd: Path | None = None) -> Tuple[bool, str]:
    """Run a yt-dlp command asynchronously."""
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            return True, stdout.decode("utf-8")
        return False, stderr.decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def is_youtube_url(url: str) -> bool:
    """Validate if URL is from YouTube."""
    youtube_regex = r"(https?://)?(www\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)/.+"
    return bool(re.match(youtube_regex, url))


def is_soundcloud_url(url: str) -> bool:
    """Validate if URL is from SoundCloud."""
    soundcloud_regex = r"(https?://)?(www\.)?soundcloud\.com/.+"
    return bool(re.match(soundcloud_regex, url))


def is_instagram_url(url: str) -> bool:
    """Validate if URL is from Instagram."""
    instagram_regex = r"(https?://)?(www\.)?(instagram\.com|instagr\.am)/.+"
    return bool(re.match(instagram_regex, url))


def is_tiktok_url(url: str) -> bool:
    """Validate if URL is from TikTok."""
    tiktok_regex = r"(https?://)?(www\.)?tiktok\.com/.+"
    return bool(re.match(tiktok_regex, url))


def is_twitter_url(url: str) -> bool:
    """Validate if URL is from Twitter/X."""
    twitter_regex = r"(https?://)?(www\.)?(twitter\.com|x\.com)/.+"
    return bool(re.match(twitter_regex, url))


def get_link_service(url: str) -> Optional[str]:
    """Return service identifier for the provided URL."""
    if is_youtube_url(url):
        return "youtube"
    if is_soundcloud_url(url):
        return "soundcloud"
    if is_instagram_url(url):
        return "instagram"
    if is_tiktok_url(url):
        return "tiktok"
    if is_twitter_url(url):
        return "twitter"
    return None


async def get_available_video_qualities(url: str) -> List[int]:
    """Return list of available AVC heights (e.g., 1080, 720) for the given video."""
    command = [
        "yt-dlp",
        "--skip-download",
        "--no-warnings",
        "--dump-json",
        url,
    ]

    success, output = await run_ytdlp(command)
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
    command = [
        "yt-dlp",
        "--skip-download",
        "--no-warnings",
        "--dump-single-json",
        "--flat-playlist",
        url,
    ]

    success, output = await run_ytdlp(command)
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
