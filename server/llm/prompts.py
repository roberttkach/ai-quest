import json
import random
from typing import Any, Dict, List, Set

from game.player import Player
from game.state import GameState, Location
from logger import lg
from llm import templates

ALL_ELEMENT_CATEGORIES = {
    'sounds': 'ЗВУК',
    'sights': 'ОБРАЗ',
    'sensations': 'ОЩУЩЕНИЕ',
    'psychological_effects': 'ЭФФЕКТ',
    'unsettling_discovery': 'НАХОДКА',
    'warning_sign': 'ЗНАК',
    'mysterious_encounter': 'ВСТРЕЧА',
}

FIXED_ELEMENT_STRUCTURE = {
    'sounds': 2,
    'sights': 1,
    'sensations': 1,
    'psychological_effects': 1,
    'unsettling_discovery': 1,
    'warning_sign': 1,
    'mysterious_encounter': 1,
}


def _get_connections_in_group(game_state: GameState, locations: List[Location]) -> List[List[str]]:
    """Возвращает список уникальных связей между локациями внутри заданной группы."""
    loc_names_in_group = {loc.name for loc in locations}
    connection_pairs: Set[frozenset[str]] = set()
    for loc in locations:
        for neighbor in game_state.location_graph.get(loc.name, set()):
            if neighbor in loc_names_in_group:
                connection_pairs.add(frozenset([loc.name, neighbor]))
    return [sorted(list(pair)) for pair in connection_pairs]


async def _select_and_update_focus_elements(game_state: GameState, story_data: Dict[str, Any],
                                            location: Location) -> str:
    """
    Выбирает динамические элементы для сцены и обновляет список использованных элементов в локации.
    """
    weights_dict = game_state.fear_weights
    fear_types_population = list(weights_dict.keys())
    fear_weights = list(weights_dict.values())
    all_sources: Dict[str, Dict[str, List[str]]] = {}
    details = story_data.get('details', {})
    events = story_data.get('events', {})
    for fear_type in fear_types_population:
        all_sources.setdefault(fear_type, {})
        for category in ALL_ELEMENT_CATEGORIES.keys():
            source_dict = details if category in details.get(fear_type, {}) else events
            all_sources[fear_type][category] = source_dict.get(fear_type, {}).get(category, [])

    selected_elements_text: List[str] = []
    used_items = location.used_story_elements.copy()
    newly_used_items: List[str] = []

    for category_key, count in FIXED_ELEMENT_STRUCTURE.items():
        for _ in range(count):
            chosen_item = None
            try:
                fear_type = random.choices(fear_types_population, weights=fear_weights, k=1)[0]
                pool = all_sources.get(fear_type, {}).get(category_key, [])
                available_items = [item for item in pool if item not in used_items]
                if available_items:
                    chosen_item = random.choice(available_items)
            except (ValueError, IndexError):
                pass

            if not chosen_item:
                shuffled_fear_types = random.sample(fear_types_population, len(fear_types_population))
                for fear_type in shuffled_fear_types:
                    pool = all_sources.get(fear_type, {}).get(category_key, [])
                    available_items = [item for item in pool if item not in used_items]
                    if available_items:
                        chosen_item = random.choice(available_items)
                        break

            if chosen_item:
                label = ALL_ELEMENT_CATEGORIES[category_key]
                selected_elements_text.append(f"- {label}: {chosen_item}")
                used_items.add(chosen_item)
                newly_used_items.append(chosen_item)
            else:
                lg.warning(f"Пул исчерпан для категории '{category_key}' в локации '{location.name}'.")

    if newly_used_items:
        location.used_story_elements.update(newly_used_items)
    lg.debug(f"Выбраны динамические элементы для промпта: {selected_elements_text}")
    return "\n".join(selected_elements_text)


