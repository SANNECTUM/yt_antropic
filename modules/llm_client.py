import socket
from typing import Optional, List
import httpx
from google import genai
from google.genai import types as genai_types
import config


def _make_http_client() -> httpx.Client:
    """Создаёт httpx.Client с SOCKS5 прокси (xray :10808) если доступен,
    иначе без системного прокси (trust_env=False), чтобы избежать зависания
    на HTTP-прокси :10809, который не работает с Gemini API.
    Таймаут увеличен до 90 сек для генерации длинных сценариев и списков."""
    try:
        s = socket.socket()
        s.settimeout(0.3)
        reachable = s.connect_ex(("127.0.0.1", 10808)) == 0
        s.close()
    except Exception:
        reachable = False

    timeout_config = httpx.Timeout(90.0, connect=15.0)
    if reachable:
        return httpx.Client(proxy="socks5://127.0.0.1:10808", timeout=timeout_config)
    else:
        return httpx.Client(trust_env=False, timeout=timeout_config)


class GeminiClient:
    def __init__(self, model_name: Optional[str] = None):
        api_key = config.GEMINI_API_KEY
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY не найден! Укажите его в файле .env (получите бесплатно: https://aistudio.google.com/)"
            )
        self.primary_model = model_name or config.DEFAULT_GEMINI_MODEL

        # Используем кастомный httpx.Client: SOCKS5 если xray запущен, иначе без системного прокси
        http_client = _make_http_client()
        self.client = genai.Client(
            api_key=api_key,
            http_options={"httpx_client": http_client}
        )

        # Скоростной стек моделей (сначала ультра-быстрые и не исчерпавшие дневной лимит Free Tier)
        self.fallback_models = [
            self.primary_model,
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3.8-flash"
        ]
        # Убираем дубликаты
        seen = set()
        self.ordered_models = []
        for m in self.fallback_models:
            if m and m not in seen:
                seen.add(m)
                self.ordered_models.append(m)

    def generate(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7) -> str:
        config_params = {}
        if system_prompt:
            config_params["system_instruction"] = system_prompt
        if temperature is not None:
            config_params["temperature"] = temperature

        gen_config = genai_types.GenerateContentConfig(**config_params) if config_params else None

        last_error = None
        for model in self.ordered_models:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=gen_config
                )
                if response:
                    if response.text:
                        return response.text
                    # Проверяем, не заблокирован ли контент фильтрами безопасности Google
                    block_reason = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
                    if block_reason:
                        raise ValueError(
                            f"Контент заблокирован фильтрами безопасности Google Gemini ({block_reason}). "
                            f"Смягчите формулировки в исходных материалах."
                        )
            except Exception as e:
                last_error = e
                err_msg = str(e)
                # Если 404, 503, 429 или таймаут — моментально пробуем следующую модель
                if any(code in err_msg for code in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "demand", "404", "NOT_FOUND", "timed out", "Timeout"]):
                    continue
                elif "location is not supported" in err_msg.lower() or "failed_precondition" in err_msg.lower():
                    raise RuntimeError(
                        "❌ Ошибка региона Google AI Studio: 'User location is not supported'.\n"
                        "Для доступа к Gemini API из вашего региона включите системный VPN или добавьте HTTPS_PROXY в файл .env."
                    )
                else:
                    raise e

        if last_error:
            raise last_error
        return ""
