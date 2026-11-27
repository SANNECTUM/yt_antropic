"""
scripts/xtts_server.py
Высокопроизводительный локальный микросервер озвучки на видеокарте NVIDIA (RTX 4060 Ti).
Основной движок: F5-TTS Russian v4 (Misha24-10/F5-TTS_RUSSIAN) — чистое студийное клонирование голоса на русском языке.
Резервный движок: Coqui XTTS-v2.

Запуск:
    .venv_xtts\Scripts\python.exe scripts/xtts_server.py --port 8020
"""

import os
import sys

# Отключаем нестабильный протокол hf_xet (часто зависает на Windows) и лишние предупреждения
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("COQUI_TOS_AGREED", "1")

# Добавляем папку Scripts (где лежит ffmpeg.exe) и папку imageio_ffmpeg в PATH для pydub / whisper / f5-tts
_scripts_dir = str(os.path.dirname(sys.executable))
if _scripts_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _scripts_dir + os.pathsep + os.environ.get("PATH", "")
try:
    import shutil, imageio_ffmpeg
    from pathlib import Path as _Path
    _ff_target = _Path(_scripts_dir) / "ffmpeg.exe"
    if not _ff_target.exists():
        shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), _ff_target)
except Exception:
    pass

import json
import base64
import argparse
import tempfile
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

VOICES_DIR = ROOT_DIR / "assets" / "voices"
VOICES_DIR.mkdir(parents=True, exist_ok=True)

_TTS_MODEL = None
_ENGINE_NAME = "f5_tts_russian_v4"
_DEVICE = "cpu"
_LOAD_ERROR = None
_REF_TEXT_CACHE = {}
_ACCENTIZER = None


def get_accentizer():
    """Ленивая загрузка нейросетевого расстановщика русских ударений (RUAccent)."""
    global _ACCENTIZER
    if _ACCENTIZER is not None:
        return _ACCENTIZER
    try:
        from ruaccent import RUAccent
        acc = RUAccent()
        acc.load(omograph_model_size="turbo3.1", use_dictionary=True, tiny_mode=False)
        _ACCENTIZER = acc
        print("[+] Модуль русских ударений RUAccent (turbo3.1) успешно загружен!")
        return _ACCENTIZER
    except Exception as e:
        print(f"[!] RUAccent недоступен ({e}), синтез пойдет без авто-ударений.")
        return None


def accentize_russian(text: str) -> str:
    """Расставляет точные знаки ударений '+' и букву 'ё' для F5-TTS Russian."""
    if not text or "+" in text:
        return text
    acc = get_accentizer()
    if acc is None:
        return text
    try:
        return acc.process_all(text)
    except Exception:
        return text


def get_tts_model():
    """Загружает F5-TTS Russian v4 (или резервный XTTS-v2) в видеопамять CUDA."""
    global _TTS_MODEL, _ENGINE_NAME, _DEVICE, _LOAD_ERROR
    if _TTS_MODEL is not None:
        return _TTS_MODEL

    try:
        import torch
        _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[*] Инициализация локального TTS на устройстве: {_DEVICE.upper()}...")
        if _DEVICE == "cuda":
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"[*] Видеокарта: {gpu_name} ({vram_gb:.1f} GB VRAM)")

        # Пробуем основной движок нового поколения: F5-TTS Russian v4
        try:
            from huggingface_hub import hf_hub_download
            from f5_tts.api import F5TTS

            print("[*] Загрузка чекпоинта Misha24-10/F5-TTS_RUSSIAN (v4)...")
            ckpt_file = hf_hub_download(
                repo_id="Misha24-10/F5-TTS_RUSSIAN",
                filename="F5TTS_v1_Base_v4_winter/model_212000.safetensors",
            )
            vocab_file = hf_hub_download(
                repo_id="Misha24-10/F5-TTS_RUSSIAN",
                filename="F5TTS_v1_Base/vocab.txt",
            )
            _TTS_MODEL = F5TTS(
                model="F5TTS_v1_Base",
                ckpt_file=ckpt_file,
                vocab_file=vocab_file,
                device=_DEVICE,
            )
            _ENGINE_NAME = "f5_tts_russian_v4"
            _LOAD_ERROR = None
            print("[+] Модель F5-TTS Russian v4 успешно загружена в CUDA и готова к синтезу!")
            return _TTS_MODEL
        except Exception as f5_err:
            print(f"[!] F5-TTS недоступен ({f5_err}), переключение на резервный Coqui XTTS-v2...")
            from TTS.api import TTS
            _TTS_MODEL = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(_DEVICE)
            _ENGINE_NAME = "xtts_v2"
            _LOAD_ERROR = None
            print("[+] Резервная модель Coqui XTTS-v2 успешно загружена!")
            return _TTS_MODEL

    except Exception as e:
        _LOAD_ERROR = str(e)
        print(f"[-] Ошибка загрузки TTS модели: {e}")
        raise


