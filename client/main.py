import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import trio

from engine import ClientEngine
from logger import lg
from utils import confirm, get_valid_ip, get_valid_port, console


async def run_session():
    server_ip = await get_valid_ip()
    server_port = await get_valid_port()
    engine = ClientEngine(host=server_ip, port=server_port)
    await engine.run()
    console.print("\n[bold yellow]Сессия завершена.[/bold yellow]")


async def main():
    while True:
        try:
            await run_session()
            if not await confirm("[bold yellow]Попробовать снова?[/bold yellow]", True):
                break
        except Exception as e:
            console.print(f"[bold red]Критическая ошибка клиента: {e}[/bold red]")
            lg.error("Критическая ошибка клиента", exc_info=True)
            if not await confirm("[bold red]Произошла ошибка. Попробовать снова?[/bold red]", False):
                break


if __name__ == "__main__":
    try:
        trio.run(main)
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Выход из клиента.[/bold yellow]")
