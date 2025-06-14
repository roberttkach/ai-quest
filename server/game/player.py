from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Player:
    """
    Чистая модель данных, представляющая игровое состояние игрока.
    Не содержит никакой логики, связанной с сетью или обработкой.
    """
    username: str
    location_name: Optional[str] = None
    inventory: List[str] = field(default_factory=lambda: ["фонарик"])
    status: List[str] = field(default_factory=lambda: ["здоров"])
    personal_history: List[str] = field(default_factory=list)

    def reset(self):
        """Сбрасывает состояние игрока к значениям по умолчанию для лобби."""
        self.location_name = None
        self.inventory = ["фонарик"]
        self.status = ["здоров"]
        self.personal_history.clear()
