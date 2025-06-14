from rich.console import RenderableType
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from model import ClientDataModel
from ui.widgets.widget import Widget
from ui.widgets.input import InputWidget


class FooterWidget(Widget):
    """
    Компонент для нижней строки, объединяющий статус и поле ввода.
    """

    def __init__(self, model: "ClientDataModel"):
        super().__init__(model)
        self.input_widget = InputWidget(model)

    def render(self) -> RenderableType:
        footer_table = Table.grid(expand=True)
        footer_table.add_column(justify="left", ratio=1)
        footer_table.add_column(justify="right", no_wrap=True)

        status_renderable: RenderableType = ""

        if self.model.status_line_content:
            status_renderable = Spinner(
                "dots10",
                text=Text.from_markup(f" [italic yellow]{self.model.status_line_content}[/]"),
                style="dim yellow"
            )

        input_renderable = self.input_widget.render()

        footer_table.add_row(status_renderable, input_renderable)
        return footer_table
