import sys
import random
from typing import Optional, List

import trio
from rich.console import Console, Group
from rich.status import Status
from rich.text import Text
from rich.live import Live
from rich.table import Table
from rich.align import Align
from rich.rule import Rule
from rich.panel import Panel

from .logger import lg

DEFAULT_PORT = 65432

console = Console()

WELCOME_ART = """
 
 
 

 █     █░▓█████  ██▓     ▄████▄   ▒█████   ███▄ ▄███▓▓█████ 
▓█░ █ ░█░▓█   ▀ ▓██▒    ▒██▀ ▀█  ▒██▒  ██▒▓██▒▀█▀ ██▒▓█   ▀ 
▒█░ █ ░█ ▒███   ▒██░    ▒▓█    ▄ ▒██░  ██▒▓██    ▓██░▒███   
░█░ █ ░█ ▒▓█  ▄ ▒██░    ▒▓▓▄ ▄██▒▒██   ██░▒██    ▒██ ▒▓█  ▄ 
░░██▒██▓ ░▒████▒░██████▒▒ ▓███▀ ░░ ████▓▒░▒██▒   ░██▒░▒████▒
░ ▓░▒ ▒  ░░ ▒░ ░░ ▒░▓  ░░ ░▒ ▒  ░░ ▒░▒░▒░ ░ ▒░   ░  ░░░ ▒░ ░
  ▒ ░ ░   ░ ░  ░░ ░ ▒  ░  ░  ▒     ░ ▒ ▒░ ░  ░      ░ ░ ░  ░
  ░   ░     ░     ░ ░   ░        ░ ░ ░ ▒  ░      ░      ░   
    ░       ░  ░    ░  ░░ ░          ░ ░         ░      ░  ░
                        ░                                   
▄▄▄█████▓ ▒█████     ▄▄▄█████▓ ██░ ██ ▓█████                
▓  ██▒ ▓▒▒██▒  ██▒   ▓  ██▒ ▓▒▓██░ ██▒▓█   ▀                
▒ ▓██░ ▒░▒██░  ██▒   ▒ ▓██░ ▒░▒██▀▀██░▒███                  
░ ▓██▓ ░ ▒██   ██░   ░ ▓██▓ ░ ░▓█ ░██ ▒▓█  ▄                
  ▒██▒ ░ ░ ████▓▒░     ▒██▒ ░ ░▓█▒░██▓░▒████▒               
  ▒ ░░   ░ ▒░▒░▒░      ▒ ░░    ▒ ░░▒░▒░░ ▒░ ░               
    ░      ░ ▒ ▒░        ░     ▒ ░▒░ ░ ░ ░  ░               
  ░      ░ ░ ░ ▒       ░       ░  ░░ ░   ░                  
             ░ ░               ░  ░  ░   ░  ░               
                                                            
 ▄▄▄       ██▓     █████   █    ██ ▓█████   ██████ ▄▄▄█████▓
▒████▄    ▓██▒   ▒██▓  ██▒ ██  ▓██▒▓█   ▀ ▒██    ▒ ▓  ██▒ ▓▒
▒██  ▀█▄  ▒██▒   ▒██▒  ██░▓██  ▒██░▒███   ░ ▓██▄   ▒ ▓██░ ▒░
░██▄▄▄▄██ ░██░   ░██  █▀ ░▓▓█  ░██░▒▓█  ▄   ▒   ██▒░ ▓██▓ ░ 
 ▓█   ▓██▒░██░   ░▒███▒█▄ ▒▒█████▓ ░▒████▒▒██████▒▒  ▒██▒ ░ 
 ▒▒   ▓▒█░░▓     ░░ ▒▒░ ▒ ░▒▓▒ ▒ ▒ ░░ ▒░ ░▒ ▒▓▒ ▒ ░  ▒ ░░   
  ▒   ▒▒ ░ ▒ ░    ░ ▒░  ░ ░░▒░ ░ ░  ░ ░  ░░ ░▒  ░ ░    ░    
  ░   ▒    ▒ ░      ░   ░  ░░░ ░ ░    ░   ░  ░  ░    ░      
      ░  ░ ░         ░       ░        ░  ░      ░           
                                                            

 
"""


