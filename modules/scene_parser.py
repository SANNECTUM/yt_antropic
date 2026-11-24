"""
scene_parser.py
Нарезает сценарий на сцены (SceneBlock) с таймингами и поисковыми запросами.
Результат сохраняется как scenes.json в папке проекта.
"""
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional


WORDS_PER_MINUTE = 135  # средний темп диктора (слов в минуту)


def _strip_md(text: str) -> str:
    """Убирает markdown-разметку из строки."""
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'^\s*[-*>]\s*', '', text, flags=re.MULTILINE)
    return text.strip()


def _estimate_duration(text: str) -> float:
    """Оценивает длительность озвучки по числу слов (в секундах)."""
    words = len(text.split())
    return max(3.0, (words / WORDS_PER_MINUTE) * 60.0)


def _build_search_query(title: str, scene_text: str, topic: str = "") -> str:
    """
    Формирует короткий английский поисковый запрос для подбора кадра.
    Берёт первые значимые слова из заголовка и первые ключевые слова из текста сцены.
    """
    ru_stops = {
        'и', 'в', 'на', 'с', 'по', 'для', 'то', 'это', 'но', 'как',
        'что', 'он', 'она', 'они', 'мы', 'вы', 'я', 'его', 'её', 'их',
        'был', 'была', 'были', 'есть', 'нет', 'уже', 'ещё', 'еще',
        'все', 'всё', 'так', 'же', 'при', 'из', 'до', 'а', 'к', 'о'
    }
    words = [w for w in re.sub(r'[^\w\s]', ' ', title + ' ' + scene_text[:120]).split()
             if w.lower() not in ru_stops and len(w) > 2][:8]
    q = ' '.join(words[:5])
    return q.strip() or topic or "documentary cinematic"


SD_STYLE_PRESETS = {
    "🕵️ True Crime (Криминальная хроника)": {
        "suffix": "cinematic documentary still, true crime investigation atmosphere, moody dramatic shadows, cold muted color grading, 35mm film grain, 8k resolution, sharp focus",
        "negative": "ugly, deformed, cartoon, anime, 3d render, illustration, painting, bad anatomy, text, watermark, blurry, oversaturated, smiling"
    },
    "🎬 Кинодокументалистика": {
        "suffix": "wide angle cinematic still, high-end documentary film footage, natural dramatic lighting, photorealistic, depth of field, sharp details, 8k resolution",
        "negative": "plastic look, CGI, 3d render, cartoon, anime, low quality, distorted, extra limbs, watermark, text"
    },
    "📸 Реалистичное фото": {
        "suffix": "candid raw photo, investigative journalism, authentic real life setting, high resolution, sharp focus, natural overcast light, Sony A7R IV photography",
        "negative": "fake, airbrushed, porcelain skin, 3d render, cartoon, drawing, text, logo, blurry"
    },
    "⏳ Архив 90-х / 2000-х": {
        "suffix": "early 2000s archival documentary photograph, authentic historical scene, nostalgic analog film aesthetic, slightly desaturated, detailed, photorealistic 8k",
        "negative": "modern, futuristic, neon, hyper digital, cartoon, drawing, distorted, blurry, watermark"
    },
    "🌃 Триллер / Нуар": {
        "suffix": "film noir aesthetic, high contrast chiaroscuro lighting, dark silhouettes, deep moody shadows, cinematic mystery atmosphere, photorealistic 8k",
        "negative": "bright, colorful, cheerful, cartoon, anime, lowres, text, watermark"
    }
}
DEFAULT_STYLE_NAME = "🕵️ True Crime (Криминальная хроника)"


def craft_smart_ai_prompt(scene: "SceneBlock", style_name: str = DEFAULT_STYLE_NAME, use_gemini: bool = False) -> tuple[str, str]:
    """
    Создает профессиональный кинематографичный промпт (на английском)
    и негативный промпт по стандартам Stable Diffusion / Midjourney.
    По умолчанию (use_gemini=False) выполняется мгновенно без блокирующих сетевых запросов.
    """
    preset = SD_STYLE_PRESETS.get(style_name, SD_STYLE_PRESETS[DEFAULT_STYLE_NAME])
    suffix = preset["suffix"]
    negative = preset["negative"]

    # 1. Попытка через GeminiClient создать контекстный визуальный промпт ТОЛЬКО если запрошено явно
    if use_gemini:
        try:
            from modules.llm_client import GeminiClient
            client = GeminiClient()
            q = (
                f"You are a prompt engineer for Stable Diffusion and cinematic films.\n"
                f"Create a concise one-sentence visual description in English for this scene from a documentary video:\n"
                f"Scene text: \"{scene.text[:300]}\"\n"
                f"Context title: \"{scene.title}\"\n\n"
                f"Requirements:\n"
                f"- Describe the visual setting, lighting, and mood (no text, no talking heads).\n"
                f"- Add this style suffix at the end: {suffix}\n"
                f"- Return ONLY the final prompt text, no quotes, no markdown."
            )
            res = client.generate(q, temperature=0.4).strip().strip('"`\'')
            if res and len(res) > 20:
                return res, negative
        except Exception as e:
            print(f"[SceneParser] Gemini prompt craft failed: {e}")

    # 2. Быстрый мгновенный fallback: очистка текста + суффикс
    sentences = re.split(r'(?<=[.!?])\s+', scene.text.strip())
    core = ' '.join(sentences[:2]).strip()[:180]
    core = re.sub(r'\b(диктор|закадровый голос|закадр\w*|монтаж\w*|поставить|вставить|кадр\w*)\b', '', core, flags=re.IGNORECASE)
    core = re.sub(r'\s{2,}', ' ', core).strip(' ,.')
    if not core or len(core) < 10:
        core = scene.title

    prompt = f"{core}, {suffix}"
    return prompt, negative


