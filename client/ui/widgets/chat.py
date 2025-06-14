from rich.box import ROUNDED
from rich.console import Console, ConsoleOptions, RenderResult, Group
from rich.panel import Panel

from ui.widgets.widget import Widget


class ChatWidget(Widget):
    """
    Компонент для отображения чата в лобби.
    Отображает сообщения из общего пула и подстраивает их количество под высоту панели.
    """

    def __rich_console__(self, _console: Console, options: ConsoleOptions) -> RenderResult:
        content_height = options.max_height - 2
        self.model.set_lobby_message_capacity(content_height)

        yield Panel(
            Group(*self.model.lobby_messages),
            box=ROUNDED,
            title="[bold yellow]:speech_balloon: Чат[/bold yellow]",
            border_style="dim yellow",
        )

    def render(self):
        """Возвращает сам объект для рендеринга через __rich_console__."""
        return self
