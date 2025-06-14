from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from ui.widgets.widget import Widget


class LobbyWidget(Widget):
    def render(self) -> RenderableType:
        table = Table.grid(padding=(0, 2))
        table.add_column(justify="right", style="dim")
        table.add_column(justify="left")

        players = self.model.players_in_lobby
        for i, player in enumerate(sorted(players), 1):
            style = "bold cyan" if player == self.model.username else "white"
            table.add_row(f"{i}.", Text(player, style=style))

        player_count = len(players)
        title = f"[bold green]:busts_in_silhouette: Игроки в лобби ({player_count}/4)[/bold green]"

        player_panel = Panel(
            Align.center(table),
            title=title,
            border_style="green",
        )

        if player_count >= 4:
            wait_text = Text(" Лобби заполнено. Ожидание начала игры...", style="italic green")
        else:
            wait_text = Text(" Ожидание начала игры...", style="italic yellow")

        return Group(
            player_panel,
            Align.center(Spinner("dots10", text=wait_text))
        )
