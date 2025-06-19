import json
from abc import ABC, abstractmethod
from typing import Optional, Set, TYPE_CHECKING

import trio
from rich.box import ROUNDED
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from model import ClientDataModel
from ui.widgets.views import render_help, render_status, render_map

if TYPE_CHECKING:
    from engine import ClientEngine

LOBBY_IGNORED_COMMANDS: Set[str] = {"NARRATION_END", "THINK_START", "STATE_THINK_START"}


class BaseState(ABC):
    def __init__(self, engine: 'ClientEngine'):
        self.engine = engine
        self.model: "ClientDataModel" = engine.model
        self._nursery: Optional[trio.Nursery] = None
        self._cancel_scope = trio.CancelScope()

    def enter(self, live: Optional[Live] = None):
        """Вызывается при входе в состояние."""
        if self.engine.nursery:
            self.engine.nursery.start_soon(self._run_state_tasks)

    async def _run_state_tasks(self):
        """Внутренний метод для запуска фоновых задач состояния."""
        with self._cancel_scope:
            async with trio.open_nursery() as nursery:
                self._nursery = nursery
                await trio.sleep_forever()

    def exit(self):
        """Вызывается при выходе из состояния."""
        self._cancel_scope.cancel()

    @abstractmethod
    async def handle_message(self, prefix: str, content: str):
        pass

    @abstractmethod
    async def handle_user_input(self, message: str):
        pass


class LoginState(BaseState):
    async def handle_message(self, prefix: str, content: str): pass

    async def handle_user_input(self, message: str): pass


class LobbyState(BaseState):
    def enter(self, live: Optional[Live] = None):
        if live and not live.is_started:
            self.engine.console.clear()
            live.start(refresh=True)

        self.model.lobby_messages.clear()

        if self.model.username:
            self.model.lobby_messages.append(
                Text.from_markup(f"[bold green]Добро пожаловать, {self.model.username}![/] :eye:")
            )
        self.model.lobby_messages.append(
            Text.from_markup("[dim]Ожидайте, пока администратор начнет новую игру.[/dim]")
        )
        super().enter(live)

    async def handle_message(self, prefix: str, content: str):
        if prefix == "LOBBY_UPDATE":
            self.model.players_in_lobby = [name for name in content.strip().split(',') if name]
        elif prefix == "CHAT":
            sender, chat_text = content.split(':', 1)
            style = "bold cyan" if self.model.username and sender.strip() == self.model.username else "magenta"
            self.model.lobby_messages.append(Text.from_markup(f"[{style}]{sender.strip()}[/]: {chat_text.strip()}"))
        elif prefix == "ERROR":
            self.model.lobby_messages.append(Text(f"[ОШИБКА] {content}", style="bold red"))
        elif prefix == "SYSTEM":
            content_str = content.strip()

            if content_str.endswith(" присоединился к игре."):
                player_name = content_str[:-len(" присоединился к игре.")]
                if player_name and player_name not in self.model.players_in_lobby:
                    self.model.players_in_lobby.append(player_name)
            elif content_str.endswith(" покинул игру."):
                player_name = content_str[:-len(" покинул игру.")]
                if player_name and player_name in self.model.players_in_lobby:
                    self.model.players_in_lobby.remove(player_name)

            parts = content_str.split(' ', 1)
            command = parts[0]
            payload = parts[1] if len(parts) > 1 else ""

            if command in LOBBY_IGNORED_COMMANDS:
                return

            if command == "STATE_UPDATE":
                if payload == "ACTIVE":
                    self.engine.change_state(GameState)
                return

            self.model.lobby_messages.append(Text.from_markup(f"[dim yellow]:gear: {content}[/dim yellow]"))

    async def handle_user_input(self, message: str):
        if not message.startswith('/'):
            await self.engine.send_message(message)


