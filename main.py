import argparse
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import trio
from rich.console import Console

console = Console()


def main():
    """
    Основная точка входа в приложение.
    Разбирает аргументы командной строки для запуска клиента или сервера.
    """

    parser = argparse.ArgumentParser(
        description="AI Quest: Запуск клиента или сервера.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', required=True, help='Доступные команды')

    subparsers.add_parser('server', help='Запустить игровой сервер. Используйте --help для просмотра опций сервера.')
    subparsers.add_parser('client', help='Запустить игровой клиент.')

    args, remaining_argv = parser.parse_known_args()
    sys.argv = [sys.argv[0]] + remaining_argv

    try:
        if args.command == 'server':
            from server.app import main as server_main
            console.print("[bold cyan]Запуск в режиме сервера...[/bold cyan]")
            trio.run(server_main)

        elif args.command == 'client':
            from client.app import main as client_main
            trio.run(client_main)

    except KeyboardInterrupt:
        log_source = "server" if args.command == 'server' else "client"
        console.print(f"\n[bold yellow]Завершение работы {log_source} по запросу пользователя.[/bold yellow]")
    except Exception as e:
        log_source = "server" if args.command == 'server' else "client"
        console.print(f"[bold red]Произошла критическая ошибка в {log_source}: {e}[/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
