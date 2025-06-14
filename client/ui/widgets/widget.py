from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from rich.console import RenderableType

if TYPE_CHECKING:
    from model import ClientDataModel


class Widget(ABC):
    def __init__(self, model: "ClientDataModel"):
        self.model = model

    @abstractmethod
    def render(self) -> RenderableType:
        pass
