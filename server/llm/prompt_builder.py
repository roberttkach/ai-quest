import random
from typing import Any, Dict, List

from .. import config
from ..game.state import GameState
from ..logger import lg
from . import templates


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


async def _get_dynamic_focus_elements(game_state: GameState, story_data: Dict[str, Any], room_name: str) -> str:
    """
    Создает список элементов для фокуса сцены, избегая повторений.
    Использует статичные веса страхов и отслеживает использованные элементы через GameState.
    """
    weights_dict = game_state.fear_weights
    fear_types_population = list(weights_dict.keys())
    fear_weights = list(weights_dict.values())

    all_sources = {}
    details = story_data.get('details', {})
    events = story_data.get('events', {})
    for fear_type in fear_types_population:
        all_sources.setdefault(fear_type, {})
        for category in ALL_ELEMENT_CATEGORIES.keys():
            source_dict = details if category in details.get(fear_type, {}) else events
            all_sources[fear_type][category] = source_dict.get(fear_type, {}).get(category, [])

    selected_elements_text: List[str] = []
    newly_used_items: List[str] = []

    used_items = await game_state.get_used_story_elements(room_name)

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
                lg.warning(f"Не удалось найти уникальный элемент для категории '{category_key}'. Пул исчерпан.")

    if newly_used_items:
        await game_state.add_used_story_elements(room_name, newly_used_items)

    lg.debug(f"Выбраны следующие динамические элементы для промпта: {selected_elements_text}")
    return "\n".join(selected_elements_text)


async def construct_prompt(username: str, game_state: GameState) -> str:
    """
    Создает расширенный промпт для ИИ-рассказчика на основе текущего состояния игры,
    используя динамически выбираемые элементы сцены только в течение первых ходов.
    """
    current_room = await game_state.get_player_room(username)
    if not current_room or current_room == 'lobby':
        lg.warning(f"Невозможно создать промпт для {username} в комнате '{current_room}'.")
        return ""

    conversation_history_list = await game_state.get_room_conversation_history(current_room, limit=12)
    turn_count = await game_state.get_turn_count(current_room)
    players_in_room_data = await game_state.get_players_in_room(current_room)
    players_in_room = [p.username for p in players_in_room_data if p.username]
    full_story_data = await game_state.get_full_story(current_room)

    situation_content = f"- ИГРОКИ: {', '.join(players_in_room)}"

    scene_focus_prompt = ""
    if turn_count < config.STORY_INJECTION_TURNS:
        lg.debug(f"Ход #{turn_count}, добавляем идеи из stories.py.")
        if full_story_data:
            scene_focus_prompt = await _get_dynamic_focus_elements(game_state, full_story_data, current_room)
    else:
        lg.debug(f"Ход #{turn_count}, идеи из stories.py больше не добавляются.")

    if not conversation_history_list:
        initial_description = await game_state.get_room_story(current_room)
        conversation_history = f"SYSTEM Мир вокруг: {initial_description}"
    else:
        conversation_history = '\n'.join(conversation_history_list)

    # Используем константу из конфига
    if turn_count < config.IMMERSION_TURNS:
        principles_header = templates.IMMERSION_HEADER
        principles_to_use = templates.IMMERSION_PRINCIPLES
        lg.debug(f"Используются принципы погружения (ход #{turn_count}).")
    else:
        principles_header = templates.PRINCIPLES_HEADER
        principles_to_use = templates.NARRATIVE_PRINCIPLES
        lg.debug(f"Используются стандартные принципы режиссуры (ход #{turn_count}).")

    content_blocks = []
    content_blocks.append(("ТЕКУЩАЯ СИТУАЦИЯ:", situation_content))
    if scene_focus_prompt:
        content_blocks.append((templates.SCENE_FOCUS_HEADER, scene_focus_prompt))
    content_blocks.append((templates.CONVERSATION_HISTORY_HEADER, conversation_history))
    content_blocks.append((principles_header, "\n".join(principles_to_use)))

    prompt_sections = [
        "### Инструкция:",
        templates.NARRATOR_INSTRUCTION,
    ]

    for i, (header, content) in enumerate(content_blocks, start=1):
        prompt_sections.append(f"{i}. {header}\n{content}")

    prompt_sections.append("### Ответ:\n<｜Assistant｜>")

    final_prompt = "\n\n".join(filter(None, prompt_sections))
    lg.debug(f"Создан промпт для {username} в комнате {current_room}:\n{final_prompt}")
    return final_prompt
