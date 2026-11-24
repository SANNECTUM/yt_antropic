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
from modules.article_parser import ArticleParser
from modules.audio_aligner import AudioSceneAligner
from modules.pexels_downloader import PexelsDownloader
from modules.timeline_builder import TimelineBuilder
from modules.scene_parser import save_scenes
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
        topic: str = "",
        source_materials: str = "",
        article_url: Optional[str] = None,
        genre: str = "Документальный детектив / True Crime",
        target_minutes: int = 5,
        include_tts: bool = True,
        tts_engine: str = "edge",
        tts_voice: str = "ru-RU-DmitryNeural",
        visual_mode: str = "pexels",
        num_visual_scenes: Optional[int] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Запускает полный цикл сборки видео БЕЗ участия человека:
        0. Авто-парсинг статьи по URL (если передана ссылка)
        1. Профессиональный сценарий с удержанием и клиффхэнгерами (Gemini)
        2. Студийная начитка диктора (Edge TTS / Coqui XTTS на RTX 4060 Ti)
        3. Раскадровка под хронометраж звука и автопилот Pexels (уникальные видео без повторов)
        4. Моментальный монтаж Full HD/HD видеоряда (FFmpeg stream copy)
        5. Финальное сведение с озвучкой, High-CTR обложка и SEO-упаковка для YouTube
        """
        start_time = time.time()
        total_steps = 6
        cur_step = 1

        # ==========================================
        # ЭТАП 0: ПАРСИНГ СТАТЬИ ПО ССЫЛКЕ
        # ==========================================
        clean_url = (article_url or "").strip()
        if clean_url:
            if progress_callback:
                progress_callback(0.04, f"Шаг {cur_step}/{total_steps}: Загрузка и анализ статьи по ссылке...")
            parse_res = ArticleParser.parse_url(clean_url)
            if parse_res.get("success"):
                extracted_txt = parse_res.get("text", "")
                extracted_title = parse_res.get("title", "")
                if not source_materials.strip():
                    source_materials = extracted_txt
                if not topic.strip() and extracted_title:
                    topic = extracted_title
            cur_step += 1

        if not topic.strip():
            topic = "Интересная история и расследование"

        self.pm.save_meta({
            "topic": topic.strip(),
            "genre": genre,
            "minutes": target_minutes,
            "include_tts": include_tts,
            "tts_engine": tts_engine,
            "tts_voice": tts_voice,
            "visual_mode": visual_mode,
            "article_url": clean_url
        })
        if source_materials.strip():
            self.pm.save_raw_material(source_materials.strip())

        # ==========================================
        # ЭТАП 1: ГЕНЕРАЦИЯ СЦЕНАРИЯ
        # ==========================================
        if progress_callback:
            progress_callback(0.12, f"Шаг {cur_step}/{total_steps}: Gemini пишет сценарий для YouTube...")

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
            progress_callback(0.24, f"Шаг {cur_step}/{total_steps}: Сценарий готов ({words_count} слов, ~{int(est_duration//60)} мин)!")
        cur_step += 1

        # ==========================================
        # ЭТАП 2: СТУДИЙНАЯ ОЗВУЧКА
        # ==========================================
        audio_path = self.pm.get_audio_path("voiceover_full.mp3")
        audio_dur = est_duration

        if include_tts:
            if progress_callback:
                progress_callback(0.28, f"Шаг {cur_step}/{total_steps}: Озвучка диктором ({tts_engine.upper()})...")

            tts = TTSSynthesizer(
                voice=tts_voice,
                engine=tts_engine,
                concurrency=4 if tts_engine == "edge" else 1
            )

            def on_tts_prog(cur, tot, prev):
                if progress_callback and tot > 0:
                    p = 0.28 + 0.16 * (cur / tot)
                    progress_callback(p, f"Озвучка: блок {cur}/{tot}...")

            tts.synthesize_to_file(clean_voiceover, audio_path, progress_callback=on_tts_prog)
            from modules.audio_aligner import get_audio_duration
            audio_dur = get_audio_duration(audio_path)
            if audio_dur <= 0:
                audio_dur = est_duration

            m = self.pm.load_meta()
            m["active_audio"] = audio_path.name
            self.pm.save_meta(m)

            if progress_callback:
                progress_callback(0.46, f"Шаг {cur_step}/{total_steps}: Озвучка готова ({int(audio_dur//60)}м {int(audio_dur%60)}с)!")
            cur_step += 1
        else:
            existing_audio = self.pm.get_audio_path("voiceover_full.mp3")
            if existing_audio.exists() and existing_audio.stat().st_size > 1000:
                audio_path = existing_audio

        # ==========================================
        # ЭТАП 3: РАСКАДРОВКА И ПОДБОР ВИЗУАЛОВ
        # ==========================================
        tl_builder = TimelineBuilder(self.pm.project_dir)
        final_video_path = self.pm.project_dir / "final_video.mp4"

        if visual_mode == "pexels":
            if progress_callback:
                progress_callback(0.50, f"Шаг {cur_step}/{total_steps}: Точная нарезка сцен под реальный голос...")

            # 1. Синхронизируем сценарий строго под полученный звук
            aligned_scenes = AudioSceneAligner.align_script_to_audio(
                script_text=clean_voiceover,
                audio_path=audio_path,
                target_scene_duration=18.0,
                use_gemini=False,
                style_context=topic
            )
            save_scenes(aligned_scenes, self.pm.project_dir)
            tl_builder.save_timeline(aligned_scenes)

            # 2. Генерируем лаконичные 2-3 словные теги для Pexels
            if progress_callback:
                progress_callback(0.56, f"Шаг {cur_step}/{total_steps}: Генерация B-roll запросов под сцены...")
            px_downloader = PexelsDownloader()
            queries = px_downloader.generate_broll_queries(
                [s.text for s in aligned_scenes],
                style_context=topic
            )
            for i, s in enumerate(aligned_scenes):
                if i < len(queries):
                    s.search_query = queries[i]

            # 3. Автопилот Pexels: скачиваем уникальные ролики БЕЗ ПОВТОРОВ
            if progress_callback:
                progress_callback(0.62, f"Шаг {cur_step}/{total_steps}: Автопилот Pexels скачивает видео...")

            used_ids = set()
            total_sc = len(aligned_scenes)
            for idx, s in enumerate(aligned_scenes):
                dest_file = self.pm.visuals_dir / f"scene_{s.index:03d}.mp4"
                rel_path = f"visuals/{dest_file.name}"
                q = s.search_query.strip() or "cinematic documentary"

                if progress_callback:
                    p = 0.62 + 0.16 * ((idx + 1) / max(total_sc, 1))
                    progress_callback(p, f"Кадр {idx+1}/{total_sc}: Pexels видео '{q}'...")

                vids = px_downloader.search_videos(q, limit=6)
                if vids:
                    chosen = None
                    for v in vids:
                        v_id = v.get("id") or v.get("download_url")
                        if v_id not in used_ids:
                            chosen = v
                            used_ids.add(v_id)
                            break
                    if not chosen:
                        chosen = vids[0]
                    if px_downloader.download_video_file(chosen["download_url"], dest_file):
                        s.visual_path = rel_path

            save_scenes(aligned_scenes, self.pm.project_dir)
            tl_builder.save_timeline(aligned_scenes)

            # 4. Монтаж видеотрека и сведение со звуком
            if progress_callback:
                progress_callback(0.80, f"Шаг {cur_step}/{total_steps}: Склейка видеоряда через FFmpeg...")

            tl_builder.build_videotrack(aligned_scenes, force=True, resolution=(1280, 720))
            tl_builder.mix_with_audio(audio_path if audio_path.exists() else None)

        else:
            # Режим нейро-изображений (FLUX / Pollinations)
            if progress_callback:
                progress_callback(0.52, f"Шаг {cur_step}/{total_steps}: Генерация 16:9 иллюстраций...")
            prompts_md = self.prompt_gen.generate_prompts(script_text)
            self.pm.save_prompts(prompts_md)
            raw_scenes = ImageGenerator.parse_prompts_from_markdown(prompts_md)
            if not raw_scenes:
                raw_scenes = [{"index": 1, "title": "Завязка", "prompt": f"{topic}, cinematic 16:9"}]

            scenes_to_render = raw_scenes[:min(len(raw_scenes), 10)]
            for idx, sc in enumerate(scenes_to_render):
                img_path = self.pm.visuals_dir / f"scene_{idx+1:02d}.jpg"
                if not img_path.exists():
                    self.image_gen.generate_single_image(sc.get("prompt") or topic, img_path, width=1280, height=720)

            self.video_editor.assemble_video(
                visuals_dir=self.pm.visuals_dir,
                audio_path=audio_path,
                output_path=final_video_path,
                resolution="1280x720",
                ken_burns=True
            )

        cur_step += 1

        # ==========================================
        # ЭТАП 5: SEO-УПАКОВКА И ЧЕРНОВИК ОБЛОЖКИ
        # ==========================================
        if progress_callback:
            progress_callback(0.92, f"Шаг {cur_step}/{total_steps}: Генерация кликабельных заголовков и описания...")

        titles_text = self.packaging_gen.generate_titles(script_text)
        self.pm.save_titles(titles_text)
        desc_text = self.packaging_gen.generate_description(script_text)
        self.pm.save_description(desc_text)

        titles_list = PackagingGenerator.parse_titles(titles_text)
        top_title = titles_list[0] if titles_list else topic

        thumbnail_path = self.pm.project_dir / "thumbnail.jpg"
        all_imgs = sorted(list(self.pm.visuals_dir.glob("*.jpg")) + list(self.pm.visuals_dir.glob("*.png")))
        if all_imgs:
            try:
                self.create_high_ctr_thumbnail(
                    bg_image_path=all_imgs[0],
                    output_path=thumbnail_path,
                    title_text=top_title
                )
            except Exception:
                pass

        total_elapsed = time.time() - start_time
        if progress_callback:
            progress_callback(1.0, f"🎉 Полный автомат завершен за {int(total_elapsed)} сек! Ролик готов к публикации.")

        return {
            "status": "success",
            "video_path": final_video_path,
            "thumbnail_path": thumbnail_path if thumbnail_path.exists() else None,
            "audio_path": audio_path,
            "audio_duration": audio_dur,
            "words_count": words_count,
            "video_size_mb": round(final_video_path.stat().st_size / (1024 * 1024), 1) if final_video_path.exists() else 0,
            "top_title": top_title,
            "all_titles": titles_list,
            "description": desc_text,
            "elapsed_seconds": int(total_elapsed)
        }
