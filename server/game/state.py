from typing import Any, Dict, List, Optional, TYPE_CHECKING, Set

import trio

from ..logger import lg
from .stories import STORIES
from ..config import DEFAULT_FEAR_WEIGHTS

if TYPE_CHECKING:
    from ..handlers.player import PlayerConnection


class GameState:
    def __init__(self):
        self._lock = trio.Lock()
        self.state: str = 'lobby'
        self.players: Dict[str, 'PlayerConnection'] = {}
        self.story_data: Dict[str, Any] = STORIES
        self.conversation_histories: Dict[str, List[str]] = {room: [] for room in self.story_data.keys()}
        self.room_turn_counters: Dict[str, int] = {}
        # Новое состояние для отслеживания использованных идей
        self.used_story_elements: Dict[str, Set[str]] = {}
        self.start_room: str = 'endless_metro'
        self.game_mode: str = 'приключение'
        self.fear_weights: Dict[str, int] = DEFAULT_FEAR_WEIGHTS.copy()
        lg.info("Объект GameState инициализирован.")

    async def add_player(self, player_connection: 'PlayerConnection') -> bool:
        """Атомарно проверяет и добавляет объект PlayerConnection."""
        async with self._lock:
            username = player_connection.username
            if not username:
                lg.warning("Попытка добавить игрока без имени.")
                return False
            if username in self.players:
                lg.warning(f"Попытка добавить игрока с уже существующим именем '{username}' отклонена.")
                return False

            room = self.start_room if self.state == 'active' else 'lobby'
            player_connection.current_room = room
            self.players[username] = player_connection

            if room != 'lobby':
                entry = f"SYSTEM {username} появляется."
                self.conversation_histories.setdefault(room, []).append(entry)
                lg.debug(f"Добавлена запись в историю комнаты '{room}': '{entry}'")

            lg.info(f"Игрок '{username}' добавлен в игру. Текущая комната: '{room}'.")
            return True

    async def remove_player(self, username: str) -> Optional[str]:
        """Удаляет игрока из игры и возвращает его комнату."""
        async with self._lock:
            player_conn = self.players.pop(username, None)
            if player_conn:
                room = player_conn.current_room
                lg.info(f"Игрок '{username}' удаляется из игры из комнаты '{room}'.")
                if room and room != 'lobby':
                    entry = f"SYSTEM {username} исчезает."
                    self.conversation_histories.setdefault(room, []).append(entry)
                    lg.debug(f"Добавлена запись в историю комнаты '{room}': '{entry}'")
                return room
            lg.warning(f"Попытка удалить несуществующего игрока '{username}'.")
            return None

    async def get_player_connection(self, username: str) -> Optional['PlayerConnection']:
        """Возвращает объект PlayerConnection по имени пользователя."""
        async with self._lock:
            return self.players.get(username)

    async def get_player_room(self, username: str) -> Optional[str]:
        """Возвращает текущую комнату игрока."""
        async with self._lock:
            player = self.players.get(username)
            return player.current_room if player else None

    async def get_players_in_room(self, room_name: str) -> List['PlayerConnection']:
        """Возвращает список объектов PlayerConnection в указанной комнате."""
        async with self._lock:
            players = [p for p in self.players.values() if p.current_room == room_name]
            lg.debug(f"В комнате '{room_name}' найдено {len(players)} игроков.")
            return players

    async def get_all_players(self) -> List['PlayerConnection']:
        """Возвращает список всех объектов PlayerConnection."""
        async with self._lock:
            return list(self.players.values())

    async def get_connected_usernames(self) -> List[str]:
        """Возвращает список имен всех подключенных игроков."""
        async with self._lock:
            return list(self.players.keys())

    async def reset_to_lobby(self):
        """Сбрасывает состояние игры в лобби."""
        async with self._lock:
            lg.info("Сброс состояния игры в 'лобби'.")
            self.state = 'lobby'
            self.conversation_histories = {room: [] for room in self.story_data.keys()}
            self.room_turn_counters = {}
            self.used_story_elements = {}
            lg.debug("Истории, счетчики ходов и использованные элементы всех комнат очищены.")
            for player in self.players.values():
                player.current_room = 'lobby'
            lg.info(f"Все {len(self.players)} игроков перемещены в 'лобби'.")

    async def start_game(self) -> bool:
        """Начинает игру, перемещая игроков из лобби."""
        async with self._lock:
            if self.state != 'lobby':
                lg.warning(f"Попытка начать игру, когда состояние не 'лобби' (текущее: '{self.state}').")
                return False
            self.state = 'active'
            lg.info(
                f"Состояние игры изменено на 'active'. Перемещение игроков в стартовую комнату '{self.start_room}'.")
            for player in self.players.values():
                if player.current_room == 'lobby':
                    player.current_room = self.start_room
            return True

    async def add_player_action_to_history(self, username: str, action: str):
        """Добавляет действие игрока в историю комнаты."""
        async with self._lock:
            player = self.players.get(username)
            if not player or not player.current_room:
                lg.warning(f"Не удалось добавить действие в историю для '{username}', игрок или комната не найдены.")
                return
            room = player.current_room
            if room != 'lobby':
                entry = f"CHAT {username}: {action}"
                self.conversation_histories.setdefault(room, []).append(entry)
                lg.debug(f"В историю комнаты '{room}' добавлено действие от '{username}': '{action[:50]}...'")

    async def add_narration_to_history(self, room: str, narration: str):
        """Добавляет повествование Рассказчика в историю комнаты."""
        async with self._lock:
            if room != 'lobby':
                narration_clean = narration.strip()
                if not narration_clean: return

                entry = f"NARRATE {narration_clean}"
                self.conversation_histories.setdefault(room, []).append(entry)
                lg.debug(f"В историю комнаты '{room}' добавлено повествование: '{narration_clean[:50]}...'")

    async def get_room_story(self, room_name: str) -> str:
        async with self._lock:
            return self.story_data.get(room_name, {}).get('initial_description', "Вы в месте без описания.")

    async def get_room_details(self, room_name: str) -> Dict[str, Any]:
        async with self._lock:
            return self.story_data.get(room_name, {}).get('details', {})

    async def get_full_story(self, room_name: str) -> Optional[Dict[str, Any]]:
        """Возвращает полный словарь данных для указанной комнаты."""
        async with self._lock:
            return self.story_data.get(room_name)

    async def get_room_conversation_history(self, room_name: str, limit: int = 10) -> List[str]:
        async with self._lock:
            history = self.conversation_histories.get(room_name, [])
            return history[-limit:]

    async def get_turn_count(self, room: str) -> int:
        """Получает текущее количество ходов в комнате."""
        async with self._lock:
            return self.room_turn_counters.get(room, 0)

    async def increment_turn_counter(self, room: str):
        """Увеличивает счетчик ходов для комнаты на один."""
        async with self._lock:
            current_count = self.room_turn_counters.get(room, 0)
            self.room_turn_counters[room] = current_count + 1
            lg.info(f"Счетчик ходов для комнаты '{room}' увеличен до {current_count + 1}.")

    async def get_used_story_elements(self, room: str) -> Set[str]:
        """Возвращает множество уже использованных идей для комнаты."""
        async with self._lock:
            return self.used_story_elements.get(room, set()).copy()

    async def add_used_story_elements(self, room: str, elements: List[str]):
        """Добавляет список новых идей в множество использованных для комнаты."""
        async with self._lock:
            if room not in self.used_story_elements:
                self.used_story_elements[room] = set()
            self.used_story_elements[room].update(elements)
            lg.debug(f"В комнате '{room}' добавлено {len(elements)} новых использованных элементов.")

    async def get_stats(self) -> str:
        async with self._lock:
            player_count = len(self.players)
            stats_str = (f"Всего игроков: {player_count}\n"
                         f"Режим игры: {self.game_mode}\n"
                         f"Состояние: {self.state}")
            lg.debug(f"Сформирована статистика: {stats_str.replace(chr(10), ', ')}")
            return stats_str

    async def is_game_active(self) -> bool:
        async with self._lock: return self.state == 'active'

    async def set_game_mode(self, mode: str):
        async with self._lock:
            lg.info(f"Режим игры изменен на '{mode}'.")
            self.game_mode = mode

    async def get_game_mode(self) -> str:
        async with self._lock: return self.game_mode
