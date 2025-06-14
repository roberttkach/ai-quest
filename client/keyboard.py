import trio
import readchar
from typing import TYPE_CHECKING
from logger import lg
import utils

if TYPE_CHECKING:
    from engine import ClientEngine

class KeyboardHandler:
    """
    Изолирует и обрабатывает весь ввод с клавиатуры, используя
    простую и надежную библиотеку readchar.
    """

    def __init__(self, engine: "ClientEngine"):
        self.engine = engine

    async def run_input_loop(self):
        """Основной цикл для получения и обработки нажатий клавиш."""
        while not self.engine.stop_event.is_set():
            live = self.engine.live
            if not (live and live.is_started):
                await trio.sleep(0.05)
                continue

            try:
                key = await trio.to_thread.run_sync(readchar.readkey)
            except Exception as e:
                lg.warning(f"Не удалось обработать нажатие клавиши: {e}", exc_info=True)
                continue

            if key == readchar.key.UP:
                self.engine.model.scroll_offset += 1
                self.engine.update_display()
                continue
            if key == readchar.key.DOWN:
                self.engine.model.scroll_offset = max(0, self.engine.model.scroll_offset - 1)
                self.engine.update_display()
                continue

            if self.engine.model.status_line_content:
                continue

            self.engine.model.scroll_offset = 0

            if key in (readchar.key.ENTER, '\r', '\n'):
                if self.engine.model.input_buffer.lower() in ['/exit', '/quit', '/выход']:
                    if live and live.is_started:
                        live.stop()
                    should_exit = await utils.confirm("[bold yellow]Вы уверены, что хотите выйти? [/bold yellow]", False)
                    if live:
                        live.start(refresh=True)
                    if should_exit:
                        self.engine.stop_event.set()
                    else:
                        self.engine.model.input_buffer = ""
                        self.engine.update_display()
                    continue

                if self.engine.model.input_buffer and self.engine.state_handler:
                    message_to_send = self.engine.model.input_buffer
                    self.engine.model.input_buffer = ""
                    await self.engine.state_handler.handle_user_input(message_to_send)
                else:
                    self.engine.model.input_buffer = ""

            elif key == readchar.key.BACKSPACE:
                self.engine.model.input_buffer = self.engine.model.input_buffer[:-1]

            elif len(key) == 1 and key.isprintable():
                self.engine.model.input_buffer += key

            self.engine.update_display()
