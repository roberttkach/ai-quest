import argparse
import sys
from typing import List, Optional

import trio
from rich.console import Console

from . import config
from .handlers.admin import AdminConsole
from .llm.prompt_builder import construct_prompt
from .game.state import GameState
from .logger import lg
from .llm.manager import ModelManager
from .handlers.player import PlayerConnection
from .utils import find_available_port

console = Console()


class Server:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.game_state = GameState()
        self.model_manager = ModelManager()
        self.admin_console = AdminConsole(self)
        self.nursery: Optional[trio.Nursery] = None
        lg.info(f"Сервер инициализирован с хостом {host} и портом {port}.")

    async def run(self):
        lg.info("--- Запуск сервера AI Quest ---")
        console.print("[bold blue]Инициализация модели...[/bold blue]")
        if not await self.model_manager.initialize_model():
            lg.critical("Не удалось инициализировать языковую модель. Сервер не может быть запущен.")
            sys.exit(1)
        try:
            self.port = await find_available_port(self.port)
            lg.info(f"Сервер будет запущен на {self.host}:{self.port}")
        except OSError as e:
            lg.critical(f"Не удалось найти доступный порт для запуска сервера: {e}", exc_info=True)
            sys.exit(1)

        async with trio.open_nursery() as nursery:
            self.nursery = nursery
            nursery.start_soon(self.admin_console.run)
            lg.info(f"Запуск TCP-сервера для прослушивания на {self.host}:{self.port}")
            console.print(f"[bold green]Сервер слушает на {self.host}:{self.port}[/bold green]")
            await trio.serve_tcp(self._connection_handler, self.port, host=self.host)
        lg.info("--- Сервер завершил работу ---")

    async def _connection_handler(self, stream: trio.SocketStream):
        peer = stream.socket.getpeername()
        lg.info(f"Получено новое входящее соединение от {peer}.")
        player_conn = PlayerConnection(self, stream)
        try:
            await player_conn.run()
        except Exception as e:
            lg.error(f"Ошибка в главном обработчике соединения для {peer}: {e}", exc_info=True)
        finally:
            if player_conn.username:
                await self.remove_player(player_conn, is_final_cleanup=True)
            lg.info(f"Соединение с {peer} окончательно закрыто.")

    async def player_joined(self, player: PlayerConnection):
        if not player.username or not player.current_room: return
        is_active = await self.game_state.is_game_active()
        state_str = "ACTIVE" if is_active else "LOBBY"
        await player.send_direct(f"SYSTEM STATE_UPDATE {state_str}")
        await self.broadcast_system(f"{player.username} присоединился к игре.", room=player.current_room,
                                    exclude=[player.username])
        if is_active:
            await self._trigger_narration(player.username, player.current_room, initial=True)
        else:
            await player.send_direct("SYSTEM Пожалуйста, ожидайте начала игры.")
            await player.send_direct("SYSTEM NARRATION_END")

    async def remove_player(self, player: PlayerConnection, is_final_cleanup: bool = False):
        username = player.username
        if not username: return
        room = await self.game_state.remove_player(username)
        if room:
            await self.broadcast_system(f"{username} покинул игру.", room=room, exclude=[username])

    async def kick_player(self, username: str) -> bool:
        player_conn = await self.game_state.get_player_connection(username)
        if not player_conn:
            return False
        await player_conn.send_direct("SYSTEM Вы были исключены администратором.")
        await player_conn.stream.aclose()
        return True

    async def handle_player_action(self, player: PlayerConnection, action: str):
        if not player.username or not player.current_room: return
        await self.game_state.add_player_action_to_history(player.username, action)
        await self.broadcast_chat(player, action, room=player.current_room)
        await self._trigger_narration(player.username, player.current_room)

    async def handle_player_say(self, player: PlayerConnection, message: str):
        if not player.username or not player.current_room: return
        await self.broadcast_chat(player, message, room=player.current_room)

    async def narrate_initial_room_for_all(self):
        start_room = self.game_state.start_room
        players_in_room = await self.game_state.get_players_in_room(start_room)
        if players_in_room and players_in_room[0].username:
            await self._trigger_narration(players_in_room[0].username, start_room, initial=True)

    async def _trigger_narration(self, username: str, room: str, initial: bool = False):
        if not initial:
            await self.game_state.increment_turn_counter(room)
        prompt = await construct_prompt(username, self.game_state)
        if not prompt: return

        try:
            async with await trio.open_file('prompt.txt', 'w', encoding='utf-8') as f:
                await f.write(prompt)
            lg.debug("Последний промпт успешно записан в prompt.txt")
        except Exception as e:
            lg.error(f"Не удалось записать промпт в файл prompt.txt: {e}")

        players_in_room = await self.game_state.get_players_in_room(room)
        if not players_in_room: return

        if self.nursery:
            for player in players_in_room:
                self.nursery.start_soon(player.send_direct, "SYSTEM THINK_START")

        full_narration_text = ""
        try:
            async for content in self.model_manager.stream_response(prompt):
                if not self.nursery: break
                if content:
                    full_narration_text += content
                    message = f"NARRATE {content.replace(chr(10), '<<BR>>')}"
                    await self._broadcast(message, room=room)
        except Exception as e:
            lg.error(f"Ошибка во время обработки потока повествования для комнаты '{room}': {e}", exc_info=True)
            await self.broadcast_system("Произошла ошибка с Рассказчиком.", room=room)
        finally:
            if full_narration_text:
                await self.game_state.add_narration_to_history(room, full_narration_text)
            await self.broadcast_system("NARRATION_END", room=room)

    async def _broadcast(self, message: str, room: Optional[str] = None, exclude: Optional[List[str]] = None):
        targets = await self.game_state.get_players_in_room(room) if room else await self.game_state.get_all_players()
        exclude_set = set(exclude or [])
        if self.nursery:
            for p in targets:
                if p.username and p.username not in exclude_set:
                    self.nursery.start_soon(p.send_direct, message)

    async def broadcast_chat(self, sender: PlayerConnection, message: str, room: str):
        if not sender.username: return
        await self._broadcast(f"CHAT {sender.username}: {message}", room=room)

    async def broadcast_system(self, message: str, room: Optional[str] = None, exclude: Optional[List[str]] = None):
        await self._broadcast(f"SYSTEM {message}", room=room, exclude=exclude)


async def main():
    parser = argparse.ArgumentParser(description="AI Quest Server")
    parser.add_argument('--host', type=str, default=config.DEFAULT_HOST,
                        help=f"Хост для сервера (по умолч.: {config.DEFAULT_HOST})")
    parser.add_argument('--port', type=int, default=config.DEFAULT_PORT,
                        help=f"Порт для сервера (по умолч.: {config.DEFAULT_PORT})")
    args = parser.parse_args()
    server = Server(host=args.host, port=args.port)
    await server.run()
