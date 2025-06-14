import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_HOST = '0.0.0.0'
DEFAULT_PORT = 65432
MAX_PLAYERS = 4
MAX_PORT_ATTEMPTS = 10

LOG_FORMAT = '[%(asctime)s] [%(levelname)s] [%(name)s] [%(funcName)s] %(message)s'
LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'

STORY_INJECTION_TURNS = 4
IMMERSION_TURNS = 2
MAX_HISTORY_CHAR_LENGTH = 8192

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_BASE_URL = "https://api.deepseek.com/v1"

NARRATOR_MODEL_NAME = "deepseek-reasoner"
ANALYZER_MODEL_NAME = "deepseek-chat"

DEFAULT_FEAR_WEIGHTS = {
    'primitive': 20,
    'atmospheric': 30,
    'dissonance': 20,
    'uncertainty': 30,
}
