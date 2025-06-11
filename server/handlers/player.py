from typing import TYPE_CHECKING, Optional

import trio

from ..logger import lg

if TYPE_CHECKING:
    from ..app import Server


class PlayerConnection:
    def __init__(self, server: 'Server', stream: trio.SocketStream):
        self.server = server
        self.stream = stream
        self.username: Optional[str] = None
        self.peer_addr = stream.socket.getpeername()
        self.current_room: Optional[str] = None
        self._buffer = ""
        self._write_lock = trio.Lock()
        lg.info(f"Создан объект PlayerConnection для нового соединения от {self.peer_addr}")

    def is_stream_closed(self) -> bool:
        """Надежная проверка, закрыт ли стрим."""
        return self.stream.socket.fileno() == -1

    async def _read_message(self) -> Optional[str]:
        """Надежно читает одно сообщение, завершающееся новой строкой."""
        while '\n' not in self._buffer:
            try:
                if self.is_stream_closed(): return None
                data = await self.stream.receive_some(4096)
                if not data:
                    return None
                self._buffer += data.decode('utf-8', errors='ignore')
            except (trio.BrokenResourceError, trio.ClosedResourceError):
                return None
        message, _, self._buffer = self._buffer.partition('\n')
        return message.strip()

    async def run(self):
        """Основной цикл жизни соединения игрока."""
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

        except (trio.BrokenResourceError, trio.ClosedResourceError):
            if login_successful and self.username:
                lg.warning(f"Соединение с '{self.username}' ({self.peer_addr}) было внезапно разорвано.")
            else:
                lg.warning(f"Соединение с {self.peer_addr} было разорвано во время попытки входа.")
        except Exception as e:
            username_info = f"'{self.username or 'Неизвестный'}' ({self.peer_addr})"
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
        """Обрабатывает последовательность входа игрока."""
        lg.debug(f"Начало последовательности входа для {self.peer_addr}.")
        try:
            await self.send_direct("PROMPT Введите ваше имя: ")

            with trio.fail_after(30):
                username = await self._read_message()

            if username is None:
                lg.warning(f"Клиент {self.peer_addr} закрыл соединение до отправки имени.")
                return False

            lg.info(f"Получено имя пользователя '{username}' от {self.peer_addr}.")
            if not username or len(username) > 20 or not username.isalnum():
                lg.warning(f"Недопустимое имя пользователя от {self.peer_addr}: '{username}'.")
                await self.send_direct(
                    "ERROR Имя должно быть от 1 до 20 букв/цифр.")
                return False

            self.username = username

            if not await self.server.game_state.add_player(self):
                lg.warning(f"Имя пользователя '{self.username}' уже занято.")
                await self.send_direct(f"ERROR Имя пользователя '{self.username}' уже занято.")
                self.username = None
                return False

            lg.info(f"Имя '{self.username}' принято. Вход успешен.")
            await self.send_direct(f"WELCOME {self.username}")
            await self.server.player_joined(self)
            return True
        except trio.TooSlowError:
            lg.warning(f"Таймаут входа для {self.peer_addr}.")
            await self.send_direct("ERROR Превышено время ожидания для входа.")
            return False
        except (trio.BrokenResourceError, trio.ClosedResourceError):
            lg.warning(f"Соединение с {self.peer_addr} потеряно во время входа.")
            return False

    async def _handle_message(self, message: str):
        if not self.username:
            return
        if message.startswith('/'):
            await self._handle_command(message)
        else:
            is_active = await self.server.game_state.is_game_active()
            if is_active:
                await self.server.handle_player_action(self, message)
            else:
                lg.info(f"Игрок '{self.username}' в лобби, сообщение '{message}' обрабатывается как /say.")
                await self.server.handle_player_say(self, message)
                await self.send_direct("SYSTEM NARRATION_END")

    async def _handle_command(self, command_str: str):
        parts = command_str.strip().split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        lg.info(f"Игрок '{self.username}' выполняет команду: '{command}' с аргументами: '{args}'")

        if command == '/say':
            if not args:
                await self.send_direct("ERROR Использование: /say [сообщение]")
            else:
                await self.server.handle_player_say(self, args)
            await self.send_direct("SYSTEM NARRATION_END")

        elif command == '/stats':
            stats = await self.server.game_state.get_stats()
            await self.send_direct(f"SYSTEM \n{stats}")
            await self.send_direct("SYSTEM NARRATION_END")

        elif command == '/players':
            players = await self.server.game_state.get_connected_usernames()
            await self.send_direct(f"SYSTEM Подключенные игроки: {', '.join(players)}")
            await self.send_direct("SYSTEM NARRATION_END")

        elif command == '/help':
            help_text = (
                "SYSTEM Доступные команды:\n"
                "  /say [сообщение] - Отправить сообщение игрокам в вашей комнате.\n"
                "  /stats           - Показать статистику игры.\n"
                "  /players         - Показать список всех подключенных игроков.\n"
                "  /help            - Показать это сообщение.\n"
                "  /quit или /exit  - Покинуть игру."
            )
            await self.send_direct(help_text)
            await self.send_direct("SYSTEM NARRATION_END")

        else:
            lg.warning(f"Игрок '{self.username}' ввел неизвестную команду: '{command}'")
            await self.send_direct(f"ERROR Неизвестная команда: {command}")
            await self.send_direct("SYSTEM NARRATION_END")

    async def send_direct(self, message: str):
        """Надежно отправляет сообщение напрямую этому игроку."""
        async with self._write_lock:
            if self.is_stream_closed():
                lg.warning(f"Попытка отправки на уже закрытый сокет для '{self.username or self.peer_addr}'.")
                return

            try:
                if not message.endswith('\n'):
                    message += '\n'

                if not message.strip().startswith("NARRATE"):
                    lg.debug(f"Отправка прямого сообщения для '{self.username or self.peer_addr}': '{message.strip()}'")

                await self.stream.send_all(message.encode('utf-8'))

            except (trio.BrokenResourceError, trio.ClosedResourceError):
                lg.warning(
                    f"Не удалось отправить прямое сообщение для '{self.username or self.peer_addr}': соединение уже закрыто.")
            except Exception as e:

                if not isinstance(e, trio.BusyResourceError):
                    lg.error(
                        f"Непредвиденная ошибка при отправке сообщения для '{self.username or self.peer_addr}': {e}",
                        exc_info=True)
                else:
                    lg.warning(
                        f"Перехвачен BusyResourceError для '{self.username}', несмотря на блокировку. Сообщение пропущено.")
