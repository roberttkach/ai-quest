from rich.console import RenderableType
from rich.text import Text

from ui.widgets.widget import Widget


class InputWidget(Widget):
    """
    Компонент для отображения интерактивной строки-приглашения для ввода.
    """

    def render(self) -> RenderableType:
        prompt = Text.from_markup(f"{self.model.input_buffer}")
        cursor = Text("█", style="blink bold green")
        return Text.from_markup("[bold green]❯ [/bold green]") + prompt + cursor
