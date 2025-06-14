import os
import shutil
import socket

import trio

from config import DEFAULT_HOST, MAX_PORT_ATTEMPTS
from logger import lg

PROMPT_DIR = 'prompts'
RESPONSE_DIR = 'responses'


def initialize_debug_directories():
    """
    Полностью очищает и пересоздает директории для сохранения промптов и ответов.
    """
    try:
        if os.path.exists(PROMPT_DIR):
            shutil.rmtree(PROMPT_DIR)
        if os.path.exists(RESPONSE_DIR):
            shutil.rmtree(RESPONSE_DIR)

        os.makedirs(os.path.join(PROMPT_DIR, 'narration'), exist_ok=True)
        os.makedirs(os.path.join(PROMPT_DIR, 'state'), exist_ok=True)
        os.makedirs(os.path.join(RESPONSE_DIR, 'narration'), exist_ok=True)
        os.makedirs(os.path.join(RESPONSE_DIR, 'state'), exist_ok=True)

        lg.info(f"Директории '{PROMPT_DIR}' и '{RESPONSE_DIR}' успешно очищены и созданы.")
    except Exception as e:
        lg.error(f"Ошибка при очистке/создании директорий для отладки: {e}", exc_info=True)


def get_local_ip() -> str:
    """
    Получает локальный IP-адрес машины, подключаясь к внешнему адресу.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        lg.info(f"Локальный IP-адрес успешно определен: {ip}")
        return ip
    except Exception as e:
        lg.warning(f"Не удалось определить локальный IP, используется 127.0.0.1. Причина: {e}")
        return '127.0.0.1'


async def find_available_port(start_port: int) -> int:
    """
    Находит доступный TCP-порт, начиная с указанного.
    """
    lg.info(f"Поиск доступного порта, начиная с {start_port}.")
    for i in range(MAX_PORT_ATTEMPTS):
        port = start_port + i
        try:
            listeners = await trio.open_tcp_listeners(port=port, host=DEFAULT_HOST)
            for l in listeners:
                await l.aclose()
            lg.info(f"Порт {port} свободен и будет использован.")
            return port
        except OSError as e:
            if e.errno == 98:
                lg.warning(f"Порт {port} уже занят. Пробуем следующий.")
                continue
            else:
                lg.error(f"Непредвиденная ошибка ОС при проверке порта {port}: {e}", exc_info=True)
                raise

    lg.critical(f"Не удалось найти доступный порт в диапазоне {start_port}-{start_port + MAX_PORT_ATTEMPTS - 1}.")
    raise OSError(f"Не удалось найти доступный порт в диапазоне {start_port}-{start_port + MAX_PORT_ATTEMPTS - 1}.")
