import json
import re
from typing import AsyncGenerator, Dict, Optional, Any, Tuple, List

import trio
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from rich.console import Console

import config
from logger import lg

console = Console()


class ModelManager:
    """Управляет жизненным циклом и взаимодействием с Deepseek API, используя разные модели для разных задач."""

    def __init__(self):
        self.client: Optional[AsyncOpenAI] = None
        self._lock = trio.Lock()
        self.narrator_model_name = config.NARRATOR_MODEL_NAME
        self.analyzer_model_name = config.ANALYZER_MODEL_NAME
        self.narrator_params: Dict[str, Any] = {
            "temperature": 0.55,
            "top_p": 0.94,
            "frequency_penalty": 1.2,
        }
        self.analyzer_params: Dict[str, Any] = {
            "temperature": 0.1,
        }

        lg.info("ModelManager инициализирован с раздельной конфигурацией для повествования и анализа.")

    @property
    def is_model_loaded(self) -> bool:
        return self.client is not None

    async def set_model(self, model_type: str, model_name: str) -> bool:
        """Безопасно изменяет имя модели для 'narrator' или 'analyzer'."""
        async with self._lock:
            if model_type == 'narrator':
                self.narrator_model_name = model_name
                lg.info(f"Модель Рассказчика изменена на: {model_name}")
                return True
            elif model_type == 'analyzer':
                self.analyzer_model_name = model_name
                lg.info(f"Модель Анализатора изменена на: {model_name}")
                return True
        return False

    async def get_models(self) -> Dict[str, str]:
        """Возвращает текущие используемые модели."""
        async with self._lock:
            return {
                "narrator_model": self.narrator_model_name,
                "analyzer_model": self.analyzer_model_name,
            }

    async def initialize_model(self) -> bool:
        lg.info("Запрос на инициализацию клиента Deepseek API.")

        if not config.DEEPSEEK_API_KEY or config.DEEPSEEK_API_KEY == "your_api_key_here":
            lg.critical("Ключ DEEPSEEK_API_KEY не найден или не изменен в .env файле.")
            console.print("[bold red]Ошибка: Ключ DEEPSEEK_API_KEY не установлен. Проверьте ваш .env файл.[/bold red]")
            return False

        try:
            async with self._lock:
                if self.client:
                    lg.info("Клиент API уже инициализирован.")
                    return True

                lg.info("Создание клиента Deepseek API...")
                console.print("[bold blue]Инициализация соединения с Deepseek API...[/bold blue]")

                self.client = AsyncOpenAI(
                    api_key=config.DEEPSEEK_API_KEY,
                    base_url=config.DEEPSEEK_API_BASE_URL,
                )

            lg.info("Клиент Deepseek API успешно создан.")
            console.print("[bold green]Соединение с API Deepseek успешно установлено.[/bold green]")
            return True

        except Exception as e:
            lg.critical(f"Не удалось инициализировать клиент Deepseek API: {e}", exc_info=True)
            self.client = None
            return False

    async def stream_narration(self, prompt: str) -> AsyncGenerator[str, None]:
        if not self.is_model_loaded or not self.client:
            lg.error("Попытка генерации, но клиент API не инициализирован.")
            yield "Рассказчик недоступен."
            return

        lg.info(f"Начало генерации ПОВЕСТВОВАНИЯ от модели '{self.narrator_model_name}'.")
        messages: List[ChatCompletionMessageParam] = [{"role": "user", "content": prompt}] # type: ignore

        try:
            stream = await self.client.chat.completions.create(
                model=self.narrator_model_name,
                messages=messages,
                stream=True,
                timeout=120.0,
                **self.narrator_params
            )
            async for chunk in stream:
                if content := chunk.choices[0].delta.content:
                    yield content
                await trio.sleep(0.01)
        except Exception as e:
            lg.error(f"Ошибка во время стриминга повествования: {e}", exc_info=True)
            yield "Рассказчик спотыкается..."
        finally:
            lg.info("Потоковая генерация повествования завершена.")

    async def get_state_changes_from_narration(self, prompt: str) -> Tuple[Optional[Dict[str, Any]], str]:
        if not self.is_model_loaded or not self.client:
            lg.error("Попытка запроса изменений состояния, но клиент API не инициализирован.")
            return None, "Клиент API не инициализирован."

        lg.info(f"Запрос ИЗМЕНЕНИЙ СОСТОЯНИЯ (JSON) от модели '{self.analyzer_model_name}'.")
        messages: List[ChatCompletionMessageParam] = [{"role": "user", "content": prompt}] # type: ignore

        raw_content = ""
        try:
            response = await self.client.chat.completions.create( # type: ignore
                model=self.analyzer_model_name,
                messages=messages,
                timeout=150.0,
                response_format={"type": "json_object"},
                **self.analyzer_params
            )
            if not (response.choices and (raw_content := response.choices[0].message.content)):
                error_text = f"Модель не вернула контент. Полный объект ответа: {response.model_dump_json(indent=2)}"
                lg.warning(error_text)
                return None, error_text

            lg.debug(f"Получен сырой ответ для изменения состояния: {raw_content}")

            json_str = ""
            if match := re.search(r'```json\s*({.*?})\s*```', raw_content, re.DOTALL):
                json_str = match.group(1)
            else:
                json_str = raw_content

            return json.loads(json_str), raw_content

        except json.JSONDecodeError as e:
            error_message = f"Ошибка декодирования JSON ответа модели. Ответ был: \n---\n{raw_content}\n---\nОшибка: {e}"
            lg.error(error_message)
            return None, error_message
        except Exception as e:
            error_message = f"Неизвестная ошибка при запросе изменений состояния: {e}"
            lg.error(error_message, exc_info=True)
            return None, error_message
        finally:
            lg.info(f"Запрос на изменение состояния от '{self.analyzer_model_name}' завершен.")
