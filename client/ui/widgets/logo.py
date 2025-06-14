import random

from rich.align import Align
from rich.console import Group, RenderableType
from rich.rule import Rule
from rich.text import Text

from ui.widgets.widget import Widget

LOGO_ART = """
 
 
 
 
 █     █░▓█████  ██▓     ▄████▄   ▒█████   ███▄ ▄███▓▓█████ 
▓█░ █ ░█░▓█   ▀ ▓██▒    ▒██▀ ▀█  ▒██▒  ██▒▓██▒▀█▀ ██▒▓█   ▀ 
▒█░ █ ░█ ▒███   ▒██░    ▒▓█    ▄ ▒██░  ██▒▓██    ▓██░▒███   
░█░ █ ░█ ▒▓█  ▄ ▒██░    ▒▓▓▄ ▄██▒▒██   ██░▒██    ▒██ ▒▓█  ▄ 
░░██▒██▓ ░▒████▒░██████▒▒ ▓███▀ ░░ ████▓▒░▒██▒   ░██▒░▒████▒
░ ▓░▒ ▒  ░░ ▒░ ░░ ▒░▓  ░░ ░▒ ▒  ░░ ▒░▒░▒░ ░ ▒░   ░  ░░░ ▒░ ░
  ▒ ░ ░   ░ ░  ░░ ░ ▒  ░  ░  ▒     ░ ▒ ▒░ ░  ░      ░ ░ ░  ░
  ░   ░     ░     ░ ░   ░        ░ ░ ░ ▒  ░      ░      ░   
    ░       ░  ░    ░  ░░ ░          ░ ░         ░      ░  ░
                        ░                                   
▄▄▄█████▓ ▒█████     ▄▄▄█████▓ ██░ ██ ▓█████                
▓  ██▒ ▓▒▒██▒  ██▒   ▓  ██▒ ▓▒▓██░ ██▒▓█   ▀                
▒ ▓██░ ▒░▒██░  ██▒   ▒ ▓██░ ▒░▒██▀▀██░▒███                  
░ ▓██▓ ░ ▒██   ██░   ░ ▓██▓ ░ ░▓█ ░██ ▒▓█  ▄                
  ▒██▒ ░ ░ ████▓▒░     ▒██▒ ░ ░▓█▒░██▓░▒████▒               
  ▒ ░░   ░ ▒░▒░▒░      ▒ ░░    ▒ ░░▒░▒░░ ▒░ ░               
    ░      ░ ▒ ▒░        ░     ▒ ░▒░ ░ ░ ░  ░               
  ░      ░ ░ ░ ▒       ░       ░  ░░ ░   ░                  
             ░ ░               ░  ░  ░   ░  ░               
 
 ▄▄▄       ██▓     █████   █    ██ ▓█████   ██████ ▄▄▄█████▓
▒████▄    ▓██▒   ▒██▓  ██▒ ██  ▓██▒▓█   ▀ ▒██    ▒ ▓  ██▒ ▓▒
▒██  ▀█▄  ▒██▒   ▒██▒  ██░▓██  ▒██░▒███   ░ ▓██▄   ▒ ▓██░ ▒░
░██▄▄▄▄██ ░██░   ░██  █▀ ░▓▓█  ░██░▒▓█  ▄   ▒   ██▒░ ▓██▓ ░ 
 ▓█   ▓██▒░██░   ░▒███▒█▄ ▒▒█████▓ ░▒████▒▒██████▒▒  ▒██▒ ░ 
 ▒▒   ▓▒█░░▓     ░░ ▒▒░ ▒ ░▒▓▒ ▒ ▒ ░░ ▒░ ░▒ ▒▓▒ ▒ ░  ▒ ░░   
  ▒   ▒▒ ░ ▒ ░    ░ ▒░  ░ ░░▒░ ░ ░  ░ ░  ░░ ░▒  ░ ░    ░    
  ░   ▒    ▒ ░      ░   ░  ░░░ ░ ░    ░   ░  ░  ░    ░      
      ░  ░ ░         ░       ░        ░  ░      ░           
 
 
 
"""
LOGO_ART_HEIGHT = len(LOGO_ART.strip('\n').split('\n')) + 3


class LogoWidget(Widget):
    def render(self) -> RenderableType:
        username = self.model.username or "..."
        letter_palette = ["#b0b0b0", "#a3a3a3", "#969696", "#8a8a8a"]
        drip_palette = ["#B22222", "#8B0000", "#8A0707", "#58111A"]

        colored_art_lines = []
        for line in LOGO_ART.strip('\n').split('\n'):
            text_line = Text()
            for char in line:
                if char in ['▀', '▄', '█', '▓']:
                    style = random.choice(letter_palette)
                    text_line.append(char, style=style)
                elif char in ['░', '▒']:
                    style = random.choice(drip_palette)
                    text_line.append(char, style=style)
                else:
                    text_line.append(char)
            colored_art_lines.append(text_line)

        welcome_text = Text.from_markup(f"Добро пожаловать, [bold red]{username}[/bold red]! :eye:")

        return Group(
            Align.center(Group(*colored_art_lines)),
            Align.center(Rule(style="dim red")),
            Align.center(welcome_text)
        )
