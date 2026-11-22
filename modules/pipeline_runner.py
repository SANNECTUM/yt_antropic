import os
import re
import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List

from modules.project_manager import ProjectManager
from modules.script_generator import ScriptGenerator
from modules.prompt_generator import PromptGenerator
from modules.image_generator import ImageGenerator
from modules.tts_synthesizer import TTSSynthesizer
from modules.video_editor import VideoEditor
from modules.packaging_generator import PackagingGenerator
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageEnhance

class VideoPipelineRunner:
    """
    Главный оркестратор сквозного авто-конвейера (One-Click Video Conveyor):
    Превращает тему или исходную статью в полностью готовый медиа-комплект:
    1. Режиссерский сценарий с удержанием и клиффхэнгерами
    2. Студийная начитка диктора (MP3)
    3. Авто-генерация 16:9 кадров под каждую сцену (FLUX / Pollinations)
    4. Автоматический монтаж Full HD 1080p с эффектом Кена Бёрнса (FFmpeg)
    5. Виральная обложка с крупным шрифтом + SEO-упаковка (Заголовки, Таймкоды, Описание)
    """

    def __init__(self, project_manager: ProjectManager, model_name: Optional[str] = None):
        self.pm = project_manager
        self.model_name = model_name
        self.script_gen = ScriptGenerator(model_name=model_name)
        self.prompt_gen = PromptGenerator(model_name=model_name)
        self.image_gen = ImageGenerator()
        self.video_editor = VideoEditor()
        self.packaging_gen = PackagingGenerator(model_name=model_name)

    @staticmethod
    def create_high_ctr_thumbnail(
        bg_image_path: Path,
        output_path: Path,
        title_text: str = "ТАЙНА РАСКРЫТА",
        target_size=(1280, 720)
    ) -> Path:
        """
        Создает кликабельную YouTube-обложку:
        - Кадрирование 16:9
        - Затемненный драматический градиент снизу
        - Крупный желто-белый текст с двойной жирной черной обводкой
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.open(bg_image_path).convert("RGB")
        target_w, target_h = target_size

        # Масштабирование и кроп по центру в 16:9
        img_ratio = img.width / img.height
        target_ratio = target_w / target_h
        if img_ratio > target_ratio:
            new_w = int(img.height * target_ratio)
            off = (img.width - new_w) // 2
            img = img.crop((off, 0, off + new_w, img.height))
        else:
            new_h = int(img.width / target_ratio)
            off = (img.height - new_h) // 4
            img = img.crop((0, off, img.width, off + new_h))
        img = img.resize(target_size, Image.Resampling.LANCZOS)

        # Контраст и сочность
        img = ImageEnhance.Contrast(img).enhance(1.25)
        img = ImageEnhance.Color(img).enhance(1.20)

        # Нижний затемняющий градиент под текст
        grad = Image.new("RGBA", target_size, (0, 0, 0, 0))
        draw_g = ImageDraw.Draw(grad)
        for y in range(int(target_h * 0.45), target_h):
            alpha = int(220 * ((y - target_h * 0.45) / (target_h * 0.55)))
            draw_g.line([(0, y), (target_w, y)], fill=(0, 0, 0, min(alpha, 230)))

        comp = Image.alpha_composite(img.convert("RGBA"), grad)
        draw = ImageDraw.Draw(comp)

        # Подбираем шрифт
        font_file = "C:/Windows/Fonts/impact.ttf"
        if not os.path.exists(font_file):
            font_file = "C:/Windows/Fonts/ariblk.ttf"

        # Разбиваем заголовок на 2 короткие ударные строки
        words = [w for w in title_text.upper().replace('"', '').replace("«", "").replace("»", "").split() if w]
        if len(words) <= 3:
            line1 = " ".join(words)
            line2 = ""
        else:
            mid = len(words) // 2
            line1 = " ".join(words[:mid])
            line2 = " ".join(words[mid:])

        lines = [l for l in [line1, line2] if l]
        font_size = 72
        font = ImageFont.truetype(font_file, font_size) if os.path.exists(font_file) else ImageFont.load_default()

        # Подгоняем размер шрифта под ширину экрана
        if os.path.exists(font_file):
            for s in range(76, 36, -4):
                f = ImageFont.truetype(font_file, s)
                widths = [draw.textlength(l, font=f) for l in lines]
                if max(widths) <= int(target_w * 0.90):
                    font_size = s
                    font = f
                    break

        # Отрисовка текста
        spacing = int(font_size * 0.20)
        line_heights = []
        for l in lines:
            bbox = draw.textbbox((0, 0), l, font=font)
            line_heights.append(bbox[3] - bbox[1])
        total_h = sum(line_heights) + spacing * (len(lines) - 1)
        y_curr = target_h - int(target_h * 0.08) - total_h

        colors = [(255, 230, 0), (255, 255, 255)] # Желтый для первой строки, белый для второй
        for idx, l in enumerate(lines):
            bbox = draw.textbbox((0, 0), l, font=font)
            w = bbox[2] - bbox[0]
            x = (target_w - w) // 2
            # Тень и контур
            draw.text((x, y_curr), l, font=font, fill=(0, 0, 0), stroke_width=8, stroke_fill=(0, 0, 0))
            # Заливка
            draw.text((x, y_curr), l, font=font, fill=colors[idx % 2], stroke_width=2, stroke_fill=colors[idx % 2])
            y_curr += line_heights[idx] + spacing

        final_out = comp.convert("RGB")
        final_out.save(output_path, "JPEG", quality=95)
        return output_path

    def run_full_pipeline(
        self,
        topic: str,
        source_materials: str = "",
        genre: str = "Документальный детектив / True Crime",
        target_minutes: int = 5,
        include_tts: bool = False,
        tts_engine: str = "edge",
        tts_voice: str = "ru-RU-DmitryNeural",
        num_visual_scenes: Optional[int] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Запускает цикл сборки видео под ключ:
        1. Сценарий (Gemini)
        2. Озвучка (опционально, если include_tts=True)
        3. Визуалы и раскадровка (FLUX / Pollinations 16:9)
        4. Монтаж видео 1080p с эффектом Ken Burns (FFmpeg)
        5. Обложка и SEO-упаковка
        """
        start_time = time.time()
        self.pm.save_meta({
            "topic": topic.strip(),
            "genre": genre,
            "minutes": target_minutes,
            "include_tts": include_tts,
            "tts_engine": tts_engine,
            "tts_voice": tts_voice
        })
        if source_materials.strip():
            self.pm.save_raw_material(source_materials.strip())

        total_steps = 5 if include_tts else 4
        cur_step = 1

        # ==========================================
        # ЭТАП 1: ГЕНЕРАЦИЯ СЦЕНАРИЯ
        # ==========================================
        if progress_callback:
            progress_callback(0.05, f"Шаг {cur_step}/{total_steps}: Gemini пишет профессиональный сценарий...")

        if target_minutes <= 6:
            script_text = self.script_gen.generate_script(
                topic=topic,
                source_materials=source_materials,
                target_minutes=target_minutes,
                genre=genre
            )
        else:
            outline = self.script_gen.generate_outline(source_materials=source_materials, topic=topic)
            self.pm.save_outline(outline)
            script_text = self.script_gen.generate_script_by_chapters(
                outline_text=outline,
                source_materials=source_materials,
                min_chars_per_chapter=2800
            )

        self.pm.save_script(script_text)
        clean_voiceover = TTSSynthesizer.clean_voiceover_text(script_text)
        self.pm.save_voiceover_clean(clean_voiceover)

        words_count = len(clean_voiceover.split())
        est_duration = max(30.0, (words_count / 135.0) * 60.0)

        if progress_callback:
            progress_callback(0.20, f"Шаг {cur_step}/{total_steps}: Сценарий готов ({words_count:,} слов, ~{words_count//135} мин)!")
        cur_step += 1

        # ==========================================
        # ЭТАП 2: СТУДИЙНАЯ ОЗВУЧКА (ОПЦИОНАЛЬНО)
        # ==========================================
        audio_path = None
        audio_dur = est_duration

        if include_tts:
            if progress_callback:
                progress_callback(0.25, f"Шаг {cur_step}/{total_steps}: Синтез речи диктора ({tts_voice})...")

            audio_path = self.pm.get_audio_path("voiceover_full.mp3")
            tts = TTSSynthesizer(
                voice=tts_voice,
                engine=tts_engine,
                concurrency=4 if tts_engine == "edge" else 2
            )

            def on_tts_prog(cur, tot, prev):
                if progress_callback and tot > 0:
                    p = 0.25 + 0.15 * (cur / tot)
                    progress_callback(p, f"Озвучка: блок {cur}/{tot} ({prev[:30]}...)")

            tts.synthesize_to_file(clean_voiceover, audio_path, progress_callback=on_tts_prog)
            audio_dur = self.video_editor.get_audio_duration(audio_path)

            if progress_callback:
                progress_callback(0.40, f"Шаг {cur_step}/{total_steps}: Озвучка завершена! Длительность речи: {audio_dur/60:.2f} мин ({int(audio_dur)} сек)")
            cur_step += 1
        else:
            # Если озвучка отключена, используем уже имеющийся в проекте аудиофайл (если пользователь озвучил его ранее)
            existing_audio = self.pm.get_audio_path("voiceover_full.mp3")
            if existing_audio.exists() and existing_audio.stat().st_size > 1000:
                audio_path = existing_audio
                audio_dur = self.video_editor.get_audio_duration(audio_path)

        # ==========================================
        # ЭТАП 3: РАСКАДРОВКА И ГЕНЕРАЦИЯ ВИЗУАЛОВ
        # ==========================================
        if progress_callback:
            progress_callback(0.45, f"Шаг {cur_step}/{total_steps}: Генерация визуальных сцен и раскадровки (16:9)...")

        prompts_md = self.prompt_gen.generate_prompts(script_text)
        self.pm.save_prompts(prompts_md)
        scenes = ImageGenerator.parse_prompts_from_markdown(prompts_md)

        # Если раскадровка пустая, генерируем базовые сцены
        if not scenes:
            scenes = [
                {"index": 1, "title": "Завязка истории", "prompt": f"{topic}, dramatic cinematic scene, 8k, photorealistic"},
                {"index": 2, "title": "Расследование", "prompt": f"detective investigation, archives, documents, dramatic lighting"},
                {"index": 3, "title": "Кульминация", "prompt": f"dramatic confrontation, cinematic realism, 8k resolution"}
            ]

        # Рассчитываем оптимальное число кадров (кадр меняется каждые ~6-9 секунд)
        ideal_scenes = max(4, int(audio_dur / 8.0))
        target_scene_count = num_visual_scenes if num_visual_scenes else min(len(scenes), ideal_scenes)
        target_scene_count = max(4, min(target_scene_count, 20)) # От 4 до 20 кадров
        scenes_to_render = scenes[:target_scene_count]

        total_sc = len(scenes_to_render)
        generated_images = []

        for idx, sc in enumerate(scenes_to_render):
            img_path = self.pm.visuals_dir / f"scene_{idx+1:02d}.jpg"
            if progress_callback:
                p = 0.45 + 0.25 * (idx / total_sc)
                progress_callback(p, f"Генерация кадра {idx+1}/{total_sc}: {sc['title'][:35]}...")

            if not (img_path.exists() and img_path.stat().st_size > 5000):
                sc_title = sc.get("title", f"Сцена {idx+1}")
                try:
                    self.image_gen.generate_single_image(
                        sc.get("prompt") or topic,
                        img_path,
                        width=1280,
                        height=720,
                        title=sc_title
                    )
                except Exception:
                    fallback_p = f"{topic}, scene {idx+1}, cinematic movie shot, 8k"
                    try:
                        self.image_gen.generate_single_image(
                            fallback_p,
                            img_path,
                            width=1280,
                            height=720,
                            title=sc_title
                        )
                    except Exception:
                        pass

            if img_path.exists() and img_path.stat().st_size > 5000:
                generated_images.append(img_path)

        if not generated_images:
            raise RuntimeError("Не удалось сгенерировать ни одного изображения для видеоряда.")

        if progress_callback:
            progress_callback(0.70, f"Шаг {cur_step}/{total_steps}: Все {len(generated_images)} кадров успешно созданы!")
        cur_step += 1

        # ==========================================
        # ЭТАП МОНТАЖА ВИДЕО
        # ==========================================
        if progress_callback:
            progress_callback(0.75, f"Шаг {cur_step}/{total_steps}: Монтаж видеоряда в Full HD с эффектом Ken Burns...")

        final_video_path = self.pm.project_dir / "final_video.mp4"

        def on_video_prog(pct, msg):
            if progress_callback:
                p = 0.75 + 0.15 * pct
                progress_callback(p, f"Монтаж: {msg}")

        self.video_editor.assemble_video(
            visuals_dir=self.pm.visuals_dir,
            audio_path=audio_path,
            output_path=final_video_path,
            fps=30,
            resolution="1920x1080",
            ken_burns=True,
            progress_callback=on_video_prog
        )

        if progress_callback:
            progress_callback(0.90, f"Шаг {cur_step}/{total_steps}: Видео смонтировано ({final_video_path.stat().st_size // (1024*1024)} MB)!")
        cur_step += 1

        # ==========================================
        # ЭТАП УПАКОВКИ, ЗАГОЛОВКОВ И ОБЛОЖКИ
        # ==========================================
        if progress_callback:
            progress_callback(0.92, f"Шаг {cur_step}/{total_steps}: Создаем High-CTR обложку и SEO-упаковку для YouTube...")

        titles_text = self.packaging_gen.generate_titles(script_text)
        self.pm.save_titles(titles_text)

        desc_text = self.packaging_gen.generate_description(script_text)
        self.pm.save_description(desc_text)

        # Выбираем лучший заголовок для обложки
        titles_list = PackagingGenerator.parse_titles(titles_text)
        top_title = titles_list[0] if titles_list else topic

        # Генерируем финальную обложку
        thumbnail_path = self.pm.project_dir / "thumbnail.jpg"
        bg_for_thumb = generated_images[0] if generated_images else None
        if bg_for_thumb and bg_for_thumb.exists():
            try:
                self.create_high_ctr_thumbnail(
                    bg_image_path=bg_for_thumb,
                    output_path=thumbnail_path,
                    title_text=top_title
                )
            except Exception:
                pass

        total_elapsed = time.time() - start_time
        if progress_callback:
            progress_callback(1.0, f"🎉 Авто-конвейер полностью завершен за {int(total_elapsed)} сек! Готовы видео, обложка и описание.")

        return {
            "status": "success",
            "video_path": final_video_path,
            "thumbnail_path": thumbnail_path if thumbnail_path.exists() else None,
            "audio_path": audio_path,
            "audio_duration": audio_dur,
            "words_count": words_count,
            "video_size_mb": round(final_video_path.stat().st_size / (1024 * 1024), 1),
            "top_title": top_title,
            "all_titles": titles_list,
            "description": desc_text,
            "elapsed_seconds": int(total_elapsed)
        }
