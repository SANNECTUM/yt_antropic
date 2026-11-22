import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
load_dotenv()

def get_secret(key: str, default: str = "") -> str:
    """Получение настройки из .env или st.secrets (для деплоя в Streamlit Cloud)."""
    val = os.getenv(key)
    if val:
        return val
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return default

BASE_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = BASE_DIR / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)

# API Ключ Gemini (Google AI Studio)
GEMINI_API_KEY = get_secret("GEMINI_API_KEY", "")

# Модели Gemini
DEFAULT_GEMINI_MODEL = get_secret("DEFAULT_GEMINI_MODEL", "gemini-2.5-flash")

# Настройки озвучки (Edge-TTS)
DEFAULT_TTS_VOICE = get_secret("DEFAULT_TTS_VOICE", "ru-RU-DmitryNeural")
DEFAULT_TTS_RATE = get_secret("DEFAULT_TTS_RATE", "+0%")
DEFAULT_TTS_CONCURRENCY = int(get_secret("DEFAULT_TTS_CONCURRENCY", "4"))
DEFAULT_TTS_CHUNK_SIZE = int(get_secret("DEFAULT_TTS_CHUNK_SIZE", "2000"))

# Настройки поиска изображений
GOOGLE_SEARCH_API_KEY = get_secret("GOOGLE_SEARCH_API_KEY", "")
GOOGLE_SEARCH_CX = get_secret("GOOGLE_SEARCH_CX", "")
PEXELS_API_KEY = get_secret("PEXELS_API_KEY", "")