async def construct_narration_prompt(game_state: GameState, locations: List[Location],
                                     players: List[Player], immersion_turns: int,
                                     story_injection_turns: int, max_history_char_length: int) -> str:
    """Создает промпт для генерации повествования для группы связанных локаций."""
    player_states = [{"username": p.username, "inventory": p.inventory, "status": p.status} for p in players]
    location_group_info = [
        {"name": loc.name, "description": loc.description,
         "players_present": sorted(list(loc.players_present)), "turn_count": loc.turn_counter}
        for loc in locations
    ]
    connections_list = _get_connections_in_group(game_state, locations)

    state_json_data: Dict[str, Any] = {
        "location_group": location_group_info, "connections": connections_list, "players": player_states
    }

    story_data = game_state.story_data.get(locations[0].name, {})
    if story_data.get('use_world_flags'):
        state_json_data['world_flags'] = game_state.world_flags
    state_json_str = json.dumps(state_json_data, indent=2, ensure_ascii=False)

    conversation_history_parts = []
    player_actions_map = {}
    for loc in locations:
        history = '\n'.join(loc.conversation_history[-15:])
        conversation_history_parts.append(f"#### Из локации: {loc.name}\n{history}")
        player_actions_map.update(loc.pending_actions)
    conversation_history = '\n\n'.join(conversation_history_parts)

    if len(conversation_history) > max_history_char_length:
        trimmed_history = conversation_history[-max_history_char_length:]
        first_newline_pos = trimmed_history.find('\n')
        final_trimmed_history = trimmed_history[first_newline_pos + 1:] if first_newline_pos != -1 else trimmed_history
        conversation_history = f"[...история была обрезана...]\n{final_trimmed_history}"
        lg.info(f"История диалогов была обрезана до ~{max_history_char_length} символов.")

    player_actions_str = "\n".join(
        [f"- {name}: {action}" for name, action in player_actions_map.items()]
    ) or "- Игроки бездействуют, осматриваясь по сторонам."

    scene_focus_prompt = ""
    main_location = locations[0]
    if main_location.turn_counter < story_injection_turns and story_data:
        scene_focus_prompt = await _select_and_update_focus_elements(game_state, story_data, main_location)

    principles_header, principles_to_use = (templates.IMMERSION_HEADER,
                                            templates.IMMERSION_PRINCIPLES) if main_location.turn_counter < immersion_turns else (
        templates.PRINCIPLES_HEADER, templates.NARRATIVE_PRINCIPLES)

    prompt_sections = [
        "### Инструкция:", templates.NARRATOR_INSTRUCTION,
        "### ТЕКУЩЕЕ СОСТОЯНИЕ МИРА И ИГРОКОВ (JSON):", f"```json\n{state_json_str}\n```",
        "### ДЕЙСТВИЯ ИГРОКОВ В ЭТОМ ХОДЕ:", player_actions_str,
    ]
    if scene_focus_prompt:
        prompt_sections.append(f"### {templates.SCENE_FOCUS_HEADER}\n{scene_focus_prompt}")
    prompt_sections.extend([
        f"### {templates.CONVERSATION_HISTORY_HEADER}\n{conversation_history}",
        f"### {principles_header}\n" + "\n\n".join(principles_to_use),
        "### Ответ (только повествовательный текст):"
    ])
    return "\n\n".join(prompt_sections)


def construct_state_update_prompt(game_state: GameState, locations: List[Location], players: List[Player],
                                  full_narration: str) -> str:
    """Создает промпт для извлечения изменений состояния в формате JSON для группы локаций."""
    player_states = [{"username": p.username, "inventory": p.inventory, "status": p.status} for p in players]
    location_group_info = [{"name": loc.name, "description": loc.description} for loc in locations]
    connections_list = _get_connections_in_group(game_state, locations)

    state_json_data: Dict[str, Any] = {
        "location_group": location_group_info, "connections": connections_list, "players": player_states,
    }
    if game_state.story_data.get(locations[0].name, {}).get('use_world_flags'):
        state_json_data['world_flags'] = game_state.world_flags

    state_json_str = json.dumps(state_json_data, indent=2, ensure_ascii=False)
    json_schema_str = json.dumps(templates.STATE_CHANGE_SCHEMA, indent=2, ensure_ascii=False)

    tool_instruction = (
        "Проанализируй ИСХОДНОЕ СОСТОЯНИЕ и НОВОЕ ПОВЕСТВОВАНИЕ. "
        "Верни JSON-объект, отражающий ВСЕ изменения, строго следуя схеме.\n"
        "Ключевые моменты:\n"
        "1.  `player_updates`: Заполняй для каждого игрока, чье состояние изменилось.\n"
        "2.  `location_updates`: Используй `change_type: 'UPDATE_DESCRIPTION'` для изменения локации, `change_type: 'CREATE'` для новой.\n"
        "3.  `connection_updates`: **ВАЖНО!** Создавай связь (`action: 'CREATE'`) только если действие явно и физически соединяет две локации (открыл дверь, проломил стену). **НЕ СОЗДАВАЙ СВЯЗЬ** при мистическом перемещении (телепорт, потеря сознания). В таких случаях просто используй `move_to_location`.\n"
        "4.  Если изменений нет, верни пустой JSON-объект `{}`."
    )

    prompt_sections = [
        "### Инструкция:", tool_instruction,
        "### Схема JSON для ответа:", f"```json\n{json_schema_str}\n```",
        f"### ИСХОДНОЕ СОСТОЯНИЕ (JSON):", f"```json\n{state_json_str}\n```",
        f"### НОВОЕ ПОВЕСТВОВАНИЕ ДЛЯ АНАЛИЗА:\n---\n{full_narration}\n---",
        "### Ответ (только JSON-объект, обернутый в ```json ... ```):"
    ]
    return "\n\n".join(prompt_sections)