def create_welcome_message(username: str) -> Group:
    """Создает красивое приветственное сообщение с ASCII-артом в стиле хоррор."""

    letter_palette = [
        "#b0b0b0",
        "#a3a3a3",
        "#969696",
        "#8a8a8a"
    ]

    drip_palette = [
        "#B22222",
        "#8B0000",
        "#8A0707",
        "#58111A"
    ]

    colored_art_lines = []
    for line in WELCOME_ART.strip('\n').split('\n'):
        text_line = Text()
        for char in line:
            if char in ['▀', '▄', '█', '▓']:
                style = random.choice(letter_palette)
                text_line.append(char, style=style)
            elif char in ['░', '▒']:
                style = random.choice(drip_palette)
                text_line.append(char, style=style)
            else:
                text_line.append(char)
        colored_art_lines.append(text_line)

    welcome_text = Text.from_markup(f"Добро пожаловать, [bold red]{username}[/bold red]! :eye:")

    return Group(
        Align.center(Group(*colored_art_lines)),
        Align.center(Rule(style="dim red")),
        Align.center(welcome_text)
    )


async def get_user_input(prompt: str | Text, default: str = "") -> str:
    def _blocking_input():
        sys.stdout.flush()
        return sys.stdin.readline()

    console.print(prompt, end="")
    line = await trio.to_thread.run_sync(_blocking_input)

    sys.stdout.write('\x1b[1A\x1b[K')
    sys.stdout.flush()

    user_input = line.strip() or default
    lg.debug(f"Получен ввод от пользователя: '{user_input}'")
    return user_input


async def get_valid_ip() -> str:
    while True:
        ip = await get_user_input(Text("Введите IP-адрес сервера [127.0.0.1]: ", style="bold blue"), "127.0.0.1")
        parts = ip.split(".")
        if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
            lg.info(f"Введен корректный IP-адрес: {ip}")
            return ip
        lg.warning(f"Пользователь ввел неверный IP-адрес: '{ip}'")
        console.print("[bold red]Неверный формат IP-адреса. Пожалуйста, попробуйте снова.[/bold red]")


async def get_valid_port() -> int:
    while True:
        port_str = await get_user_input(Text(f"Введите порт сервера [{DEFAULT_PORT}]: ", style="bold blue"),
                                        str(DEFAULT_PORT))
        if port_str.isdigit() and 0 < (port := int(port_str)) < 65536:
            lg.info(f"Введен корректный порт: {port}")
            return port
        lg.warning(f"Пользователь ввел неверный порт: '{port_str}'")
        console.print("[bold red]Неверный порт. Введите число от 1 до 65535.[/bold red]")


async def confirm_exit() -> bool:
    while True:
        response = await get_user_input("[bold yellow]Вы уверены, что хотите выйти? (y/n)[/bold yellow]: ")
        if response.lower() in ['y', 'yes', 'д', 'да']:
            return True
        if response.lower() in ['n', 'no', 'н', 'нет']:
            return False
        console.print("[bold red]Пожалуйста, введите 'y' или 'n'.[/bold red]")


class ChatClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.stream: Optional[trio.SocketStream] = None
        self.username: Optional[str] = None
        self._stop_event = trio.Event()
        self._is_closing = False
        self._buffer = ""
        self._narration_buffer = ""
        self._status: Optional[Status] = None
        self.game_state: str = "LOBBY"
        self._can_input_event = trio.Event()
        self._lobby_live: Optional[Live] = None
        self._narration_live: Optional[Live] = None
        self.lobby_players: List[str] = []
        self.phrases = [
            "Подбираю слова...", "Секунду, осматриваюсь...", "Что-то изменилось...", "Сгущается тишина...",
            "Детали проступают из тени...", "Заглядываю за занавес...", "Тени сместились...",
            "Время замедлило ход...", "Здесь что-то не так...", "Напряжение нарастает...", "Повеяло холодом...",
            "Одно мгновение...", "Что-то пробудилось...", "Ищу верную ноту...", "Занавес дрогнул...",
        ]
        lg.info(f"Клиент инициализирован для подключения к {host}:{port}")

    def _stop_status(self):
        if self._status:
            self._status.stop()
            self._status = None

    def _stop_lobby_live(self):
        if self._lobby_live:
            self._lobby_live.stop()
            self._lobby_live = None
            self.lobby_players = []

    def _stop_narration_live(self):
        if self._narration_live:
            self._narration_live.stop()
            self._narration_live = None
            self._narration_buffer = ""

    def _update_lobby_display(self):
        table = Table.grid(padding=(0, 2))
        table.add_column(justify="right", style="dim")
        table.add_column(justify="left")

        for i, player in enumerate(sorted(self.lobby_players), 1):
            style = "bold cyan" if player == self.username else "white"
            table.add_row(f"{i}.", Text(player, style=style))

        display_group = Group(
            Rule(f"[bold green]:busts_in_silhouette: Лобби [dim]({len(self.lobby_players)} иг.)[/dim]"),
            Align.center(table),
            Align.center(Text("Ожидание начала игры...", style="italic yellow"))
        )

        if not self._lobby_live:
            self._lobby_live = Live(display_group, console=console, auto_refresh=False, vertical_overflow="visible")
            self._lobby_live.start(refresh=True)
        else:
            self._lobby_live.update(display_group, refresh=True)

    async def _read_message(self) -> Optional[str]:
        if not self.stream: return None
        while '\n' not in self._buffer:
            try:
                data = await self.stream.receive_some(4096)
                if not data:
                    lg.warning("Соединение закрыто сервером при чтении (получены пустые данные).")
                    return None
                decoded_data = data.decode('utf-8', errors='ignore')
                self._buffer += decoded_data
            except (trio.BrokenResourceError, trio.ClosedResourceError) as e:
                lg.error(f"Ошибка сокета при чтении сообщения: {e}")
                return None
        message, _, self._buffer = self._buffer.partition('\n')
        return message

    async def _login_sequence(self) -> bool:
        lg.info("Начало последовательности входа.")
        prompt_message = await self._read_message()
        if prompt_message is None: return False

        parts = prompt_message.split(' ', 1)
        prefix, content = parts[0], parts[1] if len(parts) > 1 else "Введите ваше имя: "

        username_to_send = ""
        if prefix == "PROMPT":
            while not username_to_send:
                prompt_text = Text(content, style="bold blue")
                username_to_send = await get_user_input(prompt_text)
        else:
            await self._parse_and_display_message(prompt_message)
            return False

        if not self.stream: return False
        await self.stream.send_all(f"{username_to_send}\n".encode('utf-8'))

        response = await self._read_message()
        if response is None: return False

        await self._parse_and_display_message(response)
        return bool(self.username)

    async def run(self):
        try:
            with trio.move_on_after(10):
                self.stream = await trio.open_tcp_stream(self.host, self.port)
            if not self.stream:
                console.print(f"[bold red]Не удалось подключиться: Таймаут подключения[/bold red]")
                return
            if not await self._login_sequence():
                return
            async with trio.open_nursery() as nursery:
                nursery.start_soon(self.receive_messages)
                nursery.start_soon(self.handle_user_input)
                await self._stop_event.wait()
                nursery.cancel_scope.cancel()
        except Exception as e:
            if not isinstance(e, trio.Cancelled):
                console.print(f"[bold red]Произошла непредвиденная ошибка: {e}[/bold red]")
        finally:
            await self.close_connection()

    async def handle_user_input(self):
        while not self._stop_event.is_set():
            try:
                await self._can_input_event.wait()
                prompt = Text("")
                message = await get_user_input(prompt)
                message = message.strip()
                if not message:
                    self._can_input_event.set()
                    continue
                self._can_input_event = trio.Event()
                if message.lower() in ['/exit', '/quit', '/выход']:
                    if await confirm_exit():
                        self._stop_event.set()
                        break
                    else:
                        self._can_input_event.set()
                        continue
                if self.username and (not message.startswith('/') or message.lower().startswith('/say ')):
                    chat_text = message[5:] if message.lower().startswith('/say ') else message
                    self._stop_lobby_live()
                    console.print(Text(f"{self.username}: ", style="bold cyan"), end="")
                    console.print(Text(chat_text))
                if not self.stream: break
                await self.stream.send_all(f"{message}\n".encode('utf-8'))
            except trio.BrokenResourceError:
                if not self._is_closing:
                    console.print("\n[bold red]Соединение с сервером потеряно.[/bold red]")
                self._stop_event.set()
            except trio.Cancelled:
                break

    async def receive_messages(self):
        try:
            while True:
                message_str = await self._read_message()
                if message_str is None:
                    self._stop_status()
                    self._stop_lobby_live()
                    self._stop_narration_live()
                    console.print("\n[bold red]Сервер закрыл соединение.[/bold red]")
                    break
                if message_str:
                    await self._parse_and_display_message(message_str)
        except trio.BrokenResourceError:
            if not self._is_closing:
                self._stop_status()
                self._stop_lobby_live()
                self._stop_narration_live()
                console.print("\n[bold red]Соединение с сервером потеряно.[/bold red]")
        except trio.Cancelled:
            pass
        finally:
            self._stop_event.set()

    async def _parse_and_display_message(self, message_str: str, sent_username: str = None):
        parts = message_str.split(' ', 1)
        prefix, content = parts[0], parts[1] if len(parts) > 1 else ""
        clean_prefix = prefix.strip("[]")

        if clean_prefix == "WELCOME":
            self.username = content.strip()
            console.print(create_welcome_message(self.username))
            console.line()
            return

        if clean_prefix == "LOBBY_UPDATE":
            self.lobby_players = [name for name in content.strip().split(',') if name]
            self._update_lobby_display()
            return

        self._stop_lobby_live()

        if clean_prefix == "SYSTEM":
            self._stop_narration_live()
            self._stop_status()
            sub_parts = content.strip().split(' ', 1)
            sys_command, sys_payload = sub_parts[0], sub_parts[1] if len(sub_parts) > 1 else ""

            if sys_command == "STATE_UPDATE":
                new_state = sys_payload.strip()
                if self.game_state == "LOBBY" and new_state == "ACTIVE":
                    self.game_state = new_state
                    console.clear()
                    if self.username:
                        console.print(create_welcome_message(self.username))
                        console.line()
                else:
                    self.game_state = new_state
                    if self.game_state == "LOBBY":
                        self._can_input_event.set()
                return

            if sys_command == "THINK_START":
                if not self._status:
                    console.line()
                    random_phrase = random.choice(self.phrases)
                    self._status = console.status(Text(random_phrase, style="italic yellow"), spinner="dots10")
                    self._status.start()
                return

            if sys_command == "NARRATION_END":
                console.line()
                self._can_input_event.set()
                return

            console.print(Text(content, style="yellow"))

        elif clean_prefix == "NARRATE":
            self._stop_status()
            processed_content = content.replace('<<BR>>', '\n')
            self._narration_buffer += processed_content

            narration_panel = Panel(
                Text(self._narration_buffer, style="italic cyan"),
                title="Рассказчик",
                border_style="dim cyan",
                expand=False
            )

            if not self._narration_live:
                self._narration_live = Live(narration_panel, console=console, auto_refresh=False,
                                            vertical_overflow="visible")
                self._narration_live.start(refresh=True)
            else:
                self._narration_live.update(narration_panel, refresh=True)

        else:
            self._stop_narration_live()
            self._stop_status()
            if clean_prefix == "ERROR":
                console.print(Text(f"[ОШИБКА СЕРВЕРА] {content}", style="bold red"))
            elif clean_prefix == "CHAT":
                sender, chat_text = content.split(':', 1)
                if not (self.username and sender.strip() == self.username):
                    console.print(Text(f"{sender.strip()}: ", style="magenta"), end="")
                    console.print(Text(chat_text.strip()))
            else:
                console.print(Text(message_str, style="white"))

    async def close_connection(self):
        self._stop_status()
        self._stop_lobby_live()
        self._stop_narration_live()
        if self.stream and not self._is_closing:
            self._is_closing = True
            console.print("[bold red]Отключение от сервера...[/bold red]")
            await self.stream.aclose()


async def main():
    try:
        while True:
            server_ip = await get_valid_ip()
            server_port = await get_valid_port()
            client = ChatClient(host=server_ip, port=server_port)
            await client.run()
            console.print("\n[bold yellow]Сессия завершена.[/bold yellow]")
            retry = await get_user_input("[bold yellow]Попробовать снова? (y/n)[/bold yellow]: ", "y")
            if retry.lower() not in ['y', 'yes', 'д', 'да']:
                break
    except Exception as e:
        console.print(f"[bold red]Критическая ошибка клиента: {e}[/bold red]")


if __name__ == "__main__":
    try:
        trio.run(main)
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Выход из клиента.[/bold yellow]")
