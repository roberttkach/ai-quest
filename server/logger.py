import logging
import sys

LOG_FORMAT = '[%(asctime)s] [%(levelname)s] [%(name)s] [%(funcName)s] %(message)s'
LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'

lg = logging.getLogger('ai_quest_server')
lg.setLevel(logging.DEBUG)
lg.propagate = False

if lg.hasHandlers():
    lg.handlers.clear()

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)

file_handler = logging.FileHandler('server.log', mode='w', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter(LOG_FORMAT, LOG_DATEFMT)
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

lg.addHandler(console_handler)
lg.addHandler(file_handler)

lg.info("Логгер сервера успешно инициализирован (лог-файл очищен).")
