import os
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
import config

try:
    from gemini_webapi import GeminiClient
except ImportError:
    GeminiClient = None

class GeminiWebGenerator:
    """
    Утилита для работы с веб-версией Gemini (прямое подключение).
    """
    def __init__(self, secure_1psid: str = "", secure_1psidts: str = ""):
        self.secure_1psid = secure_1psid
        self.secure_1psidts = secure_1psidts
