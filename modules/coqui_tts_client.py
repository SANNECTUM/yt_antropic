"""
modules/coqui_tts_client.py
Клиент для локального нейросетевого синтеза речи через Coqui XTTS-v2 на RTX 4060 Ti.
Поддерживает:
1. Автодетект локального сервера XTTS (http://127.0.0.1:8020/health).
2. Клонирование голоса по 6-10 секундному аудиосэмплу (Voice Cloning).
3. Пакетную разбивку длинных сценариев на смысловые фразы с объединением в единый MP3/WAV.
4. Прямой fallback на библиотеку TTS в Python, если сервер не запущен.
"""

import os
import re
import json
import base64
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

DEFAULT_XTTS_URL = "http://127.0.0.1:8020"
VOICES_DIR = Path("assets/voices")


class CoquiTTSClient:
    def __init__(self, base_url: str = DEFAULT_XTTS_URL, voices_dir: Optional[Path] = None):
        self.base_url = base_url.rstrip("/")
        self.voices_dir = voices_dir or VOICES_DIR
        self.voices_dir.mkdir(parents=True, exist_ok=True)

    def is_running(self) -> bool:
        """Проверяет, запущен ли локальный сервер Coqui XTTS на порту 8020 и готова ли модель."""
        try:
            req = urllib.request.Request(f"{self.base_url}/health", headers={"User-Agent": "CoquiClient"})
            with urllib.request.urlopen(req, timeout=1.2) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data.get("status") == "ok" and data.get("ready", True)
        except Exception:
            pass
        return False

    def get_server_info(self) -> Dict[str, Any]:
        """Возвращает информацию о видеокарте и модели с локального сервера."""
        try:
            req = urllib.request.Request(f"{self.base_url}/health", headers={"User-Agent": "CoquiClient"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            pass
        return {"status": "offline", "device": "unknown"}

    def list_available_voices(self) -> List[Dict[str, str]]:
        """Возвращает список образцов голосов для клонирования из assets/voices."""
        voices = []
        if self.voices_dir.exists():
            for f in sorted(list(self.voices_dir.glob("*.wav")) + list(self.voices_dir.glob("*.mp3"))):
                name = f.stem.replace("_", " ").title()
                voices.append({
                    "id": f.name,
                    "title": name,
                    "path": str(f.resolve())
                })
        return voices

    def save_voice_sample(self, file_name: str, file_bytes: bytes) -> Path:
        """Сохраняет загруженный пользователем аудиосэмпл для клонирования."""
        clean_name = re.sub(r'[^\w\-_.]', '_', file_name)
        dest = self.voices_dir / clean_name
        dest.write_bytes(file_bytes)
        return dest

    def split_text_for_xtts(self, text: str, max_chars: int = 220) -> List[str]:
        """
        Разбивает длинный сценарий на предложения с пунктуацией.
        XTTS-v2 выдает максимальное кинематографичное качество на фразах до 200-250 символов.
        """
        cleaned = re.sub(r'[\r\n]+', ' ', text).strip()
        # Разбиваем по знакам препинания (. ! ? ... ;)
        raw_sentences = re.split(r'(?<=[.!?…;])\s+', cleaned)
        chunks = []
        current = ""

        for s in raw_sentences:
            s = s.strip()
            if not s:
                continue
            if len(current) + len(s) + 1 <= max_chars:
                current = (current + " " + s).strip()
            else:
                if current:
                    chunks.append(current)
                # Если отдельное предложение длиннее max_chars, делим по запятым
                if len(s) > max_chars:
                    sub_parts = re.split(r'(?<=[,:\—])\s+', s)
                    sub_curr = ""
                    for sp in sub_parts:
                        if len(sub_curr) + len(sp) + 1 <= max_chars:
                            sub_curr = (sub_curr + " " + sp).strip()
                        else:
                            if sub_curr:
                                chunks.append(sub_curr)
                            sub_curr = sp
                    if sub_curr:
                        chunks.append(sub_curr)
                    current = ""
                else:
                    current = s

        if current:
            chunks.append(current)

        return chunks or [cleaned]

    def synthesize_to_file(
        self,
        text: str,
        output_path: Path,
        voice_sample_name: Optional[str] = None,
        language: str = "ru",
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Path:
        """
        Синтезирует речь через локальный сервер XTTS на RTX 4060 Ti.
        Разбивает текст на блоки, отправляет на GPU и объединяет в итоговый аудиофайл.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        chunks = self.split_text_for_xtts(text)
        total_chunks = len(chunks)

        if not chunks:
            raise ValueError("Текст для озвучки пуст.")

        # Определяем путь к сэмплу голоса
        voice_file = None
        if voice_sample_name:
            cand = self.voices_dir / voice_sample_name
            if cand.exists():
                voice_file = cand
        if not voice_file:
            all_v = self.list_available_voices()
            if all_v:
                voice_file = Path(all_v[0]["path"])

        if not self.is_running():
            # Попытка прямого вызова если библиотека TTS доступна локально
            try:
                from TTS.api import TTS
                return self._synthesize_direct_tts(chunks, voice_file, output_path, language, progress_callback)
            except ImportError:
                raise RuntimeError(
                    "Локальный сервер Coqui XTTS не запущен (http://127.0.0.1:8020).\n"
                    "Для запуска на видеокарте RTX 4060 Ti выполните: start_xtts.bat\n"
                    "Или переключитесь на бесплатный '⚡ Microsoft Edge TTS' в настройках."
                )

        temp_dir = output_path.parent / "_temp_xtts"
        temp_dir.mkdir(parents=True, exist_ok=True)
        part_files: List[Path] = []

        try:
            for idx, chunk in enumerate(chunks):
                if progress_callback:
                    progress_callback(idx + 1, total_chunks, f"XTTS (RTX 4060 Ti): фрагмент {idx+1}/{total_chunks}...")

                payload = {
                    "text": chunk,
                    "language": language,
                    "voice": voice_file.name if voice_file else "default",
                }
                data_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"{self.base_url}/synthesize",
                    data=data_bytes,
                    headers={"Content-Type": "application/json", "User-Agent": "CoquiClient"}
                )

                part_file = temp_dir / f"part_{idx:04d}.wav"
                with urllib.request.urlopen(req, timeout=120) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    audio_b64 = resp_data.get("audio_base64", "")
                    if audio_b64:
                        part_file.write_bytes(base64.b64decode(audio_b64))
                        part_files.append(part_file)

            # Склейка через FFmpeg с естественной микропаузой
            self._concat_audio_parts(part_files, output_path)

        finally:
            # Очистка временных частей
            for pf in part_files:
                try:
                    pf.unlink(missing_ok=True)
                except Exception:
                    pass
            try:
                temp_dir.rmdir()
            except Exception:
                pass

        if not output_path.exists() or output_path.stat().st_size < 1000:
            raise RuntimeError("Не удалось собрать итоговый аудиофайл озвучки.")

        return output_path

    def _synthesize_direct_tts(
        self,
        chunks: List[str],
        voice_file: Optional[Path],
        output_path: Path,
        language: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Path:
        """Прямой локальный рендер через библиотеку TTS (если установлена)."""
        import torch
        from TTS.api import TTS

        device = "cuda" if torch.cuda.is_available() else "cpu"
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

        temp_dir = output_path.parent / "_temp_xtts_direct"
        temp_dir.mkdir(parents=True, exist_ok=True)
        part_files = []

        try:
            for idx, chunk in enumerate(chunks):
                if progress_callback:
                    progress_callback(idx + 1, len(chunks), f"XTTS GPU: фрагмент {idx+1}/{len(chunks)}...")
                part_p = temp_dir / f"chunk_{idx:04d}.wav"
                tts.tts_to_file(
                    text=chunk,
                    speaker_wav=str(voice_file) if voice_file else None,
                    language=language,
                    file_path=str(part_p)
                )
                if part_p.exists():
                    part_files.append(part_p)

            self._concat_audio_parts(part_files, output_path)
        finally:
            for pf in part_files:
                try:
                    pf.unlink(missing_ok=True)
                except Exception:
                    pass
            try:
                temp_dir.rmdir()
            except Exception:
                pass

        return output_path

    @staticmethod
    def _concat_audio_parts(parts: List[Path], output_path: Path, studio_mastering: bool = True):
        """Склеивает аудиочасти через FFmpeg и применяет студийный мастеринг дикторского голоса."""
        if not parts:
            return

        import shutil
        import subprocess

        ff = shutil.which("ffmpeg")
        if not ff:
            try:
                import imageio_ffmpeg
                ff = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                ff = "ffmpeg"

        concat_list = output_path.parent / "concat_audio.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for p in parts:
                f.write(f"file '{p.resolve().as_posix()}'\n")

        cmd = [
            ff, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
        ]
        if studio_mastering:
            # Стабильный студийный мастеринг для роликов любой длины (от 15 сек до 2 часов):
            # Без 1-проходного loudnorm (который замыливает звук на длинных 40+ мин дорожках).
            # 1) лёгкий шумодав nr=6 (убирает шипение, сохраняет резкость голоса)
            # 2) highpass=90 + lowpass=11500 — чистый низ и срез ультравысокого песка
            # 3) -2.5 dB @ 300Hz (убирает бубнёж), +1.5 dB @ 2.8kHz (чёткость речи), -2.5 dB @ 6.8kHz (мягкие с/ш)
            # 4) гейт тишины + ровный компрессор + пиковый лимитер (одинаковая чёткость на всей длине видео)
            af_chain = (
                "afftdn=nf=-38:nr=6:nt=w,"
                "highpass=f=90,"
                "lowpass=f=11500,"
                "equalizer=f=300:t=q:w=1.2:g=-2.5,"
                "equalizer=f=2800:t=q:w=1.5:g=1.5,"
                "equalizer=f=6800:t=q:w=1.8:g=-2.5,"
                "agate=threshold=0.010:ratio=2.2:attack=10:release=140,"
                "acompressor=threshold=-18dB:ratio=2.5:attack=12:release=140:makeup=3.0,"
                "alimiter=limit=0.95:attack=5:release=50"
            )
            cmd.extend(["-af", af_chain])

        cmd.extend([
            "-ar", "44100",
            "-c:a", "libmp3lame" if output_path.suffix.lower() == ".mp3" else "pcm_s16le",
            "-b:a", "256k",
            str(output_path)
        ])
        subprocess.run(cmd, capture_output=True, errors="ignore")
        try:
            concat_list.unlink(missing_ok=True)
        except Exception:
            pass
