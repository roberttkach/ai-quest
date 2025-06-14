import json
from typing import Optional, TYPE_CHECKING

import trio

import config
from game.player import Player
from logger import lg

if TYPE_CHECKING:
    from main import Server


class PlayerConnection:
    """
    Чистый сетевой обработчик для одного игрока.
    Управляет сокетом, аутентификацией и передачей команд/действий
    в вышестоящие сервисы. Не хранит игровое состояние.
    """

    def __init__(self, server: 'Server', stream: trio.SocketStream):
        self.server = server
        self.stream = stream
        self.peer_addr = stream.socket.getpeername()
        self._buffer = ""
        self._write_lock = trio.Lock()
        self.username: Optional[str] = None
        lg.info(f"Создан объект PlayerConnection для нового соединения от {self.peer_addr}")

    def is_stream_closed(self) -> bool:
        return self.stream.socket.fileno() == -1

    async def _read_message(self) -> Optional[str]:
        while '\n' not in self._buffer:
            try:
                if self.is_stream_closed():
                    return None
                data = await self.stream.receive_some(4096)
                if not data:
                    return None
                self._buffer += data.decode('utf-8', errors='ignore')
            except (trio.BrokenResourceError, trio.ClosedResourceError):
                return None
        message, _, self._buffer = self._buffer.partition('\n')
        return message.strip()

    async def run(self):
        login_successful = False
        try:
            lg.debug(f"Запуск цикла run() для {self.peer_addr}")
            login_successful = await self._login_sequence()

            if login_successful and self.username:
                lg.info(f"Игрок '{self.username}' успешно вошел. Начало прослушивания сообщений.")
                while True:
                    message = await self._read_message()
                    if message is None:
                        lg.info(f"Игрок '{self.username}' штатно отключился (поток закрыт).")
                        break
                    lg.debug(f"Получено сообщение от '{self.username}': '{message}'")
                    await self._handle_message(message)
            else:
                lg.warning(f"Неудачная попытка входа от {self.peer_addr}. Соединение будет закрыто.")

        except Exception as e:
            username_info = f"'{self.username or 'Неизвестный'}' ({self.peer_addr})"
            if not isinstance(e, (trio.BrokenResourceError, trio.ClosedResourceError)):
                lg.error(f"Критическая ошибка при обработке клиента {username_info}: {e}", exc_info=True)
        finally:
            username_info = f"'{self.username or 'Неизвестный'}' ({self.peer_addr})"
            lg.info(f"Начало процедуры очистки для {username_info}.")
            if self.username:
                await self.server.remove_player(self)
            if not self.is_stream_closed():
                await self.stream.aclose()
            lg.info(f"Ресурсы для {username_info} освобождены.")

    async def _login_sequence(self) -> bool:
        lg.debug(f"Начало последовательности входа для {self.peer_addr}.")
        try:
            await self.send_direct("PROMPT Введите ваше имя: ")
            with trio.fail_after(30):
                username = await self._read_message()

            if not (username and 1 <= len(username) <= 20 and username.isalnum()):
                await self.send_direct("ERROR Имя должно быть от 1 до 20 букв/цифр.")
                return False

            self.username = username
            player_model = Player(username=self.username)

            success, reason = await self.server.game_state.add_player(player_model)
            if not success:
                error_msg = f"ERROR Сервер полон (максимум {config.MAX_PLAYERS} игроков)." if reason == "full" else f"ERROR Имя пользователя '{self.username}' уже занято."
                await self.send_direct(error_msg)
                self.username = None
                return False

            lg.info(f"Имя '{self.username}' принято. Вход успешен.")
            await self.send_direct(f"WELCOME {self.username}")
            await self.server.player_joined(self)
            return True
        except trio.TooSlowError:
            await self.send_direct("ERROR Превышено время ожидания для входа.")
            return False
        except (trio.BrokenResourceError, trio.ClosedResourceError):
            lg.warning(f"Соединение с {self.peer_addr} потеряно во время входа.")
            return False

    async def _handle_message(self, message: str):
        if not self.username:
            return

        is_active = await self.server.game_state.is_game_active()
        if message.startswith('/'):
            if is_active:
                await self._handle_command(message)
            else:
                await self.send_direct("ERROR Команды недоступны в лобби.")
                await self.send_direct("SYSTEM NARRATION_END")
        else:
            if is_active:
                await self.server.game_engine.handle_player_action(self, message)
            else:
                await self.server.handle_player_say(self, message)

    async def _handle_command(self, command_str: str):
        parts = command_str.strip().split(maxsplit=1)
        command, args = parts[0].lower(), parts[1] if len(parts) > 1 else ""

        if command == '/say':
            await self.server.handle_player_say(self, args)
        elif command == '/status':
            player_model = await self.server.game_state.get_player(self.username)
            if not player_model or not player_model.location_name:
                await self.send_direct("CMD_RESULT ⚙️ Вы находитесь в лобби.")
            else:
                location = await self.server.game_state.get_or_create_location(player_model.location_name)
                other_players = [p for p in location.players_present if p != self.username]
                status_data = {
                    "player": {"name": player_model.username, "status": player_model.status, "inventory": player_model.inventory},
                    "location": {"name": location.name, "description": location.description, "players": other_players}
                }
                await self.send_direct(f"STATUS_UPDATE {json.dumps(status_data, ensure_ascii=False)}")
        elif command == '/stats':
            stats_data = await self.server.game_state.get_stats()
            await self.send_direct(f"STATS_UPDATE {json.dumps(stats_data, ensure_ascii=False)}")
        elif command == '/players':
            players_list = await self.server.game_state.get_connected_usernames()
            await self.send_direct(f"PLAYERS_UPDATE {json.dumps({'players': players_list}, ensure_ascii=False)}")
        elif command == '/help':
            await self.send_direct("HELP_UPDATE")
        else:
            await self.send_direct(f"ERROR Неизвестная команда: {command}")

        await self.send_direct("SYSTEM NARRATION_END")

    async def send_direct(self, message: str):
        async with self._write_lock:
            if self.is_stream_closed():
                return
            try:
                if not message.endswith('\n'):
                    message += '\n'
                await self.stream.send_all(message.encode('utf-8'))
            except (trio.BrokenResourceError, trio.ClosedResourceError):
                lg.warning(f"Не удалось отправить сообщение для '{self.username or self.peer_addr}': соединение уже закрыто.")
