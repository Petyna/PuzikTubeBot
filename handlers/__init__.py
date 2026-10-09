from aiogram import Dispatcher

from .download import register_download_handlers
from .start import register_start_handlers


def register_handlers(dp: Dispatcher) -> None:
    register_start_handlers(dp)
    register_download_handlers(dp)
