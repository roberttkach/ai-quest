import gc
from typing import AsyncGenerator, Dict, Optional

import trio
from openai import APIStatusError, AsyncOpenAI, OpenAIError
from rich.console import Console

from .. import config
from ..logger import lg

console = Console()


class ModelManager:
    """Управляет жизненным циклом и взаимодействием с Deepseek API."""

    def __init__(self):
        self.client: Optional[AsyncOpenAI] = None
        self.model_params: Dict = {
            "temperature": 0.55,
            "top_p": 0.94,
            "frequency_penalty": 1.2,
        }
        self._lock = trio.Lock()
        lg.info("ModelManager инициализирован для работы с Deepseek API.")

    @property
    def is_model_loaded(self) -> bool:
        """Проверяет, инициализирован ли API клиент."""
        return self.client is not None

    async def initialize_model(self) -> bool:
        """Инициализирует асинхронный клиент для Deepseek API."""
        lg.info("Запрос на инициализацию клиента Deepseek API.")

        if not config.DEEPSEEK_API_KEY:
            lg.critical("Ключ DEEPSEEK_API_KEY не найден в переменных окружения.")
            console.print("[bold red]Ошибка: Ключ DEEPSEEK_API_KEY не установлен.[/bold red]")
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

    async def stream_response(self, prompt: str) -> AsyncGenerator[str, None]:
        """
        Генерирует ответ от Deepseek API, игнорирует "рассуждения" и выдает
        чистый поток фрагментов повествования.
        """
        if not self.is_model_loaded or not self.client:
            lg.error("Попытка генерации, но клиент API не инициализирован.")
            yield "Рассказчик недоступен."
            return

        lg.info("Начало генерации потокового ответа от Deepseek API.")
        messages = [{"role": "user", "content": prompt}]

        try:
            stream = await self.client.chat.completions.create(
                model=config.DEEPSEEK_MODEL_NAME,
                messages=messages,
                stream=True,
                max_tokens=2048,
                temperature=self.model_params["temperature"],
                top_p=self.model_params["top_p"],
                frequency_penalty=self.model_params["frequency_penalty"]
            )

            async for chunk in stream:
                if chunk.choices[0].delta.reasoning_content:
                    continue

                if content := chunk.choices[0].delta.content:
                    yield content

                await trio.sleep(0.01)

        except APIStatusError as e:
            error_message = e.message or "Нет дополнительной информации"
            lg.error(f"Ошибка API (статус {e.status_code}) во время потоковой генерации: {error_message}",
                     exc_info=True)
            yield f"Рассказчик спотыкается... (Ошибка API: {e.status_code})"
        except OpenAIError as e:
            lg.error(f"Общая ошибка API во время потоковой генерации: {e}", exc_info=True)
            yield "Рассказчик спотыкается... (Ошибка API)"
        except Exception as e:
            lg.error(f"Неизвестная ошибка во время потоковой генерации: {e}", exc_info=True)
            yield "Рассказчик спотыкается..."
        finally:
            gc.collect()
            lg.info("Потоковая генерация ответа завершена.")
