import json
from collections import defaultdict
from typing import Dict, Any

from rich.console import RenderableType, Group
from rich.columns import Columns
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich.tree import Tree


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


def render_help() -> RenderableType:
    """Рендерит панель с помощью по командам."""
    help_text = Text.from_markup(
        "  [bold cyan]/say [текст][/]       - Отправить сообщение всем в вашей локации.\n"
        "  [bold cyan]/status[/]            - Показать ваше состояние и описание локации.\n"
        "  [bold cyan]/map[/]               - Показать карту известных локаций.\n"
        "  [bold cyan]/help[/]              - Показать это сообщение.\n"
        "  [bold cyan]/exit[/] или [bold cyan]/quit[/]    - Выйти из игры."
    )
    return Panel(
        help_text,
        title="[bold]❓ Помощь[/]",
        border_style="blue",
        expand=False
    )


def render_map(data: Dict[str, Any]) -> RenderableType:
    """
    Рендерит карту мира, разделяя иерархию (дерево) и связи (граф).
    """
    locations = data.get('locations', [])
    connections = data.get('connections', [])
    current_loc_name = data.get('current_location')

    if not locations:
        return Panel(Text("Нет данных о карте.", style="dim"), title="[bold]🗺️ Карта Мира[/]")

    loc_map = {loc['name']: loc for loc in locations}
    children_map = defaultdict(list)
    top_level_locs = []
    for loc in locations:
        if loc.get('parent'):
            children_map[loc['parent']].append(loc['name'])
        else:
            top_level_locs.append(loc['name'])

    hierarchy_tree = Tree("[bold]Структура локаций (вложенность)[/bold]", guide_style="dim cyan")

    def build_hierarchy_tree(parent_node: Tree, loc_name: str):
        loc_data = loc_map.get(loc_name, {})

        player_count = len(loc_data.get('players', []))
        player_str = f" ({player_count} игрок{'а' if 1 < player_count < 5 else '' if player_count == 1 else 'ов'})" if player_count > 0 else ""

        label = Text(loc_name)
        if loc_name == current_loc_name:
            label.stylize("bold magenta")
            label.append(" (Вы здесь)", style="magenta")

        label.append(player_str, style="dim")
        node = parent_node.add(label)

        for child_name in sorted(children_map.get(loc_name, [])):
            build_hierarchy_tree(node, child_name)

    for loc_name in sorted(top_level_locs):
        build_hierarchy_tree(hierarchy_tree, loc_name)

    connections_list = []
    if connections:
        for conn in sorted(connections):
            connections_list.append(f"  • [cyan]{conn[0]}[/] <--> [cyan]{conn[1]}[/]")
        connections_text = Text.from_markup("\n".join(connections_list))
    else:
        connections_text = Text("Нет известных переходов.", style="dim")

    render_group = Group(
        hierarchy_tree,
        Rule("Известные переходы", style="dim", characters="·"),
        connections_text
    )

    return Panel(render_group, title="[bold yellow]:compass: Карта Мира[/bold yellow]", border_style="yellow")
