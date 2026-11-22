"""
fooocus_client.py
Модуль интеграции с Fooocus (SDXL для фотореалистичных кадров на RTX 4060 Ti).
Поддерживает:
1. Автодетект запущенного Fooocus (http://127.0.0.1:7865/).
2. Прямую генерацию через Gradio API.
3. Мгновенный импорт последнего сгенерированного кадра из папки Fooocus/outputs.
"""

import os
import glob
import time
import shutil
import urllib.request
from pathlib import Path
from typing import Optional, List, Dict, Any


DEFAULT_FOOOCUS_URL = "http://127.0.0.1:7865/"

# Популярные пути установки Fooocus на Windows
SEARCH_PATHS = [
    Path("C:/Fooocus/Fooocus_win64_2-5-0"),
    Path("C:/Fooocus"),
    Path("C:/Users/berze/Fooocus"),
    Path("C:/Users/berze/Downloads/Fooocus"),
    Path("D:/Fooocus"),
    Path("E:/Fooocus"),
    Path("./Fooocus"),
]


class FooocusClient:
    def __init__(self, base_url: str = DEFAULT_FOOOCUS_URL, custom_dir: Optional[Path] = None):
        self.base_url = base_url.rstrip("/")
        self.custom_dir = Path(custom_dir) if custom_dir else None

    def is_running(self) -> bool:
        """Проверяет, запущен ли локальный сервер Fooocus (проверяет порты 7865, 7866, 7860)."""
        candidate_ports = [7865, 7866, 7860, 7861, 7867]
        for port in candidate_ports:
            url = f"http://127.0.0.1:{port}/"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        self.base_url = f"http://127.0.0.1:{port}"
                        return True
            except Exception:
                continue
        return False

    def find_outputs_dir(self) -> Optional[Path]:
        """Ищет папку outputs, куда Fooocus сохраняет готовые изображения."""
        candidates = []
        if self.custom_dir and self.custom_dir.exists():
            candidates.append(self.custom_dir / "outputs")
            candidates.append(self.custom_dir / "Fooocus" / "outputs")

        for p in SEARCH_PATHS:
            if p.exists():
                candidates.append(p / "outputs")
                candidates.append(p / "Fooocus" / "outputs")

        # Также проверим текущую папку и родительские
        candidates.append(Path.cwd() / "Fooocus" / "outputs")
        candidates.append(Path.cwd().parent / "Fooocus" / "outputs")

        for c in candidates:
            if c.exists() and c.is_dir():
                return c
        return None

    def get_latest_output_image(self) -> Optional[Path]:
        """
        Находит самый свежий сгенерированный кадр (PNG/JPG) в папке outputs Fooocus.
        """
        out_dir = self.find_outputs_dir()
        if not out_dir:
            return None

        # Ищем все изображения рекурсивно по дням (outputs/YYYY-MM-DD/*.png)
        patterns = [
            str(out_dir / "*" / "*.png"),
            str(out_dir / "*" / "*.jpg"),
            str(out_dir / "*.png"),
            str(out_dir / "*.jpg"),
        ]
        files = []
        for pat in patterns:
            files.extend(glob.glob(pat))

        if not files:
            return None

        # Сортируем по времени изменения (самый свежий первый)
        files.sort(key=os.path.getmtime, reverse=True)
        return Path(files[0])

    def generate_via_api(
        self,
        prompt: str,
        output_path: Path,
        negative_prompt: str = "",
        style_selections: Optional[List[str]] = None,
        aspect_ratio: str = "1152*896"
    ) -> Optional[Path]:
        """
        Генерирует изображение напрямую через Gradio API Fooocus на видеокарте RTX 4060 Ti.
        """
        if not self.is_running():
            return None

        try:
            from gradio_client import Client
            client = Client(self.base_url)

            # Пробуем вызвать API предсказания
            styles = style_selections or ["Fooocus V2", "Fooocus Photograph", "Fooocus Negative"]

            # Вызов очереди генерации
            job = client.submit(
                prompt,
                negative_prompt or "ugly, deformed, blurry, bad anatomy, cartoon, watermark, distorted",
                styles,
                "Speed",          # Performance
                aspect_ratio,     # 16:9
                1,                # Image number
                0,                # Random seed
                2.0,              # Sharpness
                7.0,              # Guidance Scale
                api_name="/generate"
            )
            result = job.result()
            if result:
                # result обычно путь к файлу или кортеж
                src_path = None
                if isinstance(result, (list, tuple)) and len(result) > 0:
                    src_path = Path(result[0])
                elif isinstance(result, str):
                    src_path = Path(result)

                if src_path and src_path.exists():
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_path, output_path)
                    return output_path
        except Exception as e:
            print(f"[FooocusClient] Gradio API error: {e}")

        # Резервный вариант: если генерация была нажата в UI, берем последний файл из outputs
        time.sleep(1.0)
        latest = self.get_latest_output_image()
        if latest and latest.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(latest, output_path)
            return output_path

        return None
