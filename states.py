from aiogram.fsm.state import State, StatesGroup


class DownloadStates(StatesGroup):
    waiting_for_choice = State()
