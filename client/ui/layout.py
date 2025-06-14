from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

from model import ClientDataModel
from ui.widgets import chat, footer, game, lobby, logo


class LayoutManager:
    def __init__(self, model: "ClientDataModel"):
        self.model = model
        self.widgets = {
            'logo': logo.LogoWidget(model),
            'chat': chat.ChatWidget(model),
            'lobby': lobby.LobbyWidget(model),
            'game': game.GameWidget(model),
            'footer': footer.FooterWidget(model),
        }

    def build_layout(self) -> Layout:
        """
        Собирает макет для UI в зависимости от текущего состояния клиента.
        """
        state_name = self.model.state_name

        if state_name == "LobbyState":
            return self._build_lobby_layout()

        if state_name == "GameState":
            return self._build_game_layout()

        return Layout(Panel(Text("Загрузка...", style="dim")))

    def _build_lobby_layout(self) -> Layout:
        """Собирает макет для состояния лобби."""
        layout = Layout()

        layout.split(
            Layout(self.widgets['logo'].render(), name="header", size=logo.LOGO_ART_HEIGHT),
            Layout(name="body", ratio=1)
        )
        layout["body"].split(
            Layout(self.widgets['chat'].render(), name="main", ratio=6),
            Layout(self.widgets['lobby'].render(), name="side", ratio=4),
            Layout(self.widgets['footer'].render(), name="footer", size=3)
        )

        return layout

    def _build_game_layout(self) -> Layout:
        """Собирает макет для основного игрового состояния."""
        layout = Layout(name="root")

        layout.split(
            Layout(self.widgets['game'].render(), name="main", ratio=1),
            Layout(self.widgets['footer'].render(), name="footer", size=1)
        )
        return layout