def build_ai_image_prompt(scene: "SceneBlock", style_name: str = DEFAULT_STYLE_NAME) -> str:
    """
    Для обратной совместимости: возвращает готовый позитивный промпт.
    """
    pos, _ = craft_smart_ai_prompt(scene, style_name=style_name)
    return pos



def resolve_visual_path(path_str: Optional[str], project_dir: Path) -> Optional[Path]:
    """
    Универсально находит файл кадра (видео/фото) на любой ОС (Windows / Linux),
    даже если в JSON сохранён абсолютный путь Windows (C:\\Users\\...) или пути с обратными слэшами.
    """
    if not path_str:
        return None

    norm_str = str(path_str).replace("\\", "/").strip()
    if not norm_str:
        return None

    # 1. Прямой путь
    try:
        p = Path(norm_str)
        if p.exists() and p.is_file():
            return p
    except Exception:
        pass

    # 2. Относительно корня проекта
    try:
        p_proj = project_dir / norm_str
        if p_proj.exists() and p_proj.is_file():
            return p_proj
    except Exception:
        pass

    # 3. В папке visuals/ текущего проекта по имени файла
    try:
        fname = Path(norm_str).name
        if fname:
            p_vis = project_dir / "visuals" / fname
            if p_vis.exists() and p_vis.is_file():
                return p_vis
    except Exception:
        pass

    # 4. Если путь содержит 'projects/<slug>/...'
    try:
        parts = Path(norm_str).parts
        if "projects" in parts:
            idx = parts.index("projects")
            rel_sub = Path(*parts[idx:])
            if rel_sub.exists() and rel_sub.is_file():
                return rel_sub
            if project_dir.parent and project_dir.parent.parent:
                parent_base = project_dir.parent.parent / rel_sub
                if parent_base.exists() and parent_base.is_file():
                    return parent_base
    except Exception:
        pass

    return None


class SceneBlock:
    """Одна сцена сценария."""

    def __init__(
        self,
        index: int,
        title: str,
        text: str,
        duration: float,
        search_query: str = "",
        visual_path: Optional[str] = None,
        effect: str = "ken_burns_in",
        custom_duration: Optional[float] = None,
        prompt: Optional[str] = None,
        **kwargs,
    ):
        self.index = index
        self.title = title
        self.text = text                      # чистый текст реплики диктора
        self.duration = duration              # расчётная длительность (сек)
        self.search_query = search_query      # запрос для поиска кадра
        self.visual_path = visual_path        # путь к выбранному файлу (jpg/mp4)
        self.effect = effect                  # ken_burns_in | ken_burns_out | fade | slide_left | slide_right | none
        self.custom_duration = custom_duration  # переопределённый тайминг пользователем
        self.prompt = prompt or kwargs.get("visual_prompt", "")            # художественное описание / промпт для B-Roll

    def get_resolved_visual_path(self, project_dir: Path) -> Optional[Path]:
        return resolve_visual_path(self.visual_path, project_dir)

    @property
    def effective_duration(self) -> float:
        return self.custom_duration if self.custom_duration else self.duration

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "title": self.title,
            "text": self.text,
            "duration": self.duration,
            "search_query": self.search_query,
            "visual_path": self.visual_path,
            "effect": self.effect,
            "custom_duration": self.custom_duration,
            "prompt": self.prompt,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SceneBlock":
        return cls(
            index=d["index"],
            title=d["title"],
            text=d["text"],
            duration=d["duration"],
            search_query=d.get("search_query", ""),
            visual_path=d.get("visual_path"),
            effect=d.get("effect", "ken_burns_in"),
            custom_duration=d.get("custom_duration"),
            prompt=d.get("prompt", ""),
        )


