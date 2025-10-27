import logging
import os
from pathlib import Path

# Bot token - Replace with your actual token or use environment variable
BOT_TOKEN = os.getenv("BOT_TOKEN", "8387845710:AAEYYfCCzRyEbHBTK-AsMo9CLv9ujSdVUGM")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("PuzikTubeBot")

# File size limits (Telegram limits)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB for regular files
MAX_VIDEO_SIZE = 2000 * 1024 * 1024  # 2GB for videos

# Download directory
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Cookie configuration
COOKIE_FILE = Path("cookies.txt")
COOKIE_MONITOR_INTERVAL = 30  # Check for cookie file updates every 30 seconds

# Cache configuration
CACHE_ENABLED = True
CACHE_TTL = 3600  # Cache download results for 1 hour
CACHE_CLEANUP_INTERVAL = 600  # Clean expired cache every 10 minutes

# Performance settings
MAX_CONCURRENT_DOWNLOADS_PER_USER = 3  # Maximum simultaneous downloads per user
CHUNK_SIZE = 65536  # 64KB chunks for file operations

# Progress update settings
PROGRESS_UPDATE_INTERVAL = 2  # Update progress messages every 2 seconds
