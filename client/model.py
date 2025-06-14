from collections import deque
from typing import Optional, List, Type

from rich.console import RenderableType

import states


class ClientDataModel:
    """
    Единый источник истины для всего UI клиента.
    Хранит все данные, необходимые для рендеринга, и текущее состояние приложения.
    """

    def __init__(self):
        self.current_state_class: Type[states.BaseState] = states.LoginState
        self.is_connected: bool = False
        self.username: Optional[str] = None
        self.players_in_lobby: List[str] = []
        self.lobby_messages: deque = deque(maxlen=100)
        self.game_log: List[RenderableType] = []
        self.input_buffer: str = ""
        self.status_line_content: str = ""
        self.scroll_offset: int = 0
        self.command_output: Optional[RenderableType] = None

    @property
    def state_name(self) -> str:
        """Возвращает имя текущего состояния для LayoutManager."""
        return self.current_state_class.__name__

    def set_lobby_message_capacity(self, new_capacity: int):
        """Изменяет вместимость очереди сообщений лобби."""
        if 0 < new_capacity != self.lobby_messages.maxlen:
            current_messages = list(self.lobby_messages)
            self.lobby_messages = deque(current_messages, maxlen=new_capacity)
