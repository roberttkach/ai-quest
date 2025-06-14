from typing import Any, Dict, List, Optional, Set, Tuple, Iterable

import trio

import config
from logger import lg
from game.player import Player
from game.stories import STORIES


class Location:
    """Представляет общее, разделяемое пространство в игре."""

    def __init__(self, name: str, initial_description: str):
        self.name = name
        self.description: str = initial_description
        self.players_present: Set[str] = set()
        self.conversation_history: List[str] = [f"SYSTEM Мир вокруг: {initial_description}"]
        self.used_story_elements: Set[str] = set()
        self.turn_counter: int = 0
        self.pending_actions: Dict[str, str] = {}
        lg.info(f"Объект Location '{name}' создан.")

    def add_player(self, username: str):
        self.players_present.add(username)
        self.add_system_message_to_history(f"{username} появляется.")

    def remove_player(self, username: str):
        self.players_present.discard(username)
        self.pending_actions.pop(username, None)
        self.add_system_message_to_history(f"{username} исчезает.")

    def add_player_action_to_history(self, username: str, action: str):
        entry = f"ACTION {username}: {action}"
        self.conversation_history.append(entry)
        lg.debug(f"В историю локации '{self.name}' добавлено действие от '{username}': '{action[:50]}...'")

    def add_narration_to_history(self, narration: str):
        narration_clean = narration.strip()
        if not narration_clean: return
        entry = f"NARRATE {narration_clean}"
        self.conversation_history.append(entry)
        lg.debug(f"В историю локации '{self.name}' добавлено повествование: '{narration_clean[:50]}...'")

    def add_system_message_to_history(self, message: str):
        entry = f"SYSTEM {message}"
        self.conversation_history.append(entry)
        lg.debug(f"В историю локации '{self.name}' добавлено системное сообщение: '{message}'")

    def clear_turn_data(self):
        self.pending_actions.clear()
        lg.debug(f"Данные хода для локации '{self.name}' очищены.")