class SceneParser:
    """
    Нарезает готовый сценарий на сцены нескольких стратегиями:
    1. По явным заголовкам (## / ### ЧАСТЬ / СЦЕНА / ACT / глава)
    2. По подзаголовкам второго уровня (## любой текст)
    3. По пустым строкам — абзацное деление (для коротких сценариев)
    """

    def __init__(self, topic: str = ""):
        self.topic = topic

    def parse(self, script_text: str, words_per_scene: int = 200, strategy: str = "auto", interval_seconds: int = 30) -> List[SceneBlock]:
        """Главный метод: возвращает список SceneBlock."""
        if not script_text.strip():
            return []

        if strategy == "time_slices":
            return self.parse_by_time_slices(script_text, interval_seconds=interval_seconds)

        if strategy == "paragraphs":
            return self._parse_by_paragraphs(script_text, words_per_scene=words_per_scene)

        scenes = self._parse_by_headers(script_text)
        if len(scenes) >= 2:
            return scenes

        scenes = self._parse_by_h2(script_text)
        if len(scenes) >= 2:
            return scenes

        # Fallback: делим на абзацы и группируем по ~words_per_scene слов
        return self._parse_by_paragraphs(script_text, words_per_scene=words_per_scene)

    def parse_by_time_slices(self, text: str, interval_seconds: int = 30) -> List[SceneBlock]:
        """Нарезка строго по временным отрезкам (например, каждые 30 секунд речи)."""
        from modules.prompt_generator import split_into_time_slices
        slices = split_into_time_slices(text, interval_seconds=interval_seconds)
        scenes: List[SceneBlock] = []
        for item in slices:
            idx = item["index"]
            clean_text = _strip_md(item["text"])
            dur = float(item.get("duration", interval_seconds))
            tc = item.get("timecode", f"Сцена {idx}")
            q = _build_search_query(f"Сцена {idx}", clean_text, self.topic)
            scenes.append(SceneBlock(
                index=idx,
                title=f"Кадр {idx} ({tc})",
                text=clean_text,
                duration=dur,
                search_query=q,
            ))
        return scenes

    # ------------------------------------------------------------------ #
    # Стратегия 1: Явные сцены / части / акты
    # ------------------------------------------------------------------ #
    def _parse_by_headers(self, text: str) -> List[SceneBlock]:
        pattern = re.compile(
            r'(?m)^#{1,4}\s*(?:СЦЕНА|ЧАСТЬ|АКТ|ГЛАВА|SCENE|ACT|PART|CHAPTER|Сцена|Часть|Акт|Глава)\s*[\d:.)]*\s*[:\-—]?\s*([^\n]*)',
            re.IGNORECASE
        )
        return self._split_by_pattern(text, pattern)

    # ------------------------------------------------------------------ #
    # Стратегия 2: Любые заголовки ##
    # ------------------------------------------------------------------ #
    def _parse_by_h2(self, text: str) -> List[SceneBlock]:
        pattern = re.compile(r'(?m)^#{2,3}\s+([^\n]+)')
        return self._split_by_pattern(text, pattern)

    # ------------------------------------------------------------------ #
    # Стратегия 3: Абзацное деление (~200 слов на сцену)
    # ------------------------------------------------------------------ #
    def _parse_by_paragraphs(self, text: str, words_per_scene: int = 200) -> List[SceneBlock]:
        # Разбиваем на абзацы (2+ пустых строки)
        paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
        scenes: List[SceneBlock] = []
        buf_title = ""
        buf_words: List[str] = []
        scene_idx = 1

        def flush():
            nonlocal scene_idx, buf_title, buf_words
            if not buf_words:
                return
            body = ' '.join(buf_words)
            clean = _strip_md(body)
            dur = _estimate_duration(clean)
            q = _build_search_query(buf_title or f"Сцена {scene_idx}", clean, self.topic)
            scenes.append(SceneBlock(
                index=scene_idx,
                title=buf_title or f"Сцена {scene_idx}",
                text=clean,
                duration=dur,
                search_query=q,
            ))
            scene_idx += 1
            buf_title = ""
            buf_words = []

        for para in paragraphs:
            # Если абзац — заголовок, создаём новую сцену
            if re.match(r'^#{1,4}\s', para):
                flush()
                buf_title = _strip_md(para)
                continue
            new_words = para.split()
            buf_words.extend(new_words)
            if len(buf_words) >= words_per_scene:
                flush()

        flush()
        return scenes

    # ------------------------------------------------------------------ #
    # Вспомогательный: разбивка по найденным заголовкам
    # ------------------------------------------------------------------ #
    def _split_by_pattern(self, text: str, pattern: re.Pattern) -> List[SceneBlock]:
        matches = list(pattern.finditer(text))
        if not matches:
            return []

        scenes: List[SceneBlock] = []
        for i, m in enumerate(matches):
            title = _strip_md(m.group(1) if m.lastindex else "")
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            clean = _strip_md(body)
            if not clean:
                continue
            dur = _estimate_duration(clean)
            q = _build_search_query(title, clean, self.topic)
            scenes.append(SceneBlock(
                index=i + 1,
                title=title or f"Сцена {i + 1}",
                text=clean,
                duration=dur,
                search_query=q,
            ))
        return scenes


# ------------------------------------------------------------------ #
# Утилиты сохранения / загрузки
# ------------------------------------------------------------------ #

def save_scenes(scenes: List[SceneBlock], project_dir: Path) -> Path:
    path = project_dir / "scenes.json"
    path.write_text(
        json.dumps([s.to_dict() for s in scenes], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return path


def load_scenes(project_dir: Path) -> List[SceneBlock]:
    path = project_dir / "scenes.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [SceneBlock.from_dict(d) for d in data]
