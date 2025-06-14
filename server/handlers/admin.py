import json
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
            "/players": self._cmd_players,
            "/kick": self._cmd_kick,
            "/say": self._cmd_say,
            "/help": self._cmd_help,
            "/config": self._cmd_config,
            "/setmodel": self._cmd_setmodel,
            "/setvar": self._cmd_setvar,
            "/setfear": self._cmd_setfear,
        }

        self.lobby_commands = {
            "/start": self._cmd_start,
            **base_commands,
        }

        self.active_commands = {
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
        cmd, args = parts[0].lower(), parts[1:]
        lg.debug(f"Команда разобрана: cmd='{cmd}', args={args}")

        is_active = await self.game_state.is_game_active()
        command_dict = self.active_commands if is_active else self.lobby_commands

        handler = command_dict.get(cmd, self._cmd_unknown)
        await handler(args)

    async def _cmd_help(self, _args: list):
        is_active = await self.game_state.is_game_active()
        state_str = "[bold]ИГРА АКТИВНА[/bold]" if is_active else "[bold]ЛОББИ[/bold]"

        common_help = (
            "  /players                   - Показать список всех игроков.\n"
            "  /kick [имя]                - Исключить игрока.\n"
            "  /say [сообщение]           - Отправить системное сообщение всем.\n"
            "  /help                      - Показать это сообщение.\n"
            "  /config                    - Показать текущие настройки игры и моделей.\n"
            "  /setmodel <narrator|analyzer> [имя_модели]\n"
            "                             - Установить модель для Рассказчика или Анализатора.\n"
            "  /setvar <injection|immersion|history> [число]\n"
            "                             - Установить игровые переменные (story_injection_turns, immersion_turns, max_history_char_length).\n"
            "  /setfear <тип> [вес]       - Установить вес для типа страха (primitive, atmospheric, dissonance, uncertainty).\n"
        )

        if is_active:
            help_text = (
                f"[bold]Состояние: {state_str}[/bold]\n"
                "Доступные команды:\n"
                "  /clear                     - Сбросить игру в состояние лобби.\n"
                "  /stats                     - Показать текущую статистику игры.\n"
                f"{common_help}"
            )
        else:
            help_text = (
                f"[bold]Состояние: {state_str}[/bold]\n"
                "Доступные команды:\n"
                "  /start                     - Начать игру.\n"
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

    async def _cmd_stats(self, _args: list):
        if not await self.game_state.is_game_active():
            console.print("[bold red]Команду /stats можно использовать только во время активной игры.[/bold red]")
            return

        lg.info("Администратор запросил статистику игры.")
        stats = await self.game_state.get_stats()
        console.print(f"[bold yellow]Статистика игры:\n{stats}[/bold yellow]")

    async def _cmd_players(self, _args: list):
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

    async def _cmd_config(self, _args: list):
        """Показывает текущие конфигурационные параметры."""
        lg.info("Администратор запросил текущую конфигурацию.")
        game_config = await self.game_state.get_full_config()
        model_config = await self.server.model_manager.get_models()

        console.print("\n[bold yellow]--- Текущие настройки Игры ---[/bold yellow]")
        console.print(json.dumps(game_config, indent=2, ensure_ascii=False))

        console.print("\n[bold yellow]--- Текущие настройки Моделей ---[/bold yellow]")
        console.print(json.dumps(model_config, indent=2, ensure_ascii=False))

    async def _cmd_setmodel(self, args: list):
        """Устанавливает имя модели: /setmodel <narrator|analyzer> <model_name>"""
        if len(args) != 2 or args[0] not in ['narrator', 'analyzer']:
            console.print("Использование: /setmodel <narrator|analyzer> [имя_модели]", style="bold red")
            return
        model_type, model_name = args[0], args[1]
        if await self.server.model_manager.set_model(model_type, model_name):
            console.print(f"[bold green]Модель '{model_type}' установлена на '{model_name}'.[/bold green]")
        else:
            console.print(f"Не удалось установить модель. Проверьте тип.", style="bold red")

    async def _cmd_setvar(self, args: list):
        """Устанавливает игровые переменные: /setvar <injection|immersion|history> <value>"""
        if len(args) != 2:
            console.print("Использование: /setvar <injection|immersion|history> [число]", style="bold red")
            return
        var_key, value_str = args[0].lower(), args[1]
        var_map = {
            "injection": "story_injection_turns",
            "immersion": "immersion_turns",
            "history": "max_history_char_length"
        }
        if var_key not in var_map:
            console.print(f"Неизвестная переменная '{var_key}'. Доступные: injection, immersion, history.", style="bold red")
            return
        try:
            value = int(value_str)
            if value < 0: raise ValueError
            var_name = var_map[var_key]
            await self.game_state.set_game_variable(var_name, value)
            console.print(f"[bold green]Переменная '{var_name}' установлена на {value}.[/bold green]")
        except ValueError:
            console.print(f"Значение должно быть положительным целым числом.", style="bold red")

    async def _cmd_setfear(self, args: list):
        """Устанавливает вес для типа страха: /setfear <type> <weight>"""
        if len(args) != 2:
            console.print("Использование: /setfear <тип> [вес]", style="bold red")
            return
        fear_type, weight_str = args[0].lower(), args[1]

        current_config = await self.game_state.get_full_config()
        fear_weights = current_config['fear_weights']

        if fear_type not in fear_weights:
            console.print(f"Неизвестный тип страха '{fear_type}'. Доступные: {', '.join(fear_weights.keys())}", style="bold red")
            return
        try:
            weight = int(weight_str)
            if weight < 0: raise ValueError
            fear_weights[fear_type] = weight
            await self.game_state.set_fear_weights(fear_weights)
            console.print(f"[bold green]Вес для '{fear_type}' установлен на {weight}.[/bold green]")
            console.print(f"Новые веса: {fear_weights}")
        except ValueError:
            console.print("Вес должен быть положительным целым числом.", style="bold red")

    async def _cmd_unknown(self, _args: list):
        lg.warning(f"Введена неизвестная или недоступная в текущем состоянии админ-команда.")
        console.print("Неизвестная команда или она недоступна в текущем состоянии игры.", style="bold red")
        await self._cmd_help([])
