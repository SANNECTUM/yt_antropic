import re
import math
from typing import Optional, List, Dict, Any, Callable
from modules.llm_client import GeminiClient

SYSTEM_PROMPT_GENERATOR_PROMPT = """
Ты — главный режиссер-постановщик и арт-директор топовых YouTube-документалок и познавательных проектов (уровня Netflix, HBO, National Geographic).

Твоя задача: превратить сценарий в ПРОФЕССИОНАЛЬНЫЙ ПАКЕТ ПРОМПТОВ ДЛЯ ГЕНЕРАЦИИ ИЗОБРАЖЕНИЙ (ФОТО 16:9) ДЛЯ КАЖДЫХ 30 СЕКУНД ТЕКСТА.

КАТЕГОРИЧЕСКИЕ ПРАВИЛА:
1. СТРОГО ТОЛЬКО ИЗОБРАЖЕНИЯ (ФОТО 16:9):
   - Никаких «ВИДЕО», никакой анимации и никаких описаний движения камеры (никаких «наездов», «пролетов» или «панорамирования»).
   - Только статические, высокохудожественные кинематографичные кадры (фото 16:9), подходящие для Midjourney, Fooocus, Stable Diffusion и Gemini Image.

2. СТРОГАЯ РАСКАДРОВКА ПО 30 СЕКУНД:
   - Каждый кадр покрывает ровно указанный 30-секундный отрезок речи диктора.
   - Формат заголовка: ### Кадр [Номер]: [Краткое название] ([Точный таймкод: 00:00 - 00:30])

3. СТРУКТУРА КАЖДОГО ПРОМПТА:
   - Промпт пишется на богатом, выразительном русском языке.
   - Обязательно укажи: композицию (общий план / крупный план / средний план), освещение (драматичный свет, сумерки, мягкий рассеянный свет), детали окружения, текстуру (пленочное зерно 35мм, документальная эстетика) и формат 16:9.

4. БЕЗОПАСНОСТЬ (SAFE PROMPTING):
   - Никаких стоп-слов, вызывающих цензуру нейросетей (без откровенной крови и насилия).
   - Передавай драматизм через холодную гамму, свет, тревожные силуэты и реалистичные детали окружения.
"""


def split_into_time_slices(text: str, interval_seconds: int = 30, wpm: int = 135) -> List[Dict[str, Any]]:
    """
    Разбивает текст сценария на логические смысловые отрезки по interval_seconds (по умолчанию 30 сек).
    Учитывает средний темп речи диктора (135 слов в минуту = ~67 слов за 30 сек)
    и разбивает строго по границам предложений.
    """
    # Убираем грубую разметку
    clean = re.sub(r'#{1,6}\s*', '', text)
    clean = re.sub(r'^\s*[-*]\s*', '', clean, flags=re.MULTILINE)
    clean = clean.strip()

    words_per_slice = max(25, int((interval_seconds / 60.0) * wpm))

    # Делим на предложения
    raw_sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean) if s.strip()]
    if not raw_sentences:
        raw_sentences = [clean]

    slices = []
    current_sentences = []
    current_words = 0

    for sent in raw_sentences:
        w_count = len(sent.split())
        if current_words + w_count > words_per_slice and current_sentences:
            slices.append(" ".join(current_sentences))
            current_sentences = [sent]
            current_words = w_count
        else:
            current_sentences.append(sent)
            current_words += w_count

    if current_sentences:
        slices.append(" ".join(current_sentences))

    # Формируем структуру с точными таймкодами
    items = []
    for idx, chunk in enumerate(slices):
        start_sec = idx * interval_seconds
        end_sec = (idx + 1) * interval_seconds
        start_str = f"{start_sec // 60:02d}:{start_sec % 60:02d}"
        end_str = f"{end_sec // 60:02d}:{end_sec % 60:02d}"
        items.append({
            "index": idx + 1,
            "timecode": f"{start_str} - {end_str}",
            "text": chunk,
            "words": len(chunk.split())
        })

    return items


