import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = BASE_DIR / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)

# API Ключ Gemini (Google AI Studio)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Модели Gemini
DEFAULT_GEMINI_MODEL = os.getenv("DEFAULT_GEMINI_MODEL", "gemini-3.8-flash")

# Настройки озвучки (Edge-TTS)
DEFAULT_TTS_VOICE = os.getenv("DEFAULT_TTS_VOICE", "ru-RU-DmitryNeural")
DEFAULT_TTS_RATE = os.getenv("DEFAULT_TTS_RATE", "+0%")
DEFAULT_TTS_CONCURRENCY = int(os.getenv("DEFAULT_TTS_CONCURRENCY", "4"))
DEFAULT_TTS_CHUNK_SIZE = int(os.getenv("DEFAULT_TTS_CHUNK_SIZE", "2000"))

# Настройки поиска изображений
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY", "")
GOOGLE_SEARCH_CX = os.getenv("GOOGLE_SEARCH_CX", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