class GameState:
    """
    Центральное хранилище состояния игрового мира.
    Оперирует чистыми моделями данных (Player, Location) и не зависит от сетевого слоя.
    """
    def __init__(self):
        self._lock = trio.Lock()
        self.state: str = 'lobby'
        self.players: Dict[str, Player] = {}
        self.locations: Dict[str, Location] = {}
        self.location_graph: Dict[str, Set[str]] = {}
        self.story_data: Dict[str, Any] = STORIES
        self.start_room: str = 'endless_metro'
        self.fear_weights: Dict[str, int] = config.DEFAULT_FEAR_WEIGHTS.copy()
        self.story_injection_turns: int = config.STORY_INJECTION_TURNS
        self.immersion_turns: int = config.IMMERSION_TURNS
        self.max_history_char_length: int = config.MAX_HISTORY_CHAR_LENGTH
        self.world_flags: Dict[str, Any] = {}
        lg.info("Объект GameState инициализирован с новой архитектурой на основе графа связности.")

    def _get_or_create_location_unsafe(self, location_name: str) -> Location:
        """Внутренний метод: создает локацию, предполагает, что блокировка уже захвачена."""
        if location_name not in self.locations:
            lg.info(f"Локация '{location_name}' не найдена, создается новая (unsafe).")
            initial_desc = self.story_data.get(location_name, {}).get('initial_description', 'Пустое место.')
            self.locations[location_name] = Location(name=location_name, initial_description=initial_desc)
            self.location_graph[location_name] = set()
            lg.info(f"Создана новая локация: {location_name} и узел в графе мира.")
        return self.locations[location_name]

    async def get_or_create_location(self, location_name: str) -> Location:
        """Публичный, потокобезопасный метод для получения или создания локации."""
        async with self._lock:
            return self._get_or_create_location_unsafe(location_name)

    async def add_player(self, player: Player) -> Tuple[bool, str]:
        """
        Атомарно проверяет и добавляет модель Player.
        Возвращает (True, "success") при успехе.
        Возвращает (False, "reason") при неудаче.
        """
        async with self._lock:
            username = player.username
            if len(self.players) >= config.MAX_PLAYERS:
                lg.warning(f"Отклонено подключение для '{username}': сервер полон ({len(self.players)}/{config.MAX_PLAYERS}).")
                return False, "full"

            if username in self.players:
                lg.warning(f"Попытка добавить игрока с уже существующим именем '{username}' отклонена.")
                return False, "taken"

            self.players[username] = player

            if self.state == 'active':
                location_name = self.start_room
                player.location_name = location_name
                location = self._get_or_create_location_unsafe(location_name)
                location.add_player(username)
                lg.info(f"Игрок '{username}' добавлен в игру. Текущая локация: '{location_name}'.")
            else:
                player.location_name = None
                lg.info(f"Игрок '{username}' добавлен в лобби.")

            return True, "success"

    async def remove_player(self, username: str) -> Optional[str]:
        """Удаляет игрока из игры и возвращает имя его последней известной локации."""
        async with self._lock:
            player_model = self.players.pop(username, None)
            if player_model:
                location_name = player_model.location_name
                lg.info(f"Игрок '{username}' удаляется из игры из локации '{location_name}'.")
                if location_name and location_name in self.locations:
                    self.locations[location_name].remove_player(username)
                return location_name
            lg.warning(f"Попытка удалить несуществующего игрока '{username}'.")
            return None

    async def apply_turn_changes(self, state_changes: Dict[str, Any]) -> Tuple[
        List[Tuple[Player, Optional[str]]], bool]:
        """
        Атомарно применяет все изменения состояния после хода.
        Возвращает кортеж: (список перемещенных игроков (моделей), флаг создания новой связи).
        """
        moved_players_info: List[Tuple[Player, Optional[str]]] = []
        new_connection_created = False

        async with self._lock:
            lg.info(f"Применение изменений хода к миру: {state_changes}")

            if location_updates := state_changes.get('location_updates'):
                for update in location_updates:
                    loc_name = update.get('location_name')
                    if not loc_name: continue
                    location = self._get_or_create_location_unsafe(loc_name)
                    if 'description' in update:
                        location.description = update['description']
                        lg.info(f"Описание локации '{loc_name}' обновлено/создано.")

            if connection_updates := state_changes.get('connection_updates'):
                for conn_update in connection_updates:
                    action = conn_update.get('action')
                    locs = conn_update.get('locations')
                    if not all([action, isinstance(locs, list), len(locs) == 2]):
                        lg.warning(f"Пропущен неполный connection_update: {conn_update}")
                        continue
                    loc1_name, loc2_name = locs[0], locs[1]

                    self._get_or_create_location_unsafe(loc1_name)
                    self._get_or_create_location_unsafe(loc2_name)

                    if action == 'CREATE':
                        self.location_graph[loc1_name].add(loc2_name)
                        self.location_graph[loc2_name].add(loc1_name)
                        new_connection_created = True
                        lg.info(f"Создана связь между '{loc1_name}' и '{loc2_name}'.")
                    elif action == 'DESTROY':
                        self.location_graph[loc1_name].discard(loc2_name)
                        self.location_graph[loc2_name].discard(loc1_name)
                        lg.info(f"Разорвана связь между '{loc1_name}' и '{loc2_name}'.")

            if flags_update := state_changes.get('world_flags_update'):
                self.world_flags.update(flags_update)
                lg.info(f"Глобальные флаги обновлены: {flags_update}")

            if player_updates := state_changes.get('player_updates'):
                for p_update in player_updates:
                    username = p_update.get('username')
                    player = self.players.get(username)
                    if not player:
                        lg.warning(f"Не удалось применить изменения: игрок '{username}' не найден.")
                        continue

                    if 'inventory_add' in p_update:
                        player.inventory.extend(
                            item for item in p_update['inventory_add'] if item not in player.inventory)
                    if 'inventory_remove' in p_update:
                        player.inventory = [item for item in player.inventory if
                                            item not in p_update['inventory_remove']]
                    if 'status_update' in p_update and isinstance(p_update['status_update'], list):
                        player.status = p_update['status_update']

                    if new_location_name := p_update.get("move_to_location"):
                        await self._move_player_to_location_unsafe(player, new_location_name, moved_players_info)

        return moved_players_info, new_connection_created

    async def _move_player_to_location_unsafe(self, player: Player, new_location_name: str,
                                              moved_players_info: List[Tuple[Player, Optional[str]]]):
        """
        Внутренний небезопасный метод для перемещения игрока. Предполагает, что блокировка уже захвачена.
        """
        old_location_name = player.location_name
        lg.info(f"Перемещение игрока '{player.username}' из '{old_location_name}' в '{new_location_name}' (unsafe).")

        if old_location_name and old_location_name in self.locations:
            self.locations[old_location_name].remove_player(player.username)

        player.location_name = new_location_name
        new_location = self._get_or_create_location_unsafe(new_location_name)
        new_location.add_player(player.username)

        moved_players_info.append((player, old_location_name))

    async def get_connected_component(self, start_location_name: str) -> Set[str]:
        """Находит все связанные локации, начиная с заданной, используя поиск в ширину (BFS)."""
        async with self._lock:
            if start_location_name not in self.location_graph:
                return {start_location_name}

            visited: Set[str] = set()
            queue: List[str] = [start_location_name]
            while queue:
                current_loc = queue.pop(0)
                if current_loc not in visited:
                    visited.add(current_loc)
                    for neighbor in self.location_graph.get(current_loc, set()):
                        if neighbor not in visited:
                            queue.append(neighbor)
            return visited

    async def get_player(self, username: str) -> Optional[Player]:
        async with self._lock:
            return self.players.get(username)

    async def get_players_in_locations(self, location_names: Iterable[str]) -> List[Player]:
        """Возвращает список моделей Player в указанных локациях."""
        async with self._lock:
            players_found: List[Player] = []
            for name in location_names:
                location = self.locations.get(name)
                if location:
                    players_found.extend(
                        self.players[uname] for uname in location.players_present if uname in self.players)
            return players_found

    async def get_all_players(self) -> List[Player]:
        async with self._lock:
            return list(self.players.values())

    async def get_connected_usernames(self) -> List[str]:
        async with self._lock:
            return list(self.players.keys())

    async def reset_to_lobby(self):
        """Сбрасывает состояние игры в лобби."""
        async with self._lock:
            lg.info("Сброс состояния игры в 'лобби'.")
            self.state = 'lobby'
            self.locations.clear()
            self.location_graph.clear()
            self.world_flags.clear()
            lg.debug("Все локации, связи и глобальные флаги очищены.")
            for player in self.players.values():
                player.reset()
            lg.info(f"Все {len(self.players)} игроков перемещены в 'лобби', их состояние сброшено.")

    async def start_game(self) -> bool:
        """Начинает игру, перемещая игроков из лобби."""
        async with self._lock:
            if self.state != 'lobby':
                lg.warning(f"Попытка начать игру, когда состояние не 'лобби' (текущее: '{self.state}').")
                return False
            self.state = 'active'
            lg.info(
                f"Состояние игры изменено на 'active'. Перемещение игроков в стартовую комнату '{self.start_room}'.")
            start_location = self._get_or_create_location_unsafe(self.start_room)
            for player in self.players.values():
                player.location_name = self.start_room
                start_location.add_player(player.username)
            return True

    async def get_stats(self) -> Dict[str, Any]:
        async with self._lock:
            player_count = len(self.players)
            location_count = len(self.locations)
            connection_count = sum(len(v) for v in self.location_graph.values()) // 2
            return {
                "player_count": player_count,
                "location_count": location_count,
                "connection_count": connection_count,
                "state": self.state,
                "world_flags": self.world_flags or "Нет"
            }

    async def is_game_active(self) -> bool:
        async with self._lock:
            return self.state == 'active'

    async def set_fear_weights(self, new_weights: Dict[str, int]):
        async with self._lock:
            self.fear_weights = new_weights
            lg.info(f"Веса страха обновлены администратором: {new_weights}")

    async def set_game_variable(self, var_name: str, value: int):
        async with self._lock:
            if hasattr(self, var_name):
                setattr(self, var_name, value)
                lg.info(f"Игровая переменная '{var_name}' обновлена на {value}")
            else:
                lg.warning(f"Попытка установить несуществующую переменную '{var_name}'")

    async def get_full_config(self) -> Dict[str, Any]:
        """Возвращает словарь с текущими настраиваемыми параметрами."""
        async with self._lock:
            return {
                "fear_weights": self.fear_weights.copy(),
                "story_injection_turns": self.story_injection_turns,
                "immersion_turns": self.immersion_turns,
                "max_history_char_length": self.max_history_char_length,
            }
