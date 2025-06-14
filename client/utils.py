import random

import trio
from rich.console import Console
from rich.prompt import Prompt
from rich.text import Text

from logger import lg

console = Console()
DEFAULT_PORT = 65432

PHRASES = [
    "Время замедлило ход...", "Здесь что-то не так...", "Напряжение нарастает...", "Повеяло холодом...",
    "Одно мгновение...", "Что-то пробудилось...", "Ищу верную ноту...", "Занавес дрогнул...",
    "Тени сгущаются...", "Что-то грядет...", "Прислушиваюсь к тишине...", "Держу паузу..."
]
STATE_PHRASES = [
    "Анализирую последствия...", "Сверяюсь с реальностью...", "Мир меняется...", "Обновляю хроники...",
    "Собираю осколки событий...", "Нити судьбы сплетаются...", "Записываю в летопись...",
    "Фиксирую аномалию...", "Рассвет новой эры...", "Заношу в архив...", "Пыль улеглась...",
    "Загрузка ландшафта..."
]


def get_random_phrase(phrase_type: str) -> str:
    pool = PHRASES if phrase_type == 'phrases' else STATE_PHRASES
    return random.choice(pool)


async def get_rich_input(prompt: str, default: str = "") -> str:
    def _blocking_input():
        return Prompt.ask(prompt, default=default, console=console)

    user_input = await trio.to_thread.run_sync(_blocking_input)
    lg.debug(f"Получен ввод от пользователя: '{user_input}'")
    return user_input


async def get_valid_ip() -> str:
    while True:
        ip = await get_rich_input(
            Text("Введите IP-адрес сервера", style="bold blue").__str__(),
            "127.0.0.1"
        )
        parts = ip.split(".")
        if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
            return ip
        lg.warning(f"Пользователь ввел неверный IP-адрес: '{ip}'")
        console.print("[bold red]Неверный формат IP-адреса. Пожалуйста, попробуйте снова.[/bold red]")


async def get_valid_port() -> int:
    while True:
        port_str = await get_rich_input(
            Text(f"Введите порт сервера", style="bold blue").__str__(),
            str(DEFAULT_PORT)
        )
        if port_str.isdigit() and 0 < (port := int(port_str)) < 65536:
            return port
        lg.warning(f"Пользователь ввел неверный порт: '{port_str}'")
        console.print("[bold red]Неверный порт. Введите число от 1 до 65535.[/bold red]")


async def confirm(prompt: str, default: bool) -> bool:
    default_str = "y" if default else "n"
    choices = ["y", "n"]

    def _blocking_ask():
        return Prompt.ask(
            prompt,
            choices=choices,
            default=default_str,
            console=console
        )

    response = await trio.to_thread.run_sync(_blocking_ask)
    return response.lower() == "y"
