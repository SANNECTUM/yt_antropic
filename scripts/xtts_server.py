"""
scripts/xtts_server.py
Высокопроизводительный локальный микросервер Coqui XTTS-v2 для Windows.
Работает на видеокарте NVIDIA (RTX 4060 Ti) через PyTorch + CUDA.

Запуск:
    python scripts/xtts_server.py --port 8020
"""

import os
import sys
import json
import base64
import argparse
import tempfile
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# Добавляем корневую директорию проекта в sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

VOICES_DIR = ROOT_DIR / "assets" / "voices"
VOICES_DIR.mkdir(parents=True, exist_ok=True)

# Глобальный инстанс модели XTTS
_XTTS_MODEL = None
_DEVICE = "cpu"


def get_xtts_model():
    """Ленивая загрузка модели XTTS-v2 в видеопамять (CUDA)."""
    global _XTTS_MODEL, _DEVICE
    if _XTTS_MODEL is not None:
        return _XTTS_MODEL

    try:
        import torch
        from TTS.api import TTS

        _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[*] Инициализация Coqui XTTS-v2 на устройстве: {_DEVICE.upper()}...")
        if _DEVICE == "cuda":
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"[*] Видеокарта: {gpu_name} ({vram_gb:.1f} GB VRAM)")

        _XTTS_MODEL = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(_DEVICE)
        print("[+] Модель Coqui XTTS-v2 успешно загружена в память и готова к синтезу!")
        return _XTTS_MODEL
    except Exception as e:
        print(f"[-] Ошибка загрузки модели XTTS: {e}")
        raise


class XTTSRequestHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            gpu_info = "CPU"
            try:
                import torch
                if torch.cuda.is_available():
                    gpu_info = torch.cuda.get_device_name(0)
            except Exception:
                pass

            resp = {
                "status": "ok",
                "device": _DEVICE,
                "gpu": gpu_info,
                "model": "xtts_v2",
                "voices": [f.name for f in sorted(list(VOICES_DIR.glob("*.wav")) + list(VOICES_DIR.glob("*.mp3")))]
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        elif self.path == "/voices":
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            voices = [{"id": f.name, "title": f.stem.replace("_", " ").title()}
                      for f in sorted(list(VOICES_DIR.glob("*.wav")) + list(VOICES_DIR.glob("*.mp3")))]
            self.wfile.write(json.dumps({"voices": voices}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/synthesize":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")

            try:
                data = json.loads(body)
                text = data.get("text", "").strip()
                language = data.get("language", "ru")
                voice_name = data.get("voice", "")

                if not text:
                    self.send_response(400)
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(b'{"error": "Text is empty"}')
                    return

                # Ищем аудиосэмпл голоса
                speaker_wav = None
                if voice_name:
                    cand = VOICES_DIR / voice_name
                    if cand.exists():
                        speaker_wav = str(cand)

                if not speaker_wav:
                    all_v = sorted(list(VOICES_DIR.glob("*.wav")) + list(VOICES_DIR.glob("*.mp3")))
                    if all_v:
                        speaker_wav = str(all_v[0])

                tts = get_xtts_model()

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                    tmp_out = tf.name

                try:
                    tts.tts_to_file(
                        text=text,
                        speaker_wav=speaker_wav,
                        language=language,
                        file_path=tmp_out
                    )

                    audio_bytes = Path(tmp_out).read_bytes()
                    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

                    self.send_response(200)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "success",
                        "audio_base64": audio_b64,
                        "bytes_count": len(audio_bytes)
                    }).encode("utf-8"))

                finally:
                    if os.path.exists(tmp_out):
                        try:
                            os.remove(tmp_out)
                        except Exception:
                            pass

            except Exception as e:
                self.send_response(500)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


def run_server(port: int = 8020):
    print("=" * 60)
    print("  🚀 ЛОКАЛЬНЫЙ СЕРВЕР СИНТЕЗА РЕЧИ COQUI XTTS-v2")
    print("  📍 Порт: http://127.0.0.1:8020")
    print("  📁 Директория голосов:", VOICES_DIR)
    print("=" * 60)

    # Прогрев модели при старте
    try:
        get_xtts_model()
    except Exception as e:
        print(f"[!] Внимание: Модель загрузится при первом запросе ({e})")

    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, XTTSRequestHandler)
    print(f"[+] Сервер слушает запросы на http://127.0.0.1:{port}/")
    print("[*] Нажмите Ctrl+C для остановки сервера.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Сервер остановлен.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coqui XTTS-v2 Local Server")
    parser.add_argument("--port", type=int, default=8020, help="Порт сервера (по умолчанию 8020)")
    args = parser.parse_args()
    run_server(args.port)
