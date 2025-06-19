from typing import Optional

import trio
from rich.text import Text

import states, utils
from engine import ClientEngine
from logger import lg


class NetworkHandler:
    """Управляет сетевым соединением, аутентификацией и циклом получения сообщений."""

    def __init__(self, engine: "ClientEngine"):
        self.engine = engine
        self.stream: Optional[trio.SocketStream] = None
        self._is_closing = False
        self._receive_buffer = ""

    async def connect(self) -> bool:
        """Устанавливает TCP-соединение и выполняет последовательность входа."""
        try:
            self.engine.console.print(f"Подключение к {self.engine.host}:{self.engine.port}...")
            with trio.move_on_after(60):
                self.stream = await trio.open_tcp_stream(self.engine.host, self.engine.port)
            if not self.stream:
                self.engine.console.print("[bold red]Не удалось подключиться: Таймаут[/bold red]")
                return False
            self.engine.model.is_connected = True
        except OSError as e:
            lg.warning(f"Ошибка подключения к серверу: {e}", exc_info=True)
            self.engine.console.print(f"[bold red]Не удалось подключиться к серверу: {e.strerror}[/bold red]")
            return False

        self.engine.change_state(states.LoginState)
        return await self._login_sequence()

    async def _login_sequence(self) -> bool:
        from ui.widgets.logo import LogoWidget

        prompt_message = await self._read_message()
        if prompt_message is None or not prompt_message.startswith("PROMPT"):
            self.engine.console.print("[bold red]Не удалось получить приглашение от сервера.[/bold red]")
            return False

        _, content = prompt_message.split(' ', 1)
        self.engine.console.print(LogoWidget(self.engine.model).render())
        username_to_send = ""
        while not username_to_send:
            username_to_send = await utils.get_rich_input(Text(content, style="bold blue").__str__())

        await self.send_message(username_to_send)
        response = await self._read_message()
        if response is None: return False

        if response.startswith("WELCOME"):
            self.engine.model.username = response.split(' ', 1)[1].strip()
            self.engine.model.lobby_messages.append(Text(f"Добро пожаловать, {self.engine.model.username}!", style="bold green"))
            return True
        else:
            self.engine.console.print(f"[bold red]Ошибка входа: {response}[/bold red]")
            return False

    async def run_message_loop(self):
        """Основной цикл для получения и обработки сообщений от сервера."""
        try:
            while not self.engine.stop_event.is_set():
                message_str = await self._read_message()
                if message_str is None: break

                try:
                    parts = message_str.split(' ', 1)
                    prefix, content = parts[0].strip("[]"), parts[1] if len(parts) > 1 else ""

                    if prefix != "NARRATE":
                        lg.debug(f"Получено сообщение: {message_str}")

                    if self.engine.state_handler:
                        await self.engine.state_handler.handle_message(prefix, content)

                    self.engine.model.scroll_offset = 0
                    self.engine.update_display()

                except Exception as e:
                    lg.error(f"Ошибка при обработке сообщения '{message_str}': {e}", exc_info=True)
                    log_target = self.engine.model.game_log if isinstance(self.engine.state_handler, states.GameState) else self.engine.model.lobby_messages
                    log_target.append(Text("[ОШИБКА КЛИЕНТА] Не удалось обработать сообщение.", style="bold red"))
                    self.engine.update_display()

        except trio.BrokenResourceError:
            lg.warning("Соединение с сервером разорвано.")
        finally:
            if not self._is_closing:
                self.engine.console.print("\n[bold red]Соединение с сервером потеряно.[/bold red]")
            self.engine.model.is_connected = False
            self.engine.stop_event.set()

    async def send_message(self, message: str):
        if self.stream and not self._is_closing:
            lg.debug(f"Отправка сообщения: {message}")
            await self.stream.send_all(f"{message}\n".encode('utf-8'))

    async def _read_message(self) -> Optional[str]:
        if not self.stream: return None
        while '\n' not in self._receive_buffer:
            try:
                data = await self.stream.receive_some(4096)
                if not data:
                    lg.warning("Соединение закрыто сервером (получены пустые данные).")
                    return None
                self._receive_buffer += data.decode('utf-8', errors='ignore')
            except (trio.BrokenResourceError, trio.ClosedResourceError):
                return None
        message, _, self._receive_buffer = self._receive_buffer.partition('\n')
        return message

    async def close(self):
        if self.engine.live and self.engine.live.is_started: self.engine.live.stop()
        if self.stream and not self._is_closing:
            self._is_closing = True
            lg.info("Закрытие соединения с сервером.")
            await self.stream.aclose()
