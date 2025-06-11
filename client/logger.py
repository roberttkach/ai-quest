import logging

LOG_FORMAT = '[%(asctime)s] [%(levelname)s] [%(name)s] [%(funcName)s] %(message)s'
LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'

lg = logging.getLogger('ai_quest_client')
lg.setLevel(logging.DEBUG)
lg.propagate = False

if lg.hasHandlers():
    lg.handlers.clear()

file_handler = logging.FileHandler('client.log', mode='w', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter(LOG_FORMAT, LOG_DATEFMT)
file_handler.setFormatter(formatter)

lg.addHandler(file_handler)

lg.info("Логгер клиента успешно инициализирован (лог-файл очищен).")
