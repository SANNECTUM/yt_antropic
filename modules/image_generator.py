import re
import os
import io
import urllib.request
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import config
from modules.web_image_search import WebImageSearcher

class ImageGenerator:
    def __init__(self, provider: str = "flux"):
        self.provider = provider
        self.searcher = WebImageSearcher()

    @staticmethod
    def parse_prompts_from_markdown(md_text: str) -> List[Dict[str, Any]]:
        """
        Универсальный парсер сцен и кадров из prompts.md.
        Извлекает заголовок сцены с точным таймингом, кадры, тип (ФОТО/ВИДЕО), таймкод и промпт.
        """
        scenes = []
        scene_blocks = re.split(r'(?m)^(?=###?\s*(?:Сцена|Кадр)\s*\d+)', md_text)
        
        for block in scene_blocks:
            block = block.strip()
            if not block or not re.match(r'^###?\s*(?:Сцена|Кадр)\s*\d+', block, re.IGNORECASE):
                continue

            # Заголовок сцены (содержит номер, название и тайминг, например: Сцена 1: Цифровой свидетель (00:00 - 00:30))
            header_line = block.splitlines()[0].strip('# \t*')

            # Куда ставить в ролике
            place_m = re.search(r'\*\s*\*\*Куда ставить[^\n:]*:\*\*\s*([^\n]+)', block, re.IGNORECASE)
            if not place_m:
                place_m = re.search(r'Куда ставить[^\n:]*:\s*([^\n]+)', block, re.IGNORECASE)
            common_placement = place_m.group(1).strip() if place_m else ""

            # Проверяем, есть ли отдельные кадры (* **Кадр X**)
            frame_matches = list(re.finditer(r'(?m)^\s*\*\s*\*\*(Кадр\s*\d+[^\n*]*)\*\*', block))

            if frame_matches:
                for i, fm in enumerate(frame_matches):
                    frame_title = fm.group(1).strip()
                    start_pos = fm.end()
                    end_pos = frame_matches[i+1].start() if i+1 < len(frame_matches) else len(block)
                    f_chunk = block[start_pos:end_pos]

                    type_m = re.search(r'Тип\s*(?:материала|кадра|визуала)?[^\n:]*:\s*([^\n]+)', f_chunk, re.IGNORECASE)
                    raw_type = type_m.group(1).lower() if type_m else ""
                    media_type = "ВИДЕО" if ("видео" in raw_type or "video" in raw_type) else "ФОТО"

                    prompt_m = re.search(r'Промпт[^\n:]*:\s*(?:>\s*|\n\s*>\s*|\n\s*)([^\n]+(?:\n\s*>[^\n]+|\n\s{4,}[^\n]+)*)', f_chunk, re.IGNORECASE)
                    if not prompt_m:
                        prompt_m = re.search(r'>\s*([^\n]+(?:\n\s*>[^\n]+|\n\s{4,}[^\n]+)*)', f_chunk)

                    raw_prompt = prompt_m.group(1) if prompt_m else ""
                    clean_prompt = re.sub(r'^\s*>\s*', '', raw_prompt, flags=re.MULTILINE)
                    clean_prompt = " ".join(clean_prompt.split()).strip('`"\'* ')

                    full_title = f"{header_line} — {frame_title}"
                    safe_slug = re.sub(r'[^a-zA-Z0-9_-]', '_', full_title[:25]).strip('_').lower()
                    ext = "mp4" if media_type == "ВИДЕО" else "jpg"
                    filename = f"scene_{len(scenes) + 1:02d}_{safe_slug}.{ext}"

                    scenes.append({
                        "index": len(scenes) + 1,
                        "title": full_title,
                        "media_type": media_type,
                        "placement": common_placement,
                        "prompt": clean_prompt,
                        "filename": filename
                    })
            else:
                type_m = re.search(r'Тип\s*(?:материала|кадра|визуала)?[^\n:]*:\s*([^\n]+)', block, re.IGNORECASE)
                raw_type = type_m.group(1).lower() if type_m else ""
                media_type = "ВИДЕО" if ("видео" in raw_type or "video" in raw_type) else "ФОТО"

                prompt_m = re.search(r'Промпт[^\n:]*:\s*(?:>\s*|\n\s*>\s*|\n\s*)([^\n]+(?:\n\s*>[^\n]+|\n\s{4,}[^\n]+)*)', block, re.IGNORECASE)
                if not prompt_m:
                    prompt_m = re.search(r'>\s*([^\n]+(?:\n\s*>[^\n]+|\n\s{4,}[^\n]+)*)', block)
                raw_prompt = prompt_m.group(1) if prompt_m else ""
                clean_prompt = re.sub(r'^\s*>\s*', '', raw_prompt, flags=re.MULTILINE)
                clean_prompt = " ".join(clean_prompt.split()).strip('`"\'* ')

                safe_slug = re.sub(r'[^a-zA-Z0-9_-]', '_', header_line[:25]).strip('_').lower()
                ext = "mp4" if media_type == "ВИДЕО" else "jpg"
                filename = f"scene_{len(scenes) + 1:02d}_{safe_slug}.{ext}"

                scenes.append({
                    "index": len(scenes) + 1,
                    "title": header_line,
                    "media_type": media_type,
                    "placement": common_placement,
                    "prompt": clean_prompt,
                    "filename": filename
                })

        return scenes

    @staticmethod
    def extract_batch_packages(md_text: str) -> List[Dict[str, str]]:
        """
        Извлекает готовые пакеты для чата Gemini Web из markdown текста, если они есть.
        """
        packages = []
        pattern = r'###?\s*([📦\w\s\d]+(?:ПАКЕТ|Серия)[^\n]*)\n*```(?:text|markdown)?\s*\n(.*?)\n```'
        matches = re.findall(pattern, md_text, re.DOTALL | re.IGNORECASE)
        for title, content in matches:
            packages.append({
                "title": title.strip(),
                "content": content.strip()
            })
        return packages

    @staticmethod
    def crop_to_16_9(img: Image.Image, target_size=(1280, 720)) -> Image.Image:
        """Обрезает и масштабирует любое изображение строго в 16:9 (1280x720)."""
        target_w, target_h = target_size
        img = img.convert("RGB")
        img_ratio = img.width / img.height
        target_ratio = target_w / target_h
        if img_ratio > target_ratio:
            new_w = int(img.height * target_ratio)
            off = (img.width - new_w) // 2
            img = img.crop((off, 0, off + new_w, img.height))
        else:
            new_h = int(img.width / target_ratio)
            off = (img.height - new_h) // 2
            img = img.crop((0, off, img.width, off + new_h))
        return img.resize(target_size, Image.Resampling.LANCZOS)

    @staticmethod
    def generate_cinematic_card(output_path: Path, title: str = "", width: int = 1280, height: int = 720) -> Path:
        """Создает стильный темный кинематографичный слайд 16:9 с заголовком."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (width, height), (15, 18, 24))
        draw = ImageDraw.Draw(img)

        # Рисуем мягкий вертикальный градиент
        for y in range(height):
            ratio = y / height
            r = int(12 + ratio * 15)
            g = int(16 + ratio * 20)
            b = int(24 + ratio * 32)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Тонкая золотисто-синяя кинематографичная рамка
        draw.rectangle([(20, 20), (width - 20, height - 20)], outline=(40, 60, 90), width=2)

        # Текст
        if title:
            font_file = "C:/Windows/Fonts/calibrib.ttf"
            if not os.path.exists(font_file):
                font_file = "C:/Windows/Fonts/arialbd.ttf"

            font_size = 42
            font = ImageFont.truetype(font_file, font_size) if os.path.exists(font_file) else ImageFont.load_default()

            words = title.strip().split()
            lines = []
            cur_line = []
            for w in words:
                cur_line.append(w)
                bbox = draw.textbbox((0, 0), " ".join(cur_line), font=font)
                if (bbox[2] - bbox[0]) > (width * 0.75):
                    cur_line.pop()
                    if cur_line:
                        lines.append(" ".join(cur_line))
                    cur_line = [w]
            if cur_line:
                lines.append(" ".join(cur_line))

            total_h = len(lines) * (font_size + 12)
            y_curr = (height - total_h) // 2
            for l in lines:
                bbox = draw.textbbox((0, 0), l, font=font)
                x = (width - (bbox[2] - bbox[0])) // 2
                draw.text((x + 2, y_curr + 2), l, font=font, fill=(0, 0, 0))
                draw.text((x, y_curr), l, font=font, fill=(240, 245, 255))
                y_curr += font_size + 12

        img.save(output_path, "JPEG", quality=90)
        return output_path

    @staticmethod
    def _translate_to_english(text: str) -> str:
        """
        Переводит русский текст промпта в английский через Gemini Flash
        для лучшего качества AI-генерации. При ошибке возвращает исходный текст.
        """
        try:
            from modules.llm_client import GeminiClient
            client = GeminiClient()
            response = client.generate(
                "Translate this image generation prompt to English. "
                "Return ONLY the translated prompt, no explanations:\n\n" + text,
                temperature=0.3
            )
            translated = response.strip().strip('"\'*`')
            return translated if translated else text
        except Exception as e:
            print(f"[ImageGen] Перевод не удался: {e}")
            return text

    def generate_single_image(
        self,
        prompt: str,
        output_path: Path,
        negative_prompt: str = "",
        width: int = 1280,
        height: int = 720,
        title: str = ""
    ) -> Path:
        """
        Генератор 16:9 изображений с многоуровневым fallback:
        0. Локальный AUTOMATIC1111 SD WebUI (если запущен на 127.0.0.1:7860).
        1. Pollinations AI (turbo) — с переводом промпта на английский и негативными фильтрами.
        2. Yandex / Bing скрейпинг — поиск реальных архивных кадров высокого разрешения.
        3. Кинематографичный слайд — гарантированный результат.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_p = output_path.parent / f"temp_{output_path.name}"

        # Уровень 0: Локальный AUTOMATIC1111 (если запущен на вашем ПК)
        try:
            import requests
            sd_url = "http://127.0.0.1:7860/sdapi/v1/txt2img"
            payload = {
                "prompt": prompt,
                "negative_prompt": negative_prompt or "ugly, deformed, bad anatomy, blurry, cartoon, text, watermark",
                "steps": 20,
                "sampler_name": "DPM++ 2M Karras",
                "cfg_scale": 7.0,
                "width": width,
                "height": height,
                "restore_faces": True,
            }
            res = requests.post(sd_url, json=payload, timeout=60)
            if res.status_code == 200:
                import base64
                b64 = res.json()["images"][0]
                output_path.write_bytes(base64.b64decode(b64))
                print(f"[ImageGen] ✅ Локальный Automatic1111 WebUI: {output_path.name}")
                return output_path
        except Exception:
            pass  # локальный WebUI не запущен, переходим к следующему уровню

        # Уровень 1: Pollinations AI (turbo)
        try:
            # Если промпт на русском, переводим
            has_cyrillic = bool(re.search(r'[\u0400-\u04FF]', prompt))
            en_prompt = self._translate_to_english(prompt) if has_cyrillic else prompt

            # Обогащаем промпт
            enhanced = f"{en_prompt.strip()[:240]}, cinematic lighting, 8k resolution, photorealistic"
            encoded = urllib.parse.quote(enhanced)

            import random
            seed = random.randint(1, 999999)
            url = (
                f"https://image.pollinations.ai/prompt/{encoded}"
                f"?width={width}&height={height}&nologo=true&model=turbo&seed={seed}"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            if len(data) > 10000:
                output_path.write_bytes(data)
                print(f"[ImageGen] ✅ Pollinations AI: {len(data)//1024}KB → {output_path.name}")
                return output_path
            else:
                print(f"[ImageGen] ⚠️ Pollinations вернул слишком малый файл ({len(data)} байт)")
        except Exception as e:
            print(f"[ImageGen] ⚠️ Pollinations недоступен: {e}")

        # Уровень 2: Yandex & Bing поиск реальных фото
        try:
            clean_q = re.sub(
                r'cinematic|documentary|8k|photorealistic|resolution|sharp focus|film grain|35mm|кинематографичн\w*|документальн\w*|реализм|драматическ\w*|4[Kk]|16:9',
                '', prompt, flags=re.IGNORECASE
            )
            clean_q = " ".join(clean_q.split()[:7]).strip(',. ')
            if not clean_q or len(clean_q) < 4:
                clean_q = title or "архивные хроники"

            # Сначала Yandex (отлично находит реальные фото и хэш-архивы)
            results = self.searcher.search_yandex(clean_q, limit=6)
            if not results:
                results = self.searcher.search_bing(f"{clean_q} 4k", limit=5)

            print(f"[ImageGen] 🔍 Поиск в сети ({clean_q}): {len(results)} результатов")
            for r in results:
                img_url = r.get("image_url")
                if not img_url:
                    continue
                try:
                    self.searcher.download_image(img_url, temp_p, thumb_url=r.get("thumb_url"))
                    if temp_p.exists() and temp_p.stat().st_size > 6000:
                        with Image.open(temp_p) as raw_img:
                            if raw_img.width < 400 or raw_img.height < 300:
                                continue
                            final_16_9 = self.crop_to_16_9(raw_img, (width, height))
                            final_16_9.save(output_path, "JPEG", quality=92)
                        temp_p.unlink(missing_ok=True)
                        print(f"[ImageGen] ✅ Кадр из сети: {r.get('title','')[:40]} → {output_path.name}")
                        return output_path
                except Exception:
                    if temp_p.exists():
                        temp_p.unlink(missing_ok=True)
                    continue
        except Exception as e:
            print(f"[ImageGen] ⚠️ Поиск в сети упал: {e}")

        # Уровень 3: Гарантированный кинематографичный слайд
        print(f"[ImageGen] ℹ️ Создаём кинематографичный слайд для '{title or prompt[:40]}'")
        return self.generate_cinematic_card(output_path, title=title or prompt[:60], width=width, height=height)
