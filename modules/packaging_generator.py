import re
from typing import Optional, Dict, Any, List
from modules.llm_client import GeminiClient
from modules.script_generator import sanitize_for_gemini

SYSTEM_PACKAGING_PROMPT = """
Ты — топ-продюсер YouTube с миллиардными охватами, специализирующийся на упаковке видео (Packaging): кликабельные заголовки (CTR), концепты обложек (Thumbnails) и алгоритмические описания (SEO Description) в стиле лучших каналов мира (MrBeast, Magnates Media, Lemmino, JCS).

ТВОЯ СУПЕРСИЛА:
Превращать глубокий сценарий в максимальный CTR без дешевого скама, используя законы психологии внимания зрителя: когнитивный диссонанс, незакрытый гештальт, моральный парадокс, шокирующие детали и эмоциональный триггер.
"""

class PackagingGenerator:
    def __init__(self, model_name: Optional[str] = None):
        self.llm = GeminiClient(model_name=model_name)

    def generate_titles(self, script_text: str, custom_notes: str = "") -> str:
        """
        Генерирует 10 взрывных вариантов заголовков по строгим правилам:
        - Высокий CTR
        - Постыдные факты / провокационные тезисы / жестокие ухищрения
        - Каждое Слово С Большой Буквы
        - Фальшивая цитата героя
        - Строго до 100 символов
        """
        clean_text = sanitize_for_gemini(script_text)
        prompt = f"""
Теперь у нас есть готовый текст, который будет озвучен для видеоролика на ютуб канале.
Твоя задача сейчас предложить 10 вариантов того, каким мы можем сделать заголовок к этому видео.
Он должен быть ярким, запоминающимся, цепляющим внимание зрителя.
Тебе нужно сосредоточиться на достижении высокого CTR.
В заголовке можешь использовать постыдные факты о главном герое выпуска, провокационные тезисы и жестокие ухищрения.
Каждое слово должно быть с большой буквы.
Добавь в название фальшивую цитату героя для привлечения внимания.
Длина заголовка: строго ДО 100 СИМВОЛОВ.

ДОПОЛНИТЕЛЬНЫЕ ПОЖЕЛАНИЯ АВТОРА:
{custom_notes if custom_notes else "Максимальный виральный потенциал и шокирующая интрига."}

СЦЕНАРИЙ / ТЕКСТ ВИДЕО (ИСХОДНИК):
{clean_text[:3500]}

ТРЕБОВАНИЯ К ФОРМАТУ ВЫВОДА:
Выведи ровно 10 пронумерованных вариантов.
Для каждого варианта:
1. Заголовок (Каждое Слово С Большой Буквы, с фальшивой цитатой, до 100 символов).
2. Под ним укажи точное количество символов: `[Символов: XX/100]`.
3. Краткое пояснение триггера (почему зритель нажмет на это видео).
"""
        return self.llm.generate(prompt=prompt, system_prompt=SYSTEM_PACKAGING_PROMPT, temperature=0.85)

    def generate_thumbnails(self, script_text: str, selected_title: str = "", custom_notes: str = "") -> str:
        """
        Генерирует концепты обложек на основе сценария и выбранного названия:
        - Стиль желтой прессы / таблоидная интрига
        - Максимальная интрига, без прямых спойлеров
        - Фальшивая цитата героя + жестокий комментарий
        - Текст дополняет название, но не дублирует
        - Промпт для генерации арт-обложки (Midjourney / FLUX)
        """
        clean_text = sanitize_for_gemini(script_text)
        prompt = f"""
Исходя из названия для видео и его сценария, придумай текст и визуальные концепты, которые мы напишем и изобразим на обложке к этому видеоролику.

ВЫБРАННОЕ НАЗВАНИЕ ВИДЕО:
{selected_title if selected_title else "Опирайся на события и главных героев сценария"}

СЦЕНАРИЙ ВИДЕО:
{clean_text[:3500]}

ДОПОЛНИТЕЛЬНЫЕ ПОЖЕЛАНИЯ:
{custom_notes if custom_notes else "Стиль таблоидов, высочайшая эмоциональная напряженность."}

ПРАВИЛА И СТАНДАРТЫ ДЛЯ ОБЛОЖКИ:
1. Стиль желтой прессы и жесткого таблоида.
2. Используй максимальную интригу, но НЕ раскрывай конкретную информацию и не спойлери развязку.
3. Используй провокационные, триггерные слова.
4. Отличный ход: написать, что мог бы сказать главный герой (фальшивая цитата героя) и жестоко прокомментировать её!
5. Обложка должна перекликаться с названием видео, но НЕ копировать его, а дополнять.
6. Текст на обложке должен вызывать бурные эмоции и непреодолимое желание открыть ролик. Текст должен быть коротким (2-5 слов), чтобы читаться даже с экрана телефона.

СФОРМИРУЙ 5 РАЗНЫХ КОНЦЕПТОВ ОБЛОЖЕК:
Для каждого концепта распиши:
### Концепт [Номер]: [Название идеи]
- **Главный текст на обложке** (крупные жирные слова, 2-4 слова, легко читаемые на мобильном)
- **Фальшивая цитата героя + Жестокий комментарий** (например: «Я Не Хотел!» — Слишком Поздно.)
- **Визуальная композиция**: Кто в кадре, какое выражение лица/глаз (шок, страх, холодная улыбка, слезы), освещение, что на заднем плане.
- **Интригующая улика / Кликбейтный элемент**: секретный документ, красная стрелка, заблюренный объект, дата на мониторе и т.д.
- **Английский промпт для нейросетей (FLUX / Midjourney / DALL-E)**: подробный готовый промпт в формате 16:9 YouTube thumbnail с драматичным светом и максимальной кинематографичностью.
"""
        return self.llm.generate(prompt=prompt, system_prompt=SYSTEM_PACKAGING_PROMPT, temperature=0.85)

    def generate_description(self, script_text: str, selected_title: str = "", topic: str = "") -> str:
        """
        Генерирует оптимизированное описание для YouTube:
        - Первые 2 интригующие строки (Хук над катом)
        - Краткий синопсис без спойлеров
        - Автоматические таймкоды глав (из сценария)
        - SEO-хэштеги и поисковые теги
        """
        clean_text = sanitize_for_gemini(script_text)
        prompt = f"""
Создай профессиональное, оптимизированное для алгоритмов YouTube описание к видео.

НАЗВАНИЕ РОЛИКА: {selected_title if selected_title else topic}
ТЕМА: {topic}

СЦЕНАРИЙ ВИДЕО:
{clean_text[:5000]}

СТРУКТУРА ОПИСАНИЯ:
1. **Хук (Первые 2-3 строки)**:
   Самый важный текст — именно его зрители видят в поиске и до нажатия кнопки «Ещё». Он должен содержать главный конфликт, парадокс и заставлять досмотреть видео.
2. **Краткий синопсис видео (2 абзаца)**:
   Интригующее описание сюжета без спойлеров финала.
3. **Таймкоды (Главы видео)**:
   Сформируй список глав с таймингами (начни обязательно с `00:00`), извлекая сцены и ключевые моменты из сценария.
4. **Хэштеги и ключевые слова (SEO)**:
   - 3-5 кликабельных хэштегов (#...)
   - Список релевантных поисковых тегов для алгоритмов YouTube через запятую.
5. **Дисклеймер и призыв подписаться**:
   Лаконичный дисклеймер и призыв оставить свое мнение в комментариях.
"""
        return self.llm.generate(prompt=prompt, system_prompt=SYSTEM_PACKAGING_PROMPT, temperature=0.7)

    def generate_complete_packaging(self, script_text: str, selected_title: str = "", topic: str = "") -> Dict[str, str]:
        """Генерирует полный комплекс упаковки: заголовки, обложки и описание."""
        titles = self.generate_titles(script_text)
        
        # Если название не выбрано, попробуем взять первый сгенерированный заголовок
        effective_title = selected_title
        if not effective_title:
            title_lines = [l.strip() for l in titles.splitlines() if re.match(r'^\d+[\.\)]\s*', l.strip())]
            if title_lines:
                effective_title = re.sub(r'^\d+[\.\)]\s*', '', title_lines[0]).split('[')[0].strip(' *"`')
        
        thumbnails = self.generate_thumbnails(script_text, selected_title=effective_title)
        description = self.generate_description(script_text, selected_title=effective_title, topic=topic)
        
        return {
            "titles": titles,
            "thumbnails": thumbnails,
            "description": description,
            "selected_title": effective_title
        }

    @staticmethod
    def parse_titles(titles_text: str) -> List[Dict[str, Any]]:
        """Извлекает структурированный список заголовков из markdown-ответа модели."""
        results = []
        lines = titles_text.splitlines()
        current_item = None

        for line in lines:
            line_str = line.strip()
            # Поиск строки номера заголовка (например "1. «Я Не Хотел Этого»...")
            m = re.match(r'^(?:###\s*)?(\d+)[\.\)]\s*(.+)', line_str)
            if m:
                if current_item:
                    results.append(current_item)
                num = int(m.group(1))
                raw_title = m.group(2).strip(' *`"')
                # Убираем счетчик символов если модель прикрепила его в той же строке
                clean_title = re.sub(r'\[(?:Символов|Длина|Симв)[^\]]*\]', '', raw_title, flags=re.IGNORECASE).strip(' *`"')
                current_item = {
                    "number": num,
                    "title": clean_title,
                    "length": len(clean_title),
                    "details": ""
                }
            elif current_item:
                if line_str:
                    current_item["details"] += (" " + line_str if current_item["details"] else line_str)

        if current_item:
            results.append(current_item)

        return results

    @staticmethod
    def parse_packaging_sections(full_md: str) -> Dict[str, str]:
        """Парсит packaging.md на 3 независимых блока: titles, thumbnails, description."""
        sections = {"titles": "", "thumbnails": "", "description": ""}
        if not full_md:
            return sections

        t_match = re.search(r'# 🎯 Варианты названий.*?(?=(?:# 🖼️|# 📝|\Z))', full_md, re.DOTALL)
        if t_match:
            sec_t = re.sub(r'^# 🎯 Варианты названий[^\n]*\n+', '', t_match.group(0)).strip()
            sections["titles"] = re.sub(r'---\s*$', '', sec_t).strip()

        th_match = re.search(r'# 🖼️ Концепты обложек.*?(?=(?:# 🎯|# 📝|\Z))', full_md, re.DOTALL)
        if th_match:
            sec_th = re.sub(r'^# 🖼️ Концепты обложек[^\n]*\n+', '', th_match.group(0)).strip()
            sections["thumbnails"] = re.sub(r'---\s*$', '', sec_th).strip()

        d_match = re.search(r'# 📝 Описание для YouTube.*?(?=(?:# 🎯|# 🖼️|\Z))', full_md, re.DOTALL)
        if d_match:
            sec_d = re.sub(r'^# 📝 Описание для YouTube[^\n]*\n+', '', d_match.group(0)).strip()
            sections["description"] = re.sub(r'---\s*$', '', sec_d).strip()

        return sections

    @classmethod
    def update_section(cls, full_md: str, section_type: str, new_content: str) -> str:
        """Безопасно заменяет указанную секцию (titles, thumbnails, description) без дублирования."""
        sections = cls.parse_packaging_sections(full_md)
        sections[section_type] = new_content.strip()

        blocks = []
        if sections.get("titles"):
            blocks.append(f"# 🎯 Варианты названий видео (CTR)\n\n{sections['titles']}")
        if sections.get("thumbnails"):
            blocks.append(f"# 🖼️ Концепты обложек (Thumbnails)\n\n{sections['thumbnails']}")
        if sections.get("description"):
            blocks.append(f"# 📝 Описание для YouTube (SEO)\n\n{sections['description']}")

        return "\n\n---\n\n".join(blocks)

    def generate_3_styles_package(self, text_or_topic: str) -> str:
        """
        Генерирует названия для видео и тексты для 3-х утвержденных стилей обложек:
        - Стиль 1 (Красный неон: тайна семьи / скрытый монстр)
        - Стиль 2 (Сплит-скрин: конфликт / разоблачение)
        - Стиль 3 (Герой + Улики: расследование / шокирующая деталь)
        """
        clean_text = sanitize_for_gemini(text_or_topic)
        prompt = f"""
У нас есть история для видеоролика (True Crime / Детектив / Расследование).
Мы запускаем эту историю сразу на 3 разных YouTube каналах с разными заголовками и 3 разными стилями обложек.

ТЕКСТ / ТЕМА ИСТОРИИ:
{clean_text[:4000]}

Твоя задача — предложить для каждого из 3-х каналов мощный пакет упаковки (Кликабельный заголовок видео + 2 строки короткого текста для обложки).

ФОРМАТ ВЫВОДА СТРОГО СЛЕДУЮЩИЙ:

### 🔴 КАНАЛ 1 (Стиль 1: Красный неон / Тайна семьи / Скрытый монстр)
- **Название видео (CTR, до 100 симв):** [Заголовок в Title Case с интригой]
- **Обложка Строка 1 (Красная):** [2-3 слова, ALL CAPS]
- **Обложка Строка 2 (Белая):** [2-4 слова, ALL CAPS]
- *Почему это сработает:* [Краткое пояснение триггера]

### 🟡 КАНАЛ 2 (Стиль 2: Сплит-скрин / Противостояние / Преступник vs Жертва)
- **Название видео (CTR, до 100 симв):** [Заголовок в Title Case с конфликтом]
- **Обложка Строка 1 (Желтая):** [2-3 слова, ALL CAPS]
- **Обложка Строка 2 (Желтая):** [2-4 слова, ALL CAPS]
- *Почему это сработает:* [Краткое пояснение триггера]

### ⬛ КАНАЛ 3 (Стиль 3: Улики / Разоблачение / Герой + 2 вещдока)
- **Название видео (CTR, до 100 симв):** [Заголовок в Title Case с фокусом на улика/ложь/суд]
- **Обложка Строка 1 (В плашке):** [2-3 слова, ALL CAPS]
- **Обложка Строка 2 (В плашке):** [2-4 слова, ALL CAPS]
- *Почему это сработает:* [Краткое пояснение триггера]
"""
        return self.llm.generate(prompt=prompt, system_prompt=SYSTEM_PACKAGING_PROMPT, temperature=0.85)