def get_ref_text(speaker_wav: str) -> str:
    """Читает транскрипт референса из .txt файла рядом с .wav (если есть) или кеша."""
    if not speaker_wav:
        return ""
    if speaker_wav in _REF_TEXT_CACHE:
        return _REF_TEXT_CACHE[speaker_wav]
    txt_path = Path(speaker_wav).with_suffix(".txt")
    if txt_path.exists():
        txt = txt_path.read_text(encoding="utf-8").strip()
        _REF_TEXT_CACHE[speaker_wav] = txt
        return txt
    return ""


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
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            ready_str = f"✅ ГОТОВА К СИНТЕЗУ ({_ENGINE_NAME})" if _TTS_MODEL is not None else f"❌ ОШИБКА ЗАГРУЗКИ ({_LOAD_ERROR})"
            html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>Local Neural TTS Server</title>
            <style>body{{background:#12121a;color:#eee;font-family:sans-serif;padding:40px;max-width:700px;margin:auto;}}
            .card{{background:#1d1d2b;padding:24px;border-radius:12px;border:1px solid #333;}}</style></head>
            <body><div class='card'><h2>🎙️ Локальный сервер нейроозвучки (F5-TTS Russian v4)</h2>
            <p><b>Статус модели:</b> {ready_str}</p>
            <p><b>Устройство:</b> {_DEVICE.upper()}</p>
            <p><b>API Эндпоинты:</b> <code>GET /health</code>, <code>GET /voices</code>, <code>POST /synthesize</code></p>
            </div></body></html>"""
            self.wfile.write(html.encode("utf-8"))
            return

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
            except Exception as err:
                gpu_info = f"No torch ({err})"

            is_ready = (_TTS_MODEL is not None)
            resp = {
                "status": "ok" if is_ready else "error",
                "ready": is_ready,
                "error": _LOAD_ERROR,
                "device": _DEVICE,
                "gpu": gpu_info,
                "model": _ENGINE_NAME,
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

                speaker_wav = None
                if voice_name:
                    cand = VOICES_DIR / voice_name
                    if cand.exists():
                        speaker_wav = str(cand)

                if not speaker_wav:
                    all_v = sorted(list(VOICES_DIR.glob("*.wav")) + list(VOICES_DIR.glob("*.mp3")))
                    if all_v:
                        speaker_wav = str(all_v[0])

                model = get_tts_model()

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                    tmp_out = tf.name

                try:
                    speed = float(data.get("speed", 1.0))

                    if _ENGINE_NAME == "f5_tts_russian_v4":
                        ref_text = data.get("ref_text") or get_ref_text(speaker_wav)
                        gen_text_ready = accentize_russian(text) if language == "ru" else text
                        model.infer(
                            ref_file=speaker_wav,
                            ref_text=ref_text,
                            gen_text=gen_text_ready,
                            nfe_step=int(data.get("nfe_step", 32)),
                            cfg_strength=float(data.get("cfg_strength", 2.0)),
                            speed=speed,
                            remove_silence=False,
                            file_wave=tmp_out,
                        )
                    else:
                        model.tts_to_file(
                            text=text,
                            speaker_wav=speaker_wav,
                            language=language,
                            file_path=tmp_out,
                            split_sentences=True,
                            temperature=float(data.get("temperature", 0.55)),
                            speed=float(data.get("speed", 1.06)),
                            repetition_penalty=float(data.get("repetition_penalty", 5.0)),
                            top_p=float(data.get("top_p", 0.80)),
                            top_k=int(data.get("top_k", 40)),
                        )

                    audio_bytes = Path(tmp_out).read_bytes()
                    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

                    self.send_response(200)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "success",
                        "engine": _ENGINE_NAME,
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
                import traceback
                traceback.print_exc()
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
    print("  🚀 ЛОКАЛЬНЫЙ СЕРВЕР НЕЙРООЗВУЧКИ F5-TTS RUSSIAN v4")
    print("  📍 Порт: http://127.0.0.1:8020")
    print("  📁 Директория голосов:", VOICES_DIR)
    print("=" * 60)

    try:
        get_tts_model()
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
    parser = argparse.ArgumentParser(description="Local Neural TTS Server (F5-TTS Russian v4)")
    parser.add_argument("--port", type=int, default=8020, help="Порт сервера (по умолчанию 8020)")
    args = parser.parse_args()
    run_server(args.port)