class GameState(BaseState):
    def enter(self, live: Optional[Live] = None):
        if live and not live.is_started:
            self.engine.console.clear()
            live.start(refresh=True)

        self.model.game_log.clear()
        self.model.game_log.append(Text.from_markup("[bold green]Игра началась![/bold green]"))
        self.model.game_log.append(
            Text.from_markup("[dim]Введите текст и нажмите Enter для взаимодействия с миром.[/dim]"))
        super().enter(live)

    def exit(self):
        self.model.status_line_content = ""
        super().exit()

    async def handle_user_input(self, message: str):
        self.model.command_output = None
        if message.lower() == '/map':
            await self.engine.send_message('/map')
            return
        if not message.startswith('/'):
            if self.model.username:
                style = "bold cyan"
                self.model.game_log.append(
                    Text.from_markup(f"[{style}]{self.model.username}[/]: {message.strip()}")
                )
        await self.engine.send_message(message)

    async def handle_message(self, prefix: str, content: str):
        import utils

        if prefix in {"NARRATE", "ACTION", "CHAT", "ERROR"}:
            self.model.command_output = None
        self.model.status_line_content = ""

        try:
            if prefix == "STATUS_UPDATE":
                self.model.command_output = render_status(json.loads(content))
                return
            if prefix == "HELP_UPDATE":
                self.model.command_output = render_help()
                return
            if prefix == "MAP_UPDATE":
                self.model.command_output = render_map(json.loads(content))
                return
        except (json.JSONDecodeError, TypeError):
            self.model.command_output = Text("Ошибка отображения данных: неверный формат от сервера.", style="bold red")
            return

        if prefix == "CMD_RESULT":
            clean_content = content.replace('<<BR>>', '\n')
            self.model.command_output = Text.from_markup(f"[dim yellow]{clean_content}[/dim yellow]")
            return

        if prefix == "LOBBY_UPDATE":
            self.model.players_in_lobby = [name for name in content.strip().split(',') if name]
        elif prefix == "SYSTEM":
            content_str = content.strip()
            sub_parts = content_str.split(' ', 1)
            cmd, payload = sub_parts[0], sub_parts[1] if len(sub_parts) > 1 else ""

            if cmd == "STATE_UPDATE" and payload == "LOBBY":
                self.engine.change_state(LobbyState)
                return
            if cmd == "THINK_START":
                self.model.status_line_content = utils.get_random_phrase('phrases')
            elif cmd == "STATE_THINK_START":
                self.model.status_line_content = utils.get_random_phrase('state_phrases')
            elif cmd == "NARRATION_END":
                pass
            else:
                self.model.game_log.append(Text.from_markup(f"[dim yellow]{content}[/dim yellow]"))
        elif prefix == "NARRATE":
            clean_content = content.replace('<<BR>>', '\n')
            last_message = self.model.game_log[-1] if self.model.game_log else None
            if (isinstance(last_message, Panel) and
                    last_message.title == "[bold purple]:scroll: Рассказчик[/]" and
                    isinstance(last_message.renderable, Text)):
                last_message.renderable.append(clean_content)
            else:
                narrator_panel = Panel(
                    Text(clean_content, style="italic cyan"),
                    title="[bold purple]:scroll: Рассказчик[/]", border_style="purple", box=ROUNDED, expand=False
                )
                self.model.game_log.append(narrator_panel)
        elif prefix == "ACTION":
            sender, action_text = content.split(':', 1)
            sender_name = sender.strip()
            if sender_name == self.model.username: return
            self.model.game_log.append(Text.from_markup(f"[magenta]{sender_name}[/]: {action_text.strip()}"))
        elif prefix == "CHAT":
            sender, chat_text = content.split(':', 1)
            sender_name = sender.strip()
            style = "bold cyan" if sender_name == self.model.username else "magenta"
            self.model.game_log.append(
                Text.from_markup(f"[dim](Чат)[/dim] [{style}]{sender_name}[/]: {chat_text.strip()}"))
        elif prefix == "ERROR":
            self.model.game_log.append(Text(f"[ОШИБКА] {content}", style="bold red"))
