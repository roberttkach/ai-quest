from typing import Dict, Any

from rich.console import RenderableType
from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def render_status(data: Dict[str, Any]) -> RenderableType:
    """
    Создает красивое и адаптивное отображение статуса игрока и окружения.
    """
    player_data = data.get('player', {})
    location_data = data.get('location', {})

    player_text = Text.from_markup(
        f"[bold]Имя:[/] {player_data.get('name', 'N/A')}\n"
        f"[bold]Статус:[/] {', '.join(player_data.get('status', ['N/A']))}\n"
        f"[bold]Инвентарь:[/] {', '.join(player_data.get('inventory', ['N/A']))}"
    )
    player_panel = Panel(
        player_text,
        title="[bold]👤 Персонаж[/]",
        border_style="cyan",
        expand=True
    )

    location_text = Text.from_markup(
        f"[bold]Локация:[/] {location_data.get('name', 'N/A')}\n"
        f"[bold]Другие игроки здесь:[/] {', '.join(location_data.get('players', [])) or 'никого'}\n"
        f"[bold]Описание:[/] {location_data.get('description', 'N/A')}"
    )
    location_panel = Panel(
        location_text,
        title="[bold]📍 Окружение[/]",
        border_style="yellow",
        expand=True
    )

    return Columns([player_panel, location_panel], expand=True, equal=True)


def render_stats(data: Dict[str, Any]) -> RenderableType:
    """Рендерит панель со статистикой игры."""
    stats_table = Table.grid(padding=(0, 2))
    stats_table.add_column(style="bold cyan", justify="right")
    stats_table.add_column(justify="left")

    stats_table.add_row("Всего игроков:", str(data.get('player_count', 'N/A')))
    stats_table.add_row("Активных локаций:", str(data.get('location_count', 'N/A')))
    stats_table.add_row("Связей между локациями:", str(data.get('connection_count', 'N/A')))
    stats_table.add_row("Глобальные флаги:", str(data.get('world_flags', 'Нет')))

    return Panel(
        stats_table,
        title="[bold]📊 Статистика Игры[/]",
        border_style="green",
        expand=False
    )


def render_players(data: Dict[str, Any], current_user: str) -> RenderableType:
    """Рендерит панель со списком игроков."""
    players = data.get('players', [])
    player_list = Text()
    for player in sorted(players):
        style = "bold yellow" if player == current_user else "white"
        player_list.append(f" • {player}\n", style=style)

    return Panel(
        player_list,
        title=f"[bold]👥 Игроки ({len(players)})[/]",
        border_style="magenta",
        expand=False
    )


def render_help() -> RenderableType:
    """Рендерит панель с помощью по командам."""
    help_text = Text.from_markup(
        "  [bold cyan]/say [текст][/] - Отправить сообщение всем в вашей локации.\n"
        "  [bold cyan]/status[/]      - Показать ваше состояние и описание локации.\n"
        "  [bold cyan]/stats[/]       - Показать глобальную статистику игры.\n"
        "  [bold cyan]/players[/]     - Показать список всех подключенных игроков.\n"
        "  [bold cyan]/help[/]        - Показать это сообщение.\n"
        "  [bold cyan]/exit[/] или [bold cyan]/quit[/] - Выйти из игры."
    )
    return Panel(
        help_text,
        title="[bold]❓ Помощь[/]",
        border_style="blue",
        expand=False
    )
