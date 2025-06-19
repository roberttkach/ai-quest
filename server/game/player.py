from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class StatusEffect:
    """Представляет статусный эффект с возможной длительностью."""
    name: str
    description: str
    duration_turns: Optional[int] = None
    is_positive: bool = False


@dataclass
class Player:
    """
    Чистая модель данных, представляющая игровое состояние игрока.
    Не содержит никакой логики, связанной с сетью или обработкой.
    """
    username: str
    location_name: Optional[str] = None
    inventory: List[str] = field(default_factory=lambda: ["фонарик"])
    status_effects: List[StatusEffect] = field(
        default_factory=lambda: [StatusEffect(name="здоров", description="В полном порядке.", is_positive=True)])
    personal_history: List[str] = field(default_factory=list)

    def reset(self):
        """Сбрасывает состояние игрока к значениям по умолчанию для лобби."""
        self.location_name = None
        self.inventory = ["фонарик"]
        self.status_effects = [StatusEffect(name="здоров", description="В полном порядке.", is_positive=True)]
        self.personal_history.clear()
