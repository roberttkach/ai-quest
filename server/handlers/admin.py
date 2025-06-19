from typing import Awaitable, Callable, Dict, List, TYPE_CHECKING

import trio
from rich.console import Console
from rich.prompt import Prompt

from logger import lg
from utils import initialize_debug_directories

if TYPE_CHECKING:
    from main import Server


console = Console()


class AdminConsole:
    """Обрабатывает административные команды из консоли сервера."""

    def __init__(self, server: 'Server'):
        self.server = server
        self.game_state = server.game_state
        self.game_engine = server.game_engine

        base_commands: Dict[str, Callable[[List[str]], Awaitable[None]]] = {
            "/say": self._cmd_say,
            "/kick": self._cmd_kick,
            "/help": self._cmd_help,
        }

        self.lobby_commands = {
            "/start": self._cmd_start,
            **base_commands,
        }

        self.active_commands = {
            "/clear": self._cmd_clear,
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
        cmd, args = parts[0].lower(), parts[1:]
        lg.debug(f"Команда разобрана: cmd='{cmd}', args={args}")

        is_active = await self.game_state.is_game_active()
        command_dict = self.active_commands if is_active else self.lobby_commands

        handler = command_dict.get(cmd, self._cmd_unknown)
        await handler(args)

    async def _cmd_say(self, args: list):
        if not args:
            lg.warning("Команда /say вызвана без сообщения.")
            console.print("Использование: /say [сообщение]", style="bold red")
            return
        message = ' '.join(args)
        lg.info(f"Администратор отправляет системное сообщение: '{message}'")
        await self.server.broadcast_system(f"[bold yellow][АДМИН] {message}[/bold yellow]")
        console.print(f"[bold magenta]Отправлено всем: {message}[/bold magenta]")

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

    async def _cmd_clear(self, _args: list):
        if not await self.game_state.is_game_active():
            console.print("[bold red]Команду /clear можно использовать только во время активной игры.[/bold red]")
            return

        lg.info("Администратор инициировал сброс игры в лобби.")
        await self.game_state.reset_to_lobby()
        initialize_debug_directories()
        console.print("[bold green]Игра сброшена в лобби. Папки для отладки очищены.[/bold green]")
        await self.server.broadcast_system("Игра была сброшена в лобби администратором.")
        await self.server.broadcast_system("STATE_UPDATE LOBBY")

    async def _cmd_help(self, _args: list):
        is_active = await self.game_state.is_game_active()
        state_str = "[bold]ИГРА АКТИВНА[/bold]" if is_active else "[bold]ЛОББИ[/bold]"

        common_help = (
            "  /say [сообщение]    - Отправить системное сообщение всем.\n"
            "  /kick [имя]         - Исключить игрока.\n"
            "  /help               - Показать это сообщение.\n"
        )

        if is_active:
            help_text = (
                f"[bold]Состояние: {state_str}[/bold]\n"
                "Доступные команды:\n"
                "  /clear              - Сбросить игру в состояние лобби.\n"
                f"{common_help}"
            )
        else:
            help_text = (
                f"[bold]Состояние: {state_str}[/bold]\n"
                "Доступные команды:\n"
                "  /start              - Начать игру.\n"
                f"{common_help}"
            )

        console.print(help_text, style="bold cyan")

    async def _cmd_start(self, _args: list):
        if await self.game_state.is_game_active():
            console.print("[bold red]Игра уже запущена. Используйте /clear для сброса.[/bold red]")
            return

        lg.info("Администратор пытается начать игру.")
        await self.game_engine.start_game()
        console.print("[bold green]Игра началась.[/bold green]")

    async def _cmd_unknown(self, _args: list):
        lg.warning(f"Введена неизвестная или недоступная в текущем состоянии админ-команда.")
        console.print("Неизвестная команда или она недоступна в текущем состоянии игры.", style="bold red")
        await self._cmd_help([])
