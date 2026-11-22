import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
load_dotenv()

def get_secret(key: str, default: str = "") -> str:
    """Получение настройки из .env, st.session_state или st.secrets (для деплоя в Streamlit Cloud)."""
    val = os.getenv(key)
    if val:
        return str(val).strip("'\" ")
    try:
        import streamlit as st
        # 1. Проверяем st.session_state
        if key in st.session_state and st.session_state[key]:
            return str(st.session_state[key]).strip("'\" ")
        if f"user_{key.lower()}" in st.session_state and st.session_state[f"user_{key.lower()}"]:
            return str(st.session_state[f"user_{key.lower()}"]).strip("'\" ")

        # 2. Проверяем st.secrets (все возможные варианты регистра)
        if hasattr(st, "secrets"):
            candidates = [key, key.lower(), key.upper()]
            for c in candidates:
                try:
                    if c in st.secrets:
                        s_val = st.secrets[c]
                        if s_val:
                            return str(s_val).strip("'\" ")
                except Exception:
                    pass
    except Exception:
        pass
    return default

def get_gemini_api_key() -> str:
    """Динамическое получение актуального ключа Gemini."""
    return get_secret("GEMINI_API_KEY", "")

BASE_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = BASE_DIR / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)

# API Ключ Gemini (Google AI Studio)
GEMINI_API_KEY = get_gemini_api_key()
if GEMINI_API_KEY:
    os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

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
