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
