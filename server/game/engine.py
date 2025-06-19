import os
from typing import List, Set, Dict, Optional, TYPE_CHECKING

import trio

from game.state import Location
from game.player import StatusEffect
from logger import lg
from llm.prompts import construct_narration_prompt, construct_state_update_prompt

if TYPE_CHECKING:
    from handlers.player import PlayerConnection
    from main import Server


async def _write_debug_file(f_type: str, turn: int, group_name: str, content_type: str, content: str):
    base_dir = {'narration': 'prompts/narration', 'state': 'prompts/state'} if content_type == 'prompt' else {
        'narration': 'responses/narration', 'state': 'responses/state'}
    folder = base_dir.get(f_type)
    if not folder: return

    filename = ""
    try:
        filename = os.path.join(folder, f"{group_name}_turn_{turn}.txt")
        async with await trio.open_file(filename, 'w', encoding='utf-8') as f:
            await f.write(content)
    except Exception as e:
        lg.error(f"Не удалось записать отладочный файл {filename}: {e}")


class GameEngine:
    def __init__(self, server: 'Server'):
        self.server = server
        self.game_state = server.game_state
        self.model_manager = server.model_manager
        self.turn_processing_locks: Set[frozenset[str]] = set()
        self._lock = trio.Lock()
        lg.info("Игровой движок инициализирован.")

    async def handle_player_action(self, player_conn: 'PlayerConnection', action: str):
        player = await self.game_state.get_player(player_conn.username)
        if not player or not player.location_name:
            return

        location = await self.game_state.get_or_create_location(player.location_name)
        if player.username in location.pending_actions:
            await player_conn.send_direct("SYSTEM ERROR Вы уже совершили действие. Ожидайте.")
            await player_conn.send_direct("SYSTEM NARRATION_END")
            return

        location.pending_actions[player.username] = action
        location.add_player_action_to_history(player.username, action)

        component_loc_names = await self.game_state.get_connected_component(location.name)
        await self.server.broadcast_to_locations(component_loc_names, f"ACTION {player.username}: {action}")

        await self._check_and_process_all_groups()

    async def start_game(self):
        if await self.game_state.start_game():
            await self.server.broadcast_system("STATE_UPDATE ACTIVE")
            await self._narrate_initial_room_for_all()

    async def _narrate_initial_room_for_all(self):
        start_loc_name = self.game_state.start_room
        location = await self.game_state.get_or_create_location(start_loc_name)
        players_in_loc = await self.game_state.get_players_in_locations({start_loc_name})

        if players_in_loc:
            lg.info("Запуск начального повествования для стартовой комнаты.")
            for p in players_in_loc:
                if p.username not in location.pending_actions:
                    location.pending_actions[p.username] = "осматривается по сторонам"
            await self._check_and_process_all_groups()

    async def on_player_removed(self, last_location_name: Optional[str]):
        if last_location_name:
            await self._check_and_process_all_groups()

    async def _check_and_process_all_groups(self):
        async with self._lock:
            all_players = await self.game_state.get_all_players()
            if not all_players:
                return

            player_groups: Dict[frozenset[str], List[str]] = {}
            visited_players: Set[str] = set()

            for player in all_players:
                if player.username in visited_players or not player.location_name:
                    continue

                component = await self.game_state.get_connected_component(player.location_name)
                component_key = frozenset(component)

                if component_key not in player_groups:
                    player_groups[component_key] = []

                players_in_component = await self.game_state.get_players_in_locations(component)
                for p_in_comp in players_in_component:
                    if p_in_comp.username not in visited_players:
                        player_groups[component_key].append(p_in_comp.username)
                        visited_players.add(p_in_comp.username)

            for group_key, player_usernames_in_group in player_groups.items():
                if group_key in self.turn_processing_locks or not player_usernames_in_group:
                    continue

                locations_in_group = [await self.game_state.get_or_create_location(name) for name in group_key]
                turn_counters = {loc.turn_counter for loc in locations_in_group}
                is_merge_turn = len(turn_counters) > 1

                if is_merge_turn:
                    lg.warning(
                        f"!!! ОБНАРУЖЕНО СЛИЯНИЕ МИРОВ !!! Рассинхронизация ходов в группе {set(group_key)}: {turn_counters}.")

                actions_in_group = {}
                for loc in locations_in_group:
                    actions_in_group.update(loc.pending_actions)

                if len(actions_in_group) >= len(player_usernames_in_group):
                    lg.info(f"Группа {set(group_key)} готова к обработке. Запуск...")
                    self.turn_processing_locks.add(group_key)
                    self.server.nursery.start_soon(self._process_turn, locations_in_group, is_merge_turn)
                else:
                    await self.server.broadcast_to_locations(group_key, "SYSTEM NARRATION_END",
                                                             exclude=list(actions_in_group.keys()))

    async def _process_turn(self, group_locations: List[Location], is_merge_turn: bool = False):
        group_key = frozenset(loc.name for loc in group_locations)
        group_name = "_".join(sorted(group_key))
        log_turn_counter = max(loc.turn_counter for loc in group_locations) + 1

        try:
            lg.info(f"Обработка хода (лог #{log_turn_counter}) для группы '{group_name}'. Is Merge: {is_merge_turn}")
            players_in_group = await self.game_state.get_players_in_locations(group_key)
            if not players_in_group:
                lg.warning(f"Попытка обработать ход в пустой группе '{group_name}'. Отмена.")
                return

            expired_effects_messages = []
            for player in players_in_group:
                active_effects = []
                for effect in player.status_effects:
                    if effect.duration_turns is not None:
                        effect.duration_turns -= 1
                        if effect.duration_turns <= 0:
                            expired_effects_messages.append(f"Эффект '{effect.name}' на игроке {player.username} прошел.")
                            continue
                    active_effects.append(effect)
                player.status_effects = active_effects
                if not player.status_effects:
                    player.status_effects.append(StatusEffect(name="здоров", description="В полном порядке.", is_positive=True))

            if expired_effects_messages:
                main_location = group_locations[0]
                for msg in expired_effects_messages:
                    main_location.add_system_message_to_history(msg)

            if not is_merge_turn:
                for loc in group_locations: loc.turn_counter += 1

            for loc in group_locations:
                for p_name in loc.players_present:
                    if p_name not in loc.pending_actions:
                        loc.pending_actions[p_name] = "бездействует"
                        loc.add_player_action_to_history(p_name, "бездействует")
                        await self.server.broadcast_to_locations(group_key, f"ACTION {p_name}: бездействует")

            game_cfg = await self.game_state.get_full_config()

            narration_prompt = await construct_narration_prompt(
                self.game_state,
                group_locations,
                players_in_group,
                immersion_turns=game_cfg['immersion_turns'],
                story_injection_turns=game_cfg['story_injection_turns'],
                max_history_char_length=game_cfg['max_history_char_length']
            )
            await _write_debug_file('narration', log_turn_counter, group_name, 'prompt', narration_prompt)
            await self.server.broadcast_to_locations(group_key, "SYSTEM THINK_START")

            full_narration_text = ""
            async for content in self.model_manager.stream_narration(narration_prompt):
                if not self.server.nursery: break
                full_narration_text += content
                await self.server.broadcast_to_locations(group_key, f"NARRATE {content.replace(chr(10), '<<BR>>')}")

            await _write_debug_file('narration', log_turn_counter, group_name, 'response', full_narration_text)
            if not full_narration_text.strip():
                lg.warning("Модель вернула пустое повествование. Ход завершается.")
            else:
                for loc in group_locations:
                    loc.add_narration_to_history(full_narration_text)
                await self.server.broadcast_to_locations(group_key, "SYSTEM STATE_THINK_START")

                state_update_prompt = construct_state_update_prompt(self.game_state, group_locations, players_in_group,
                                                                    full_narration_text)
                await _write_debug_file('state', log_turn_counter, group_name, 'prompt', state_update_prompt)

                state_changes, raw_response = await self.model_manager.get_state_changes_from_narration(
                    state_update_prompt)
                await _write_debug_file('state', log_turn_counter, group_name, 'response', raw_response)

                if state_changes:
                    moved_players, new_conn = await self.game_state.apply_turn_changes(state_changes)
                    if moved_players or new_conn:
                        lg.info("Перемещение игроков или создание связи вызвало повторную проверку групп.")
                        await self._check_and_process_all_groups()
                else:
                    lg.warning(f"Не удалось получить изменения состояния от модели для группы {group_name}.")
        except Exception as e:
            lg.error(f"Ошибка во время обработки хода для '{group_name}': {e}", exc_info=True)
            await self.server.broadcast_to_locations(group_key, "SYSTEM Произошла ошибка с Рассказчиком. Ход прерван.")
        finally:
            if is_merge_turn:
                final_turn = max(loc.turn_counter for loc in group_locations) + 1
                for loc in group_locations: loc.turn_counter = final_turn
                lg.info(f"Счетчики ходов для группы {group_key} СИНХРОНИЗИРОВАНЫ на {final_turn}.")

            await self.server.broadcast_to_locations(group_key, "SYSTEM NARRATION_END")
            for loc in group_locations:
                loc.clear_turn_data()

            async with self._lock:
                self.turn_processing_locks.discard(group_key)
