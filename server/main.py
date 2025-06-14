import sys
import argparse
from typing import Dict, Iterable, Optional, List

import trio
from rich.console import Console

import config
from game.engine import GameEngine
from game.state import GameState
from handlers.admin import AdminConsole
from handlers.player import PlayerConnection
from logger import lg
from llm.manager import ModelManager
from utils import find_available_port, initialize_debug_directories

console = Console()


class Server:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.nursery: Optional[trio.Nursery] = None
        self.game_state = GameState()
        self.model_manager = ModelManager()
        self.game_engine = GameEngine(self)
        self.admin_console = AdminConsole(self)
        self.player_connections: Dict[str, PlayerConnection] = {}
        lg.info(f"Сервер инициализирован с хостом {host} и портом {port}.")

    async def run(self):
        lg.info("--- Запуск сервера AI Quest ---")
        initialize_debug_directories()
        console.print("[bold blue]Инициализация языковой модели...[/bold blue]")
        if not await self.model_manager.initialize_model():
            lg.critical("Не удалось инициализировать языковую модель. Сервер не может быть запущен.")
            sys.exit(1)
        try:
            self.port = await find_available_port(self.port)
        except OSError as e:
            lg.critical(f"Не удалось найти доступный порт для запуска сервера: {e}", exc_info=True)
            sys.exit(1)

        async with trio.open_nursery() as nursery:
            self.nursery = nursery
            nursery.start_soon(self.admin_console.run)
            console.print(f"[bold green]Сервер слушает на {self.host}:{self.port}[/bold green]")
            await trio.serve_tcp(self._connection_handler, self.port, host=self.host)
        lg.info("--- Сервер завершил работу ---")

    async def _connection_handler(self, stream: trio.SocketStream):
        peer = stream.socket.getpeername()
        lg.info(f"Получено новое входящее соединение от {peer}.")
        player_conn = PlayerConnection(self, stream)
        await player_conn.run()

    async def player_joined(self, player_conn: PlayerConnection):
        if not player_conn.username: return
        self.player_connections[player_conn.username] = player_conn

        is_active = await self.game_state.is_game_active()
        await player_conn.send_direct(f"SYSTEM STATE_UPDATE {'ACTIVE' if is_active else 'LOBBY'}")

        if is_active:
            player_model = await self.game_state.get_player(player_conn.username)
            if player_model and player_model.location_name:
                await self.broadcast_to_locations({player_model.location_name},
                                                  f"SYSTEM {player_model.username} присоединился.",
                                                  exclude=[player_model.username])
                location = await self.game_state.get_or_create_location(player_model.location_name)
                await player_conn.send_direct(f"NARRATE {location.description.replace(chr(10), '<<BR>>')}")
                await player_conn.send_direct("SYSTEM NARRATION_END")
        else:
            all_players = await self.game_state.get_connected_usernames()
            await self.broadcast_system("LOBBY_UPDATE " + ",".join(all_players), is_direct=True)

    async def remove_player(self, player_conn: PlayerConnection):
        username = player_conn.username
        if not username: return

        self.player_connections.pop(username, None)
        last_loc_name = await self.game_state.remove_player(username)

        if last_loc_name:
            component = await self.game_state.get_connected_component(last_loc_name)
            await self.broadcast_to_locations(component, f"SYSTEM {username} покинул игру.", exclude=[username])
            await self.game_engine.on_player_removed(last_loc_name)
        else:
            all_players = await self.game_state.get_connected_usernames()
            if all_players:
                await self.broadcast_system("LOBBY_UPDATE " + ",".join(all_players), is_direct=True)

    async def kick_player(self, username: str) -> bool:
        player_conn = self.player_connections.get(username)
        if not player_conn: return False
        await player_conn.send_direct("SYSTEM Вы были исключены администратором.")
        await player_conn.stream.aclose()
        return True

    async def handle_player_say(self, player_conn: PlayerConnection, message: str):
        if not player_conn.username or not message: return

        is_active = await self.game_state.is_game_active()
        if is_active:
            player_model = await self.game_state.get_player(player_conn.username)
            if player_model and player_model.location_name:
                component = await self.game_state.get_connected_component(player_model.location_name)
                await self.broadcast_to_locations(component, f"CHAT {player_conn.username}: {message}")
        else:
            await self.broadcast_system(f"CHAT {player_conn.username}: {message}", is_direct=True)

    async def broadcast_to_locations(self, location_names: Iterable[str], message: str,
                                     exclude: Optional[List[str]] = None):
        players_in_locs = await self.game_state.get_players_in_locations(set(location_names))
        target_usernames = {p.username for p in players_in_locs}
        exclude_set = set(exclude or [])

        if self.nursery:
            for uname in target_usernames:
                if uname not in exclude_set and (conn := self.player_connections.get(uname)):
                    self.nursery.start_soon(conn.send_direct, message)

    async def broadcast_system(self, message: str, exclude: Optional[List[str]] = None, is_direct: bool = False):
        exclude_set = set(exclude or [])
        final_message = message if is_direct else f"SYSTEM {message}"

        if self.nursery:
            for uname, conn in self.player_connections.items():
                if uname not in exclude_set:
                    self.nursery.start_soon(conn.send_direct, final_message)


async def main():
    parser = argparse.ArgumentParser(description="AI Quest Server")
    parser.add_argument('--host', type=str, default=config.DEFAULT_HOST, help=f"Хост (умолч.: {config.DEFAULT_HOST})")
    parser.add_argument('--port', type=int, default=config.DEFAULT_PORT, help=f"Порт (умолч.: {config.DEFAULT_PORT})")
    args = parser.parse_args()
    server = Server(host=args.host, port=args.port)
    await server.run()


if __name__ == "__main__":
    try:
        trio.run(main)
    except KeyboardInterrupt:
        console.print(f"\n[bold yellow]Завершение работы сервера по запросу пользователя.[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Произошла критическая ошибка в сервере: {e}[/bold red]")
        lg.error("Критическая ошибка на верхнем уровне server/main.py", exc_info=True)
        sys.exit(1)
