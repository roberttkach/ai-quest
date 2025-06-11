import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_HOST = '0.0.0.0'
DEFAULT_PORT = 65432
MAX_PORT_ATTEMPTS = 10

LOG_FORMAT = '[%(asctime)s] [%(levelname)s] [%(name)s] [%(funcName)s] %(message)s'
LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'

GAME_MODES = ['приключение', 'выживание']

STORY_INJECTION_TURNS = 5
IMMERSION_TURNS = 2

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL_NAME = "deepseek-reasoner"

DEFAULT_FEAR_WEIGHTS = {
    'primitive': 20,
    'atmospheric': 30,
    'dissonance': 20,
    'uncertainty': 30,
}
