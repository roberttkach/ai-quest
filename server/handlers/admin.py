from typing import TYPE_CHECKING, Awaitable, Callable, Dict, List

import trio
from rich.console import Console
from rich.prompt import Prompt

from ..logger import lg
from ..utils import clear_prompt_directory  # Импортируем утилиту

if TYPE_CHECKING:
    from ..app import Server

console = Console()


class AdminConsole:
    """Обрабатывает административные команды из консоли сервера."""

    def __init__(self, server: 'Server'):
        self.server = server
        self.game_state = server.game_state
        self.model_manager = server.model_manager

        base_commands = {
            "/players": self._cmd_players,
            "/kick": self._cmd_kick,
            "/say": self._cmd_say,
            "/help": self._cmd_help,
        }

        self.lobby_commands: Dict[str, Callable[[List[str]], Awaitable[None]]] = {
            "/start": self._cmd_start,
            **base_commands,
        }

        self.active_commands: Dict[str, Callable[[List[str]], Awaitable[None]]] = {
            "/clear": self._cmd_clear,
            "/stats": self._cmd_stats,
            **base_commands,
        }

        lg.info("Админ-консоль инициализирована с контекстно-зависимыми командами.")

    async def run(self):
        """Основной цикл для админ-консоли."""
        lg.info("Админ-консоль запущена и ожидает команды.")
        console.print("[bold green]Админ-консоль запущена. Введите '/help' для списка команд.[/bold green]")
        while True:
            try:
                command_input = await trio.to_thread.run_sync(
                    lambda: Prompt.ask("[bold blue][АДМИН] Введите команду[/bold blue]", default="")
                )
                if command_input:
                    lg.info(f"Администратор ввел команду: '{command_input}'")
                    await self._handle_command(command_input)
            except (EOFError, KeyboardInterrupt):
                lg.info("Получен сигнал завершения (EOF/KeyboardInterrupt), админ-консоль останавливается.")
                console.print("\n[bold yellow]Админ-консоль завершает работу.[/bold yellow]")
                if self.server.nursery:
                    self.server.nursery.cancel_scope.cancel()
                break
            except Exception as e:
                lg.error(f"Ошибка в админ-консоли: {e}", exc_info=True)
                console.print(f"[bold red]Ошибка: {e}[/bold red]")

    async def _handle_command(self, command_str: str):
        """Разбирает и выполняет команду администратора в зависимости от состояния игры."""
        parts = command_str.strip().split()
        if not parts:
            return
        cmd = parts[0].lower()
        args = parts[1:]
        lg.debug(f"Команда разобрана: cmd='{cmd}', args={args}")

        is_active = await self.game_state.is_game_active()
        command_dict = self.active_commands if is_active else self.lobby_commands

        handler = command_dict.get(cmd, self._cmd_unknown)
        await handler(args)

    async def _cmd_help(self, args: list):
        is_active = await self.game_state.is_game_active()

        if is_active:
            help_text = (
                "[bold]Состояние: ИГРА АКТИВНА[/bold]\n"
                "Доступные команды:\n"
                "  /clear                     - Сбросить игру в состояние лобби.\n"
                "  /stats                     - Показать текущую статистику игры.\n"
                "  /players                   - Показать список всех подключенных игроков.\n"
                "  /kick [имя_пользователя]   - Исключить игрока.\n"
                "  /say [сообщение]           - Отправить системное сообщение всем игрокам.\n"
                "  /help                      - Показать это сообщение.\n"
            )
        else:
            help_text = (
                "[bold]Состояние: ЛОББИ[/bold]\n"
                "Доступные команды:\n"
                "  /start                     - Начать игру.\n"
                "  /players                   - Показать список всех подключенных игроков.\n"
                "  /kick [имя_пользователя]   - Исключить игрока.\n"
                "  /say [сообщение]           - Отправить системное сообщение всем игрокам.\n"
                "  /help                      - Показать это сообщение.\n"
            )

        console.print(help_text, style="bold cyan")

    async def _cmd_start(self, args: list):
        if await self.game_state.is_game_active():
            console.print("[bold red]Игра уже запущена. Используйте /clear для сброса.[/bold red]")
            return

        lg.info("Администратор пытается начать игру.")
        await self.game_state.start_game()

        lg.info("Игра успешно начата администратором.")
        console.print("[bold green]Игра началась.[/bold green]")
        await self.server.broadcast_system("STATE_UPDATE ACTIVE")
        await self.server.narrate_initial_room_for_all()

    async def _cmd_clear(self, args: list):
        if not await self.game_state.is_game_active():
            console.print("[bold red]Команду /clear можно использовать только во время активной игры.[/bold red]")
            return

        lg.info("Администратор инициировал сброс игры в лобби.")
        await self.game_state.reset_to_lobby()
        clear_prompt_directory()
        console.print("[bold green]Игра сброшена в лобби. Папка с промптами очищена.[/bold green]")
        await self.server.broadcast_system("Игра была сброшена в лобби администратором.")
        await self.server.broadcast_system("STATE_UPDATE LOBBY")

    async def _cmd_stats(self, args: list):
        if not await self.game_state.is_game_active():
            console.print("[bold red]Команду /stats можно использовать только во время активной игры.[/bold red]")
            return

        lg.info("Администратор запросил статистику игры.")
        stats = await self.game_state.get_stats()
        console.print(f"[bold yellow]Статистика игры:\n{stats}[/bold yellow]")

    async def _cmd_players(self, args: list):
        lg.info("Администратор запросил список игроков.")
        players = await self.game_state.get_connected_usernames()
        console.print(f"Подключенные игроки: [bold yellow]{', '.join(players) or 'Нет'}[/bold yellow]")

    async def _cmd_kick(self, args: list):
        if not args:
            lg.warning("Команда /kick вызвана без имени пользователя.")
            console.print("Использование: /kick [имя_пользователя]", style="bold red")
            return
        username_to_kick = args[0]
        lg.info(f"Администратор пытается исключить игрока '{username_to_kick}'.")
        if await self.server.kick_player(username_to_kick):
            lg.info(f"Игрок '{username_to_kick}' был успешно исключен.")
            console.print(f"[bold green]{username_to_kick} был исключен.[/bold green]")
        else:
            lg.warning(f"Попытка исключить несуществующего игрока '{username_to_kick}'.")
            console.print(f"Игрок '{username_to_kick}' не найден.", style="bold red")

    async def _cmd_say(self, args: list):
        if not args:
            lg.warning("Команда /say вызвана без сообщения.")
            console.print("Использование: /say [сообщение]", style="bold red")
            return
        message = ' '.join(args)
        lg.info(f"Администратор отправляет системное сообщение: '{message}'")
        await self.server.broadcast_system(f"[bold yellow][АДМИН] {message}[/bold yellow]")
        console.print(f"[bold magenta]Отправлено всем: {message}[/bold magenta]")

    async def _cmd_unknown(self, args: list):
        lg.warning(f"Введена неизвестная или недоступная в текущем состоянии админ-команда.")
        console.print("Неизвестная команда или она недоступна в текущем состоянии игры.", style="bold red")
        await self._cmd_help([])
