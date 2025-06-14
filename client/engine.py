from typing import Optional, Type, TYPE_CHECKING

import trio
from rich.console import Console
from rich.live import Live

import states
from logger import lg
from model import ClientDataModel
from ui.layout import LayoutManager

if TYPE_CHECKING:
    from keyboard import KeyboardHandler
    from network import NetworkHandler


class ClientEngine:
    """
    Ядро-оркестратор клиента. Управляет жизненным циклом, машиной состояний,
    и делегирует обработку ввода и сети специализированным модулям.
    """

    def __init__(self, host: str, port: int):
        from keyboard import KeyboardHandler
        from network import NetworkHandler

        self.host = host
        self.port = port
        self.stop_event = trio.Event()
        self.nursery: Optional[trio.Nursery] = None
        self.console = Console()
        self.live: Optional[Live] = None
        self.model = ClientDataModel()
        self.network_handler: 'NetworkHandler' = NetworkHandler(self)
        self.keyboard_handler: 'KeyboardHandler' = KeyboardHandler(self)
        self.layout_manager = LayoutManager(self.model)
        self.state_handler: Optional['states.BaseState'] = None

        lg.info(f"Движок клиента инициализирован для подключения к {host}:{port}")

    def change_state(self, new_state_class: Type['states.BaseState']):
        lg.info(f"Переход в состояние: {new_state_class.__name__}")
        if self.state_handler:
            self.state_handler.exit()

        self.model.current_state_class = new_state_class
        self.state_handler = new_state_class(self)
        self.state_handler.enter(self.live)

        if self.live and self.live.is_started:
            self.update_display()

    def update_display(self):
        if self.live and self.live.is_started:
            layout = self.layout_manager.build_layout()
            self.live.update(layout, refresh=True)

    async def send_message(self, message: str):
        """Делегирует отправку сообщения сетевому обработчику."""
        await self.network_handler.send_message(message)

    async def run(self):
        try:
            if not await self.network_handler.connect():
                return

            self.console.clear()

            with Live(console=self.console, screen=True, auto_refresh=False,
                      refresh_per_second=30, transient=True, vertical_overflow="visible") as live:
                self.live = live
                self.change_state(states.LobbyState)

                async with trio.open_nursery() as nursery:
                    self.nursery = nursery
                    nursery.start_soon(self.network_handler.run_message_loop)
                    nursery.start_soon(self.keyboard_handler.run_input_loop)
                    await self.stop_event.wait()
                    nursery.cancel_scope.cancel()

        except Exception as e:
            if not isinstance(e, trio.Cancelled):
                self.console.print(f"[bold red]Произошла непредвиденная ошибка: {e}[/bold red]")
                lg.error("Критическая ошибка в ClientEngine.run", exc_info=True)
        finally:
            await self.network_handler.close()