class PromptGenerator:
    def __init__(self, model_name: Optional[str] = None):
        self.llm = GeminiClient(model_name=model_name)

    def determine_style_dna(self, script_text: str, custom_genre: str = "") -> Dict[str, str]:
        """
        Анализирует сценарий и формирует ЕДИНЫЙ визуальный стиль (Style DNA),
        чтобы все кадры видеоряда сохраняли одинаковую цветовую палитру,
        освещение, фактуру камеры и эпоху.
        """
        q = f"""Проанализируй данный сценарий документального ролика и сформируй ЕДИНЫЙ ВИЗУАЛЬНЫЙ СТИЛЬ (Style Bible) для всех кадров видеоряда.
Все кадры должны выглядеть так, будто сняты одним оператором в единой цветовой гамме и стилистике.
КОНТЕКСТ: {custom_genre or "Документальный реализм, true crime, атмосфера эпохи"}

ТЕКСТ СЦЕНАРИЯ (фрагмент):
{script_text[:1800]}

Верни ответ СТРОГО в формате JSON без кавычек и markdown:
{{
  "style_title": "Краткое название единого стиля",
  "color_palette": "Цветовая гамма (палитра)",
  "lighting": "Характер освещения",
  "camera_look": "Тип камеры и оптики (пленка, зерно, резкость)",
  "era_and_mood": "Эпоха, окружение и атмосфера",
  "unified_suffix": "Единый суффикс для каждого промпта на русском (композиция, свет, гамма, формат 16:9)"
}}
"""
        import json
        try:
            res = self.llm.generate(q, temperature=0.3).strip('`* ')
            if res.startswith("json"):
                res = res[4:].strip()
            data = json.loads(res)
            return data
        except Exception as e:
            print(f"[PromptGenerator] Style DNA fallback: {e}")
            return {
                "style_title": "Кинематографичный документальный реализм",
                "color_palette": "Приглушенная естественная палитра, холодные тени, глубокий контраст",
                "lighting": "Драматичный естественный свет, мягкие глубокие тени",
                "camera_look": "35мм пленочная фотография, легкое зерно, глубина резкости",
                "era_and_mood": "Аутентичная атмосфера эпохи",
                "unified_suffix": "35мм пленка, кинематографичный кадр, драматичное освещение, реализм, формат 16:9, 4K"
            }

    def generate_prompts(
        self,
        script_text: str,
        style: str = "Кинематографичный реализм (35мм пленка, глубокие тени, 4K, формат 16:9)",
        interval_seconds: int = 30,
        only_images: bool = True,
        style_dna: Optional[Dict[str, str]] = None,
        custom_instructions: str = "",
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> str:
        """
        Генерирует полную режиссерскую раскадровку.
        При interval_seconds=30 нарезает весь сценарий строго на 30-секундные отрезки
        и создает ТОЛЬКО изображения (ФОТО 16:9) в едином визуальном стиле (Style DNA).
        """
        # Если Style DNA не передан, определяем его автоматически
        if not style_dna:
            if progress_callback:
                progress_callback(5, "Анализ сценария и определение единого визуального стиля (Style DNA)...")
            style_dna = self.determine_style_dna(script_text)

        style_title = style_dna.get("style_title", style)
        color_palette = style_dna.get("color_palette", "")
        lighting = style_dna.get("lighting", "")
        camera_look = style_dna.get("camera_look", "")
        era_and_mood = style_dna.get("era_and_mood", "")
        unified_suffix = style_dna.get("unified_suffix", "формат 16:9, 4K")

        slices = split_into_time_slices(script_text, interval_seconds=interval_seconds)
        total_slices = len(slices)

        if total_slices == 0:
            return "Сценарий пуст."

        # Пакетная генерация (по 10-12 кадров)
        batch_size = 12
        num_batches = math.ceil(total_slices / batch_size)
        all_results = []

        header_intro = (
            f"# РЕЖИССЕРСКАЯ РАСКАДРОВКА ВИДЕОМАТЕРИАЛОВ\n\n"
            f"Каждый кадр покрывает строго **{interval_seconds} секунд** речи диктора.\n"
            f"Всего планов: **{total_slices}** • Формат: **16:9 (Только ФОТО)**.\n\n"
            f"### 🎨 ЕДИНЫЙ ВИЗУАЛЬНЫЙ СТИЛЬ РОЛИКА (STYLE BIBLE):\n"
            f"* **Концепция:** {style_title}\n"
            f"* **Цветовая палитра:** {color_palette}\n"
            f"* **Освещение:** {lighting}\n"
            f"* **Камера и оптика:** {camera_look}\n"
            f"* **Эпоха и атмосфера:** {era_and_mood}\n"
            f"* **Единый стилистический якорь:** `{unified_suffix}`\n\n"
            f"---\n\n"
        )

        for b_idx in range(num_batches):
            b_start = b_idx * batch_size
            b_end = min(b_start + batch_size, total_slices)
            batch_slices = slices[b_start:b_end]

            if progress_callback:
                pct = 10 + int((b_idx / num_batches) * 80)
                progress_callback(pct, f"Генерация промптов в едином стиле: кадры {b_start+1}–{b_end} из {total_slices}...")

            slices_desc = []
            for s in batch_slices:
                slices_desc.append(
                    f"### Кадр {s['index']} ({s['timecode']})\n"
                    f"Речь диктора: \"{s['text']}\""
                )
            slices_block = "\n\n".join(slices_desc)

            batch_prompt = f"""
Ты создаешь промпты ТОЛЬКО ДЛЯ СТАТИЧЕСКИХ ИЗОБРАЖЕНИЙ (ФОТО 16:9) для следующих {len(batch_slices)} кадров сценария.
Шаг: СТРОГО каждые {interval_seconds} секунд.

КАТЕГОРИЧЕСКИ ВАЖНО: СОБЛЮДАТЬ ЕДИНЫЙ ВИЗУАЛЬНЫЙ СТИЛЬ ДЛЯ ВСЕХ КАДРОВ:
- Название стиля: {style_title}
- Палитра цветов: {color_palette}
- Характер света: {lighting}
- Оптика и текстура: {camera_look}
- Эпоха и атмосфера: {era_and_mood}
- Единый стилистический суффикс (добавляй в конец КАЖДОГО промпта): {unified_suffix}

КАТЕГОРИЧЕСКИЕ ТРЕБОВАНИЯ:
1. ТОЛЬКО ФОТО (ИЗОБРАЖЕНИЯ 16:9)! Запрещено писать про видео, анимацию или движение камеры.
2. Сохраняй нумерацию и точные таймкоды для каждого кадра без изменений!
3. Каждый промпт должен выглядеть частью одного и того же фильма, снятого на одну камеру.
4. Промпт пиши на выразительном русском языке.

СПИСОК КАДРОВ ДЛЯ ОБРАБОТКИ:
{slices_block}

ФОРМАТ ВЫВОДА ДЛЯ КАЖДОГО КАДРА (СТРОГО):
### Кадр [Номер]: [Краткое название] ([Точный таймкод])
* **Куда ставить в ролике:** [Краткая цитата речи диктора на эти 30 сек]
* **Тип материала:** 📸 ФОТО (16:9)
* **Промпт для генерации:**
> [Высокохудожественный промпт на русском языке, описывающий конкретную визуальную сцену под эту реплику, в единой цветовой гамме и освещении, завершающийся суффиксом: {unified_suffix}]
"""
            res_part = self.llm.generate(
                prompt=batch_prompt,
                system_prompt=SYSTEM_PROMPT_GENERATOR_PROMPT,
                temperature=0.75
            )
            all_results.append(res_part.strip())

        # Генерируем 2 варианта кликабельной обложки YouTube в том же едином стиле
        if progress_callback:
            progress_callback(93, "Генерация кликабельных обложек в едином стиле...")

        thumb_prompt = f"""
Создай 2 варианта высококликабельной обложки (Thumbnail 16:9, CTR 15%+) для YouTube по данному сценарию.
ЕДИНЫЙ СТИЛЬ: {style_title} ({color_palette})
ТЕКСТ СЦЕНАРИЯ (фрагмент):
{script_text[:1200]}

ФОРМАТ:
### ОБЛОЖКА YOUTUBE (THUMBNAIL 16:9)
#### Вариант 1: [Название концепции]
* **Главный объект:** [Что в центре]
* **Эмоция / Интрига:** [Что привлекает взгляд]
* **Промпт для генерации:**
> [Промпт на русском языке, 16:9, в стилистике {style_title}, яркий акцентный свет, 8K]

#### Вариант 2: [Название концепции]
* **Главный объект:** [Что в центре]
* **Эмоция / Интрига:** [Что привлекает взгляд]
* **Промпт для генерации:**
> [Промпт на русском языке, 16:9, в стилистике {style_title}, яркий акцентный свет, 8K]
"""
        try:
            thumb_res = self.llm.generate(
                prompt=thumb_prompt,
                system_prompt=SYSTEM_PROMPT_GENERATOR_PROMPT,
                temperature=0.85
            )
        except Exception:
            thumb_res = ""

        full_md = header_intro + "\n\n".join(all_results)
        if thumb_res:
            full_md += "\n\n---\n\n" + thumb_res.strip()

        if progress_callback:
            progress_callback(100, f"Готово! Сформировано {total_slices} кадров по {interval_seconds} сек в едином стиле.")

        return full_md

    def generate_single_prompt(self, scene_title: str, current_prompt: str, style: str = "") -> str:
        """Создает альтернативный промпт для конкретного кадра/сцены."""
        prompt = f"""
Создай альтернативный, свежий и выразительный промпт для генерации статического кадра (ФОТО 16:9) для сцены:
НАЗВАНИЕ КАДРА: {scene_title}
ТЕКУЩИЙ ПРОМПТ (для контекста): {current_prompt}
СТИЛЬ: {style or "Кинематографичный реализм 16:9, 4K"}

Требования:
- Напиши только сам текст промпта на русском языке (без вводных слов, префиксов и кавычек).
- Укажи детали композиции, ракурс, свет, атмосферу, 35мм пленку и формат 16:9.
- Только статическое фото, без видео и движения камеры!
"""
        return self.llm.generate(prompt=prompt, system_prompt=SYSTEM_PROMPT_GENERATOR_PROMPT, temperature=0.85).strip(' "`\'')
