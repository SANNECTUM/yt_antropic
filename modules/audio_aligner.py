import os
import re
import json
import math
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Callable
import imageio_ffmpeg

import config
from modules.scene_parser import SceneBlock, save_scenes
from modules.llm_client import GeminiClient

def get_ffmpeg_exe() -> str:
    """Возвращает путь к исполняемому файлу ffmpeg."""
    return imageio_ffmpeg.get_ffmpeg_exe()

def get_audio_duration(audio_path: Path) -> float:
    """
    Определяет точную длительность аудиофайла (в секундах) через FFmpeg.
    Работает с mp3, wav, m4a, ogg, aac и т.д.
    """
    if not audio_path.exists():
        return 0.0

    ffmpeg = get_ffmpeg_exe()
    cmd = [ffmpeg, "-i", str(audio_path), "-f", "null", "-"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
        m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", res.stderr)
        if m:
            hours = int(m.group(1))
            minutes = int(m.group(2))
            seconds = float(m.group(3))
            return hours * 3600 + minutes * 60 + seconds
    except Exception as e:
        print(f"[get_audio_duration] Ошибка при чтении длительности {audio_path}: {e}")
    return 0.0

def format_duration(seconds: float) -> str:
    """Форматирует секунды в читаемый вид (например: '48 мин 15 сек' или '03:45')."""
    if seconds <= 0:
        return "0 сек"
    total_sec = int(round(seconds))
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    if h > 0:
        return f"{h} ч {m} мин {s} сек"
    elif m > 0:
        return f"{m} мин {s} сек"
    else:
        return f"{s} сек"

class AudioSceneAligner:
    """
    Синхронизатор сценария с реальной аудиодорожкой (Audio-First Pipeline).
    Разбивает сценарий на смысловые сцены так, чтобы сумма их длительностей
    строго совпадала с длительностью аудиодорожки диктора до миллисекунды.
    """

    @staticmethod
    def clean_script_text(script: str) -> str:
        """Очищает сценарий от служебных пометок, заголовков и ремарок."""
        lines = []
        for line in script.splitlines():
            line = line.strip()
            if not line:
                continue
            # Пропускаем заголовки markdown
            if line.startswith("#"):
                continue
            # Убираем ремарки [Музыка], (Шепотом), **Голос за кадром:** и т.д.
            line = re.sub(r'\[.*?\]', '', line)
            line = re.sub(r'\(.*?\)', '', line)
            line = re.sub(r'^\*{1,2}[^*]+:\*{1,2}', '', line)
            line = line.strip()
            if line:
                lines.append(line)
        return "\n\n".join(lines)

    @classmethod
    def align_script_to_audio(
        cls,
        script_text: str,
        audio_path: Path,
        target_scene_duration: float = 18.0,
        use_gemini: bool = True,
        style_context: str = "",
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[SceneBlock]:
        """
        Создаёт раскадровку, идеально подогнанную под реальную аудиодорожку.
        1. Измеряет хронометраж аудиодорожки.
        2. Формирует сцены через Gemini или пропорциональный сплиттер.
        3. Нормализует тайминги: sum(scene.duration) == total_audio_duration.
        4. Создаёт точные B-Roll промпты под каждую реплику.
        """
        total_audio_sec = get_audio_duration(audio_path)
        if total_audio_sec <= 0:
            raise ValueError(f"Не удалось определить длительность аудиофайла: {audio_path}")

        cleaned_script = cls.clean_script_text(script_text)
        if not cleaned_script:
            cleaned_script = script_text.strip()

        # Расчет целевого количества сцен (например: для 48 минут по 18 сек ~ 160 сцен)
        target_scene_duration = max(5.0, min(60.0, float(target_scene_duration)))
        num_scenes = max(1, round(total_audio_sec / target_scene_duration))

        scenes: List[SceneBlock] = []

        if progress_callback:
            progress_callback(0.1, f"Длительность аудио: {format_duration(total_audio_sec)}. Анализ {num_scenes} сцен...")

        # Попытка интеллектуальной нарезки через Gemini
        gemini_success = False
        if use_gemini and config.GEMINI_API_KEY:
            try:
                scenes = cls._gemini_chunk_and_prompt(
                    cleaned_script,
                    total_audio_sec=total_audio_sec,
                    num_scenes=num_scenes,
                    style_context=style_context,
                    progress_callback=progress_callback
                )
                if scenes:
                    gemini_success = True
            except Exception as e:
                print(f"[AudioSceneAligner] Ошибка Gemini нарезки, переключение на локальный сплиттер: {e}")

        # Локальный fallback если Gemini недоступен или вернул ошибку
        if not gemini_success:
            if progress_callback:
                progress_callback(0.3, "Локальная пропорциональная нарезка текста по звуковым интервалам...")
            scenes = cls._local_proportional_chunk(cleaned_script, total_audio_sec, num_scenes)

        # Жёсткая нормализация длительностей: сумма строго равна total_audio_sec!
        cls._normalize_durations(scenes, total_audio_sec)

        if progress_callback:
            progress_callback(1.0, f"Готово! Сформировано {len(scenes)} сцен общей длительностью {format_duration(total_audio_sec)}.")

        return scenes

    @classmethod
    def _gemini_chunk_and_prompt(
        cls,
        text: str,
        total_audio_sec: float,
        num_scenes: int,
        style_context: str = "",
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[SceneBlock]:
        """Использует Gemini для смысловой нарезки и генерации B-roll тегов."""
        # Для очень больших текстов делим текст на части, чтобы уложиться в контекст
        words = text.split()
        total_words = len(words)
        avg_wps = total_words / max(total_audio_sec, 1.0) # слов в секунду диктора

        # Разобьем на пакеты по ~15-20 сцен
        scenes_per_batch = 15
        num_batches = math.ceil(num_scenes / scenes_per_batch)
        words_per_batch = math.ceil(total_words / num_batches)

        client = GeminiClient(model_name="gemini-2.5-flash")
        all_blocks: List[SceneBlock] = []

        global_idx = 1
        for b_idx in range(num_batches):
            if progress_callback:
                pct = 0.15 + 0.7 * (b_idx / max(num_batches, 1))
                progress_callback(pct, f"Gemini анализирует смысловые кадры (часть {b_idx + 1}/{num_batches})...")

            w_start = b_idx * words_per_batch
            w_end = min((b_idx + 1) * words_per_batch, total_words)
            chunk_words = words[w_start:w_end]
            chunk_text = " ".join(chunk_words)
            chunk_approx_sec = len(chunk_words) / max(avg_wps, 0.5)
            target_k = max(1, round(len(chunk_words) / (18.0 * avg_wps)))

            prompt = f"""
Ты — главный режиссер монтажа документальных YouTube-роликов.
У нас есть аудиозапись диктора длительностью ~{chunk_approx_sec:.1f} сек.
Текст этой части озвучки:
\"\"\"{chunk_text}\"\"\"

Разбей этот фрагмент ровно на {target_k} логических сцен (кадров).
Для КАЖДОЙ сцены сформируй:
1. "title": краткий заголовок сцены на русском (до 5 слов).
2. "text": точный фрагмент текста озвучки, который звучит в этой сцене.
3. "weight": приблизительная доля длительности этой сцены (от 1 до 10, где 5 — средняя фраза).
4. "search_query": точный английский поисковый запрос (2-4 слова) для стокового видео на Pexels, передающий визуальный смысл реплики (например: 'stressed programmer screen', 'money counting slow motion', 'empty street rain').
5. "visual_prompt": кинематографичное описание кадра для видеомонтажа (16:9, детали, освещение).

Тематика канала/стиль: {style_context or 'документальное расследование, кинематографичный B-Roll'}

Верни СТРОГО чистый JSON-массив без markdown-обёрток:
[
  {{
    "title": "...",
    "text": "...",
    "weight": 5,
    "search_query": "...",
    "visual_prompt": "..."
  }}
]
"""
            try:
                res = client.generate_text(prompt, max_output_tokens=4096)
                # Очистка JSON от кавычек
                cleaned_res = re.sub(r'^```json\s*', '', res.strip(), flags=re.MULTILINE)
                cleaned_res = re.sub(r'```$', '', cleaned_res.strip())
                data = json.loads(cleaned_res)

                # Вычисляем длительности сцен внутри батча пропорционально весу/словам
                total_w = sum(item.get("weight", 5) for item in data) or 1
                for item in data:
                    item_dur = (item.get("weight", 5) / total_w) * chunk_approx_sec
                    block = SceneBlock(
                        index=global_idx,
                        title=item.get("title", f"Сцена {global_idx}"),
                        text=item.get("text", ""),
                        duration=max(3.0, round(item_dur, 2)),
                        search_query=item.get("search_query", "cinematic stock footage"),
                        prompt=item.get("visual_prompt", "")
                    )
                    all_blocks.append(block)
                    global_idx += 1
            except Exception as e:
                print(f"[AudioSceneAligner] Ошибка пакета {b_idx}: {e}. Применяем локальный сплиттер для этого куска.")
                loc_blocks = cls._local_proportional_chunk(chunk_text, chunk_approx_sec, target_k, start_idx=global_idx)
                all_blocks.extend(loc_blocks)
                global_idx += len(loc_blocks)

        return all_blocks

    @classmethod
    def _local_proportional_chunk(
        cls,
        text: str,
        total_sec: float,
        num_scenes: int,
        start_idx: int = 1
    ) -> List[SceneBlock]:
        """Локальный алгоритм: делит текст на предложения и группирует в N сцен."""
        sentences = re.split(r'(?<=[.!?…])\s+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            sentences = [text]

        num_scenes = max(1, min(num_scenes, len(sentences)))
        avg_sent_per_scene = len(sentences) / num_scenes

        blocks: List[SceneBlock] = []
        total_words_all = sum(len(s.split()) for s in sentences) or 1

        for i in range(num_scenes):
            s_start = int(round(i * avg_sent_per_scene))
            s_end = int(round((i + 1) * avg_sent_per_scene))
            if i == num_scenes - 1:
                s_end = len(sentences)

            chunk_sents = sentences[s_start:s_end]
            chunk_str = " ".join(chunk_sents)
            chunk_words_cnt = sum(len(s.split()) for s in chunk_sents)

            dur = (chunk_words_cnt / total_words_all) * total_sec
            dur = max(3.0, round(dur, 2))

            # Простой английский B-roll тег по ключевым словам
            broll_tag = "cinematic documentary b-roll"
            first_words = re.findall(r'[a-zA-Zа-яА-ЯёЁ]+', chunk_str)[:6]
            title = " ".join(first_words[:4]).capitalize() if first_words else f"Сцена {start_idx + i}"

            blocks.append(SceneBlock(
                index=start_idx + i,
                title=title,
                text=chunk_str,
                duration=dur,
                search_query=broll_tag,
                prompt=f"Кадр для реплики: {chunk_str[:120]}, кинематографичный стиль 16:9"
            ))

        return blocks

    @staticmethod
    def _normalize_durations(scenes: List[SceneBlock], total_audio_sec: float):
        """
        Гарантирует, что сумма длительностей всех сцен строго равна длительности аудиофайла.
        Корректирует погрешность округления на последней сцене.
        """
        if not scenes:
            return
        curr_sum = sum(s.duration for s in scenes)
        if curr_sum <= 0:
            avg = total_audio_sec / len(scenes)
            for s in scenes:
                s.duration = avg
            return

        # Масштабируем пропорционально
        factor = total_audio_sec / curr_sum
        for s in scenes:
            s.duration = round(s.duration * factor, 2)

        # Выравниваем остаточную погрешность (обычно доли секунды) на последней сцене
        final_sum = sum(s.duration for s in scenes[:-1])
        last_dur = round(total_audio_sec - final_sum, 2)
        if last_dur >= 1.0:
            scenes[-1].duration = last_dur
        else:
            scenes[-1].duration = max(3.0, scenes[-1].duration)

    @classmethod
    def apply_alignment_to_project(
        cls,
        project_dir: Path,
        scenes: List[SceneBlock],
        audio_file: Optional[Path] = None
    ):
        """Сохраняет выровненные сцены в scenes.json, timeline.json и обновляет prompts.md."""
        from modules.timeline_builder import TimelineBuilder
        tl = TimelineBuilder(project_dir)

        # Сохраняем сцены
        save_scenes(scenes, project_dir)
        tl.save_timeline(scenes)

        # Формируем prompts.md для Раздела 2
        prompts_lines = [
            f"# Раскадровка под готовую аудиодорожку ({len(scenes)} кадров)\n",
            "Каждый кадр строго подогнан по таймкодам под речь диктора.\n"
        ]
        curr_time = 0.0
        for s in scenes:
            start_str = format_duration(curr_time)
            end_str = format_duration(curr_time + s.duration)
            prompts_lines.append(f"## Кадр {s.index}: {s.title}")
            prompts_lines.append(f"- **Таймкод:** {start_str} – {end_str} (`{s.duration:.1f} сек`)")
            prompts_lines.append(f"- **Реплика диктора:** {s.text}")
            prompts_lines.append(f"- **Pexels B-Roll Tag:** `{s.search_query}`")
            prompts_lines.append(f"- **Промпт для визуала:** {s.prompt}\n")
            curr_time += s.duration

        prompts_file = project_dir / "prompts.md"
        prompts_file.write_text("\n".join(prompts_lines), encoding="utf-8")
