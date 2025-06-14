from rich.box import ROUNDED
from rich.console import Console, ConsoleOptions, RenderResult, Group
from rich.panel import Panel
from rich.text import Text

from ui.widgets.widget import Widget


class GameWidget(Widget):
    """
    Игровой компонент ("Мир") для отображения всех событий в игре.
    Поддерживает построчную прокрутку и отображение временного вывода команд.
    """

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        content_height = options.max_height - 2
        if content_height <= 0:
            yield Panel(Group(), expand=True)
            return

        renderables_to_process = list(self.model.game_log)
        if self.model.command_output:
            renderables_to_process.append(self.model.command_output)

        history_group = Group(*renderables_to_process)

        render_options = options.update(width=options.max_width - 4)

        all_lines = []
        current_line = Text()
        for segment in console.render(history_group, render_options):
            if segment.text == "\n":
                all_lines.append(current_line)
                current_line = Text()
            else:
                current_line.append(segment.text, style=segment.style)

        if current_line:
            all_lines.append(current_line)

        total_lines = len(all_lines)

        max_offset = max(0, total_lines - content_height)

        self.model.scroll_offset = min(self.model.scroll_offset, max_offset)
        clamped_offset = self.model.scroll_offset

        end_index = total_lines - clamped_offset
        start_index = max(0, end_index - content_height)

        lines_to_render = all_lines[start_index:end_index]

        if total_lines > content_height:
            subtitle = f"Строки {start_index + 1}-{end_index} из {total_lines} | [bold cyan][↑][↓][/] для прокрутки"
        else:
            subtitle = ""

        yield Panel(
            Group(*lines_to_render),
            box=ROUNDED,
            title="[bold yellow]:compass: Мир[/bold yellow]",
            subtitle=f"[dim]{subtitle}[/dim]",
            border_style="dim yellow",
        )

    def render(self):
        """Возвращает сам объект для рендеринга через __rich_console__."""
        return self
