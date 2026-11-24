import os
import re
import asyncio
import time
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Callable, Any
import edge_tts
import config

class TTSSynthesizer:
    def __init__(
        self, 
        voice: Optional[str] = None, 
        rate: Optional[str] = None,
        concurrency: Optional[int] = None,
        chunk_size: Optional[int] = None,
        engine: Optional[str] = None,
        *args,
        **kwargs
    ):
        """
        voice: голос TTS.
               Для Google AI Studio: 'Charon', 'Fenrir', 'Puck', 'Aoede', 'Kore'
               Для Edge TTS: 'ru-RU-DmitryNeural', 'ru-RU-SvetlanaNeural'
        engine: 'gemini' (Google AI Studio) или 'edge' (Microsoft Edge TTS)
        rate: скорость речи (для Edge TTS)
        concurrency: число параллельных потоков запросов
        chunk_size: максимальный размер блока текста в символах
        """
        gemini_voice_ids = ["Milo", "Nika", "Charon", "Fenrir", "Puck", "Aoede", "Kore"]
        self.engine = engine or kwargs.get("engine")
        if not self.engine:
            if voice in gemini_voice_ids:
                self.engine = "gemini"
            elif voice and (voice.endswith(".wav") or voice.endswith(".mp3")):
                self.engine = "coqui"
            else:
                self.engine = getattr(config, "DEFAULT_TTS_ENGINE", "gemini")

        if self.engine == "gemini":
            self.voice = voice or "Milo"
            self.style = kwargs.get("style") or ("podcast" if self.voice in ["Milo", "Nika"] else "documentary")
            self.concurrency = concurrency if concurrency is not None else kwargs.get("concurrency", 2)
            self.chunk_size = chunk_size if chunk_size is not None else kwargs.get("chunk_size", 2500)
        elif self.engine == "coqui":
            self.voice = voice or "dmitry_narrator.wav"
            self.style = "documentary"
            self.concurrency = 1
            self.chunk_size = chunk_size or 220
        else:
            self.voice = voice or getattr(config, "DEFAULT_TTS_VOICE", "ru-RU-DmitryNeural")
            self.style = "documentary"
            self.concurrency = concurrency if concurrency is not None else kwargs.get("concurrency", getattr(config, "DEFAULT_TTS_CONCURRENCY", 4))
            self.chunk_size = chunk_size if chunk_size is not None else kwargs.get("chunk_size", getattr(config, "DEFAULT_TTS_CHUNK_SIZE", 2000))

        self.rate = rate or getattr(config, "DEFAULT_TTS_RATE", "+0%")
        self.cache_dir = getattr(config, "BASE_DIR", Path(".")) / ".cache" / "tts"
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    @staticmethod
    def clean_voiceover_text(raw_text: str) -> str:
        """
        Полностью очищает сценарий от любых режиссерских пометок, таблиц,
        таймкодов, SFX, звездочек, кавычек и спецсимволов, оставляя ИСКЛЮЧИТЕЛЬНО
        чистую человеческую речь диктора, готовую для безупречной озвучки ИИ-голосом
        без прочтения лишних символов и знаков пунктуации.
        """
        text = raw_text

        # 1. Если есть специальные блоки дикторского текста, извлекаем ТОЛЬКО их
        pattern = r'(?:\[Дикторский текст\]|\*\*Текст диктора:\*\*|### ЧИСТЫЙ ТЕКСТ ДЛЯ ОЗВУЧКИ:)(.*?)(?=\n\[\d|\n\[Видеоряд|\n\[Аудиоряд|\n###|\Z)'
        blocks = re.findall(pattern, text, flags=re.DOTALL | re.IGNORECASE)
        if blocks:
            text = '\n\n'.join(b.strip() for b in blocks if b.strip())
        else:
            # Иначе отсекаем блоки видеоряда, аудиоряда и таймингов
            text = re.sub(r'\[Видеоряд[^\]]*\]:[^\n]*(\n(?!\n?\[)[^\n]*)*', '', text, flags=re.IGNORECASE)
            text = re.sub(r'\[Аудиоряд[^\]]*\]:[^\n]*(\n(?!\n?\[)[^\n]*)*', '', text, flags=re.IGNORECASE)
            text = re.sub(r'\[\d{2}:\d{2}[^\]]*\][^\n]*', '', text)

        # 2. Удаляем блоки кода markdown (```yaml, ``` и т.д.)
        text = re.sub(r'```[a-zA-Z]*', '', text)
        text = text.replace('```', '')

        # 3. Удаляем HTML теги (<br>, <p> и т.д.)
        text = re.sub(r'<[^>]+>', ' ', text)

        # 4. Преобразуем паузы вида `[Пауза — 1.5 сек]` в мягкие паузы (запятая или многоточие)
        text = re.sub(r'(`?\[Пауза[^\]]*\]`?)', '... ', text, flags=re.IGNORECASE)

        # 5. Удаляем любые другие квадратные скобки со всем содержимым:
        # [SFX:...], [Звук:...], [Видео:...], [Тайминг:...]
        text = re.sub(r'\[[^\]]*\]', '', text)

        # 6. Удаляем любые пометки в круглых скобках (эмоции, ремарки, шепот):
        # например: (Медленно, интригующе...), (с иронией), (темп 130 слов)
        text = re.sub(r'\([^\)]*(?:интонаци|темп|голос|шепот|пауз|сдержанно|тревожно|ирони|драматич)[^\)]*\)', '', text, flags=re.IGNORECASE)
        # Также общие ремарки в скобках короче 60 символов
        text = re.sub(r'\([^\)]{1,60}\)', '', text)

        # 7. Заменяем спецсимволы, которые ломают XML парсер Edge-TTS
        text = text.replace('&', ' и ')
        text = text.replace('<', ' ').replace('>', ' ')

        # 8. Удаляем все спецсимволы markdown и разметки (звездочки, решетки, бэктики, тильды, прямые черты)
        text = re.sub(r'[\*\#\`\_\~\|]', '', text)

        # 9. Удаляем дефисы, маркеры списков и двоеточия в начале строк
        text = re.sub(r'^\s*[:\-—•]\s*', '', text, flags=re.MULTILINE)

        # 10. Удаляем служебные заголовки в начале строк
        text = re.sub(r'^(Диктор|Кадр|Сцена|Тайминг|Видеоряд|Акт|SFX|Звук)[^\n:]*:', '', text, flags=re.MULTILINE | re.IGNORECASE)

        # 11. Удаляем все виды кавычек (робот не должен читать «кавычки открываются/закрываются»)
        for q in ['"', "'", '«', '»', '“', '”', '„', '`']:
            text = text.replace(q, '')

        # 12. Длинные тире между словами делаем запятой, чтобы робот делал естественную речевую паузу
        text = re.sub(r'\s+[-—]\s+', ', ', text)

        # 13. Удаляем изолированные двоеточия и знаки препинания в начале абзацев
        text = re.sub(r'^\s*[:,\.\-—]+\s*', '', text, flags=re.MULTILINE)

        # 14. Нормализуем многоточия, пробелы и переносы строк
        text = re.sub(r'\.{4,}', '...', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n\s*\n+', '\n\n', text)

        return text.strip()

    @staticmethod
    def split_into_chunks(text: str, max_chars: int = 2500) -> List[str]:
        """
        Разбивает текст на компактные логические фрагменты (абзацы / предложения),
        чтобы Microsoft Edge-TTS не обрывал websocket-соединение при озвучке длинных сценариев.
        """
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_len = 0

        for p in paragraphs:
            if current_len + len(p) + 1 <= max_chars:
                current_chunk.append(p)
                current_len += len(p) + 1
            else:
                if current_chunk:
                    chunks.append('\n'.join(current_chunk))
                    current_chunk = []
                    current_len = 0

                # Если сам абзац длиннее max_chars, аккуратно бьем его по предложениям
                if len(p) > max_chars:
                    sentences = re.split(r'(?<=[.!?…])\s+', p)
                    sub_chunk: List[str] = []
                    sub_len = 0
                    for s in sentences:
                        if sub_len + len(s) + 1 <= max_chars:
                            sub_chunk.append(s)
                            sub_len += len(s) + 1
                        else:
                            if sub_chunk:
                                chunks.append(' '.join(sub_chunk))
                            sub_chunk = [s]
                            sub_len = len(s)
                    if sub_chunk:
                        chunks.append(' '.join(sub_chunk))
                else:
                    current_chunk.append(p)
                    current_len = len(p)

        if current_chunk:
            chunks.append('\n'.join(current_chunk))

        return [c.strip() for c in chunks if c.strip()]

    async def _synthesize_chunk_with_retry(
        self, 
        chunk_text: str, 
        max_retries: int = 4
    ) -> bytes:
        """
        Озвучивает один фрагмент с автоматическим повтором при сбоях сети.
        Использует boundary='WordBoundary' для предотвращения сбоя 'No audio was received'
        на серверах Azure/Edge TTS для русского голоса DmitryNeural.
        """
        clean_text = chunk_text.strip()
        if not clean_text or not re.search(r'[a-zA-Zа-яА-Я0-9]', clean_text):
            return b""

        # Гарантируем закрывающий знак препинания для корректной интонации нейросети
        if clean_text[-1] not in '.!?…:':
            clean_text += '.'

        last_error = None

        for attempt in range(max_retries):
            # На последней попытке, если Дмитрий завис на Bing, пробуем Светлану как безотказный резерв
            current_voice = self.voice
            if attempt == (max_retries - 1) and self.voice == "ru-RU-DmitryNeural":
                current_voice = "ru-RU-SvetlanaNeural"

            try:
                communicate = edge_tts.Communicate(
                    text=clean_text,
                    voice=current_voice,
                    rate=self.rate,
                    boundary="WordBoundary",
                    connect_timeout=15,
                    receive_timeout=45
                )
                audio_bytes = bytearray()
                async for message in communicate.stream():
                    if message["type"] == "audio":
                        audio_bytes.extend(message["data"])

                if len(audio_bytes) > 0:
                    return bytes(audio_bytes)
                else:
                    raise RuntimeError("Сервер не вернул аудиоданные (0 байт).")
            except Exception as e:
                last_error = e
                backoff = 2.0 * (attempt + 1)
                await asyncio.sleep(backoff)

        raise RuntimeError(f"Не удалось озвучить фрагмент после {max_retries} попыток: {last_error}")

    def _synthesize_gemini_chunk_with_retry(
        self, 
        chunk_text: str, 
        max_retries: int = 4
    ) -> bytes:
        """
        Синтезирует речь через официальный Google AI Studio (Gemini Flash TTS).
        Использует естественные эмоциональные нейро-голоса Gemini (Charon, Fenrir, Puck и др.)
        и сохраняет в чистом MP3 формате через FFmpeg.
        """
        from google.genai import types
        from modules.llm_client import GeminiClient
        import subprocess
        import imageio_ffmpeg
        import tempfile

        clean_text = chunk_text.strip()
        if not clean_text or not re.search(r'[a-zA-Zа-яА-Я0-9]', clean_text):
            return b""

        gc = GeminiClient()
        client = gc.client

        if getattr(self, "style", "") == "podcast" or self.voice in ["Milo", "Nika"]:
            style_prompt = (
                "Ты — ведущий популярного подкаста. "
                "Прочитай вслух строго следующий текст на русском языке в стиле живого разговорного подкаста (Podcast style): "
                "непринужденно, живо, тепло, с естественной разговорной подачей и паузами, "
                "как будто общаешься со слушателями у микрофона в уютной студии. "
            )
        else:
            style_prompt = (
                "Ты — профессиональный диктор документальных фильмов, аудиокниг и захватывающих историй. "
                "Прочитай вслух строго следующий текст на русском языке, максимально выразительно, "
                "с естественными речевыми паузами, правильными смысловыми акцентами и кинематографичными интонациями. "
            )

        prompt = (
            f"{style_prompt}"
            "СТРОГО ЗАПРЕЩЕНО добавлять любые приветствия, пояснения, комментарии или фразы от себя. "
            f"Читай ИСКЛЮЧИТЕЛЬНО сам текст:\n\n{clean_text}"
        )

        cfg = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice)
                )
            )
        )

        models_to_try = [
            "gemini-3.8-flash-lite-tts",
            "gemini-3.8-flash-tts", 
            "gemini-2.5-flash-preview-tts"
        ]

        last_error = None
        for attempt in range(max_retries):
            for model_id in models_to_try:
                try:
                    resp = client.models.generate_content(
                        model=model_id,
                        contents=prompt,
                        config=cfg
                    )
                    wav_data = None
                    if resp and resp.candidates and resp.candidates[0].content:
                        for part in resp.candidates[0].content.parts:
                            if part.inline_data and part.inline_data.data:
                                wav_data = part.inline_data.data
                                break

                    if wav_data and len(wav_data) > 1000:
                        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf_wav:
                            tf_wav.write(wav_data)
                            wav_path = tf_wav.name
                        mp3_path = wav_path.replace(".wav", ".mp3")
                        try:
                            cmd = [
                                ffmpeg_exe, "-y",
                                "-i", wav_path,
                                "-b:a", "192k",
                                mp3_path
                            ]
                            subprocess.run(cmd, check=True, capture_output=True)
                            with open(mp3_path, "rb") as f_mp3:
                                return f_mp3.read()
                        finally:
                            for p in [wav_path, mp3_path]:
                                if os.path.exists(p):
                                    try: os.unlink(p)
                                    except Exception: pass
                    else:
                        raise RuntimeError("Gemini TTS вернул пустые аудиоданные.")
                except Exception as e:
                    last_error = e
                    err_str = str(e)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        if "per day" in err_str.lower() or "requests per day" in err_str.lower():
                            raise RuntimeError(
                                "Исчерпан суточный лимит бесплатного тарифа Google AI Studio (10 запросов в день на генерацию аудио).\n"
                                "👉 Как продолжить прямо сейчас:\n"
                                "1. Переключите движок на '⚡ Microsoft Edge TTS' (полностью бесплатно и без лимитов).\n"
                                "2. Либо подключите биллинг в Google AI Studio (тариф Pay-as-you-go снимает суточный лимит 10 RPD)."
                            )
                        time.sleep(12.0 * (attempt + 1))
                        break
                    elif "404" in err_str or "NOT_FOUND" in err_str:
                        continue
                    else:
                        time.sleep(2.0 * (attempt + 1))
                        break

        raise RuntimeError(f"Не удалось озвучить через Google Gemini TTS: {last_error}")

    async def _synthesize_chunks_async(
        self, 
        chunks: List[str], 
        output_path: Path,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        concurrency: Optional[int] = None,
        use_cache: bool = True
    ):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        total_chunks = len(chunks)
        if total_chunks == 0:
            return

        concurrency_val = max(1, concurrency or self.concurrency)
        sem = asyncio.Semaphore(concurrency_val)
        results: List[Optional[bytes]] = [None] * total_chunks

        completed_count = 0
        lock = asyncio.Lock()

        async def worker(idx: int, chunk: str):
            nonlocal completed_count
            preview = chunk[:45].replace('\n', ' ')

            # Умное кэширование по содержимому фрагмента, движку и голосу
            audio_data: Optional[bytes] = None
            cache_file: Optional[Path] = None
            if use_cache and self.cache_dir:
                cache_key = hashlib.sha256(f"{self.engine}:{self.voice}:{self.rate}:{chunk.strip()}".encode("utf-8")).hexdigest()
                cache_file = self.cache_dir / f"{cache_key}.mp3"
                if cache_file.exists() and cache_file.stat().st_size > 1000:
                    try:
                        audio_data = cache_file.read_bytes()
                    except Exception:
                        audio_data = None

            if audio_data is None:
                async with sem:
                    if self.engine == "gemini":
                        audio_data = await asyncio.to_thread(self._synthesize_gemini_chunk_with_retry, chunk)
                    else:
                        audio_data = await self._synthesize_chunk_with_retry(chunk)

                    if use_cache and cache_file and audio_data:
                        try:
                            cache_file.write_bytes(audio_data)
                        except Exception:
                            pass

            results[idx] = audio_data

            async with lock:
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count, total_chunks, preview)

        # Параллельный синтез всех блоков через пул воркеров
        await asyncio.gather(*(worker(i, c) for i, c in enumerate(chunks)))

        # Строгая сборка фрагментов в исходном хронологическом порядке
        total_audio = bytearray()
        for r in results:
            if r:
                total_audio.extend(r)

        output_path.write_bytes(total_audio)

    def synthesize_to_file(
        self, 
        text: str, 
        output_path: Path,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        concurrency: Optional[int] = None,
        use_cache: bool = True
    ) -> Path:
        """
        Синтезирует речь с максимальной скоростью (многопоточный асинхронный синтез)
        и сохраняет в MP3-файл.
        Разбивает длинный текст на логические части, гарантируя отсутствие обрывов соединения
        и сохраняя 100% исходное качество звука.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned_text = self.clean_voiceover_text(text)
        if not cleaned_text:
            raise ValueError("Текст для озвучки пуст после очистки.")

        # Синтез через локальный нейросетевой Coqui XTTS-v2 на видеокарте
        if self.engine == "coqui":
            from modules.coqui_tts_client import CoquiTTSClient
            client = CoquiTTSClient()
            return client.synthesize_to_file(
                text=cleaned_text,
                output_path=output_path,
                voice_sample_name=self.voice if (self.voice and self.voice.endswith((".wav", ".mp3"))) else None,
                language="ru",
                progress_callback=progress_callback
            )

        chunks = self.split_into_chunks(cleaned_text, max_chars=self.chunk_size)
        if not chunks:
            raise ValueError("Не удалось сформировать фрагменты для озвучки.")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                self._synthesize_chunks_async(
                    chunks, 
                    output_path, 
                    progress_callback=progress_callback,
                    concurrency=concurrency,
                    use_cache=use_cache
                )
            )
        finally:
            loop.close()

        return output_path

    @staticmethod
    def split_into_parts(text: str, num_parts: int = 4) -> List[Dict[str, Any]]:
        """
        Интеллектуально делит большой дикторский текст на N сбалансированных частей
        строго по границам абзацев и предложений БЕЗ малейшей потери содержания.
        Возвращает список словарей: [{'part_index': 1, 'text': '...', 'words': 500, 'chars': 3500}, ...]
        """
        # Сначала очищаем текст, чтобы делить чистую речь
        cleaned = TTSSynthesizer.clean_voiceover_text(text)
        paragraphs = [p.strip() for p in cleaned.split('\n\n') if p.strip()]
        if not paragraphs:
            return [{"part_index": 1, "text": cleaned, "words": len(cleaned.split()), "chars": len(cleaned)}] if cleaned.strip() else []

        if len(paragraphs) <= num_parts:
            # Если абзацев мало, каждый абзац или пара - отдельная часть
            parts_res = []
            for i, p in enumerate(paragraphs):
                parts_res.append({
                    "part_index": i + 1,
                    "text": p,
                    "words": len(p.split()),
                    "chars": len(p)
                })
            return parts_res

        total_chars = sum(len(p) for p in paragraphs)
        target_part_chars = total_chars / num_parts

        result_parts = []
        current_paras: List[str] = []
        current_chars = 0

        for p in paragraphs:
            current_paras.append(p)
            current_chars += len(p)

            # Если набрали достаточный объем и это еще не последняя часть
            if current_chars >= target_part_chars and len(result_parts) < num_parts - 1:
                part_text = '\n\n'.join(current_paras)
                result_parts.append({
                    "part_index": len(result_parts) + 1,
                    "text": part_text,
                    "words": len(part_text.split()),
                    "chars": len(part_text)
                })
                current_paras = []
                current_chars = 0

        if current_paras:
            part_text = '\n\n'.join(current_paras)
            result_parts.append({
                "part_index": len(result_parts) + 1,
                "text": part_text,
                "words": len(part_text.split()),
                "chars": len(part_text)
            })

        return result_parts

    @staticmethod
    def merge_audio_files(input_files: List[Path], output_file: Path) -> Path:
        """
        Бесшовно склеивает список аудиофайлов MP3 в единый итоговый аудиофайл
        с помощью встроенного ffmpeg без пережатия (lossless concat).
        """
        import subprocess
        import imageio_ffmpeg
        
        valid_files = [f for f in input_files if f.exists() and f.stat().st_size > 1000]
        if not valid_files:
            raise ValueError("Нет готовых аудиофайлов для склейки.")
            
        if len(valid_files) == 1:
            import shutil
            shutil.copy2(valid_files[0], output_file)
            return output_file

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        list_file = output_file.parent / f"temp_concat_{int(time.time())}.txt"
        
        try:
            with open(list_file, "w", encoding="utf-8") as lf:
                for vf in valid_files:
                    clean_path = str(vf.resolve()).replace('\\', '/')
                    lf.write(f"file '{clean_path}'\n")

            cmd = [
                ffmpeg_exe, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_file),
                "-c", "copy",
                str(output_file)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"Ошибка склейки аудио ffmpeg: {res.stderr}")
        finally:
            if list_file.exists():
                try:
                    list_file.unlink()
                except Exception:
                    pass

        return output_file

    @staticmethod
    def list_available_russian_voices() -> List[Dict[str, str]]:
        return [
            {"id": "ru-RU-DmitryNeural", "name": "Дмитрий (Мужской, солидный, документальный)", "gender": "Male"},
            {"id": "ru-RU-SvetlanaNeural", "name": "Светлана (Женский, выразительный)", "gender": "Female"},
        ]

    @staticmethod
    def list_available_gemini_voices() -> List[Dict[str, str]]:
        return [
            {"id": "Milo", "name": "🎙️ Milo (Мужской, стиль: Podcast / Подкаст)", "gender": "Male"},
            {"id": "Nika", "name": "🎙️ Nika (Женский, стиль: Podcast / Подкаст)", "gender": "Female"},
            {"id": "Charon", "name": "Charon (Глубокий кинематографичный бас, детективный/кино)", "gender": "Male"},
            {"id": "Fenrir", "name": "Fenrir (Брутальный, авторитетный мужской)", "gender": "Male"},
            {"id": "Puck", "name": "Puck (Энергичный, харизматичный рассказчик)", "gender": "Male"},
            {"id": "Aoede", "name": "Aoede (Выразительный, эмоциональный женский)", "gender": "Female"},
            {"id": "Kore", "name": "Kore (Спокойный, размеренный, чистый женский)", "gender": "Female"},
        ]
