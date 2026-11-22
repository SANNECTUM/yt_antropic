"""
modules/pexels_downloader.py
Пакетный загрузчик стоковых Full HD (1080p) b-roll видео с Pexels.
Работает без официального API-ключа (на базе архитектуры omkarcloud/pexels-scraper),
используя клиентский веб-токен Pexels и curl_cffi с имитацией браузера.
Поддерживает прокси (SOCKS5/HTTP) и прямой доступ через VPN.
"""

import os
import re
import socket
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from curl_cffi import requests
try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger("pexels_downloader")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("[%(levelname)s] %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)

from modules.llm_client import GeminiClient


PEXELS_CLIENT_ID = "4faffa81915014bbd90c420f22898950"
PEXELS_SEARCH_URL = "https://www.pexels.com/en-us/api/v3/search/videos"


def detect_local_proxy() -> Optional[str]:
    """
    Автоматически ищет открытый локальный прокси (Xray/v2ray/Clash)
    или читает переменные окружения PEXELS_PROXY / HTTPS_PROXY.
    """
    env_proxy = os.getenv("PEXELS_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    if env_proxy:
        return env_proxy

    # Проверяем популярные локальные порты: 10808 (xray socks5), 10809 (http), 7890 (clash), 1080 (socks)
    test_ports = [
        ("socks5://127.0.0.1:10808", ("127.0.0.1", 10808)),
        ("http://127.0.0.1:10809", ("127.0.0.1", 10809)),
        ("http://127.0.0.1:7890", ("127.0.0.1", 7890)),
        ("socks5://127.0.0.1:1080", ("127.0.0.1", 1080)),
    ]
    for proxy_url, (host, port) in test_ports:
        try:
            s = socket.socket()
            s.settimeout(0.2)
            if s.connect_ex((host, port)) == 0:
                s.close()
                return proxy_url
            s.close()
        except Exception:
            pass
    return None


class PexelsDownloader:
    """
    Клиент для поиска и скачивания стоковых Full HD видео с Pexels.
    """

    def __init__(self, proxy: Optional[str] = None):
        self.proxy = proxy if proxy is not None else detect_local_proxy()
        self.client_id = PEXELS_CLIENT_ID

    def _get_session(self) -> requests.Session:
        sess = requests.Session(impersonate="chrome120")
        if self.proxy:
            sess.proxies = {"http": self.proxy, "https": self.proxy}
        sess.headers.update({
            "accept": "application/json, text/plain, */*",
            "pexels-client-id": self.client_id,
            "x-client-type": "react",
            "referer": "https://www.pexels.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        return sess

    def search_videos(
        self,
        query: str,
        limit: int = 10,
        orientation: str = "landscape"
    ) -> List[Dict[str, Any]]:
        """
        Ищет стоковые видео на Pexels по ключевым словам.
        Возвращает список видео с прямыми ссылками на MP4.
        """
        clean_q = query.strip()
        if not clean_q:
            return []

        params = {
            "query": clean_q,
            "page": 1,
            "per_page": min(limit * 2, 24),
            "orientation": orientation,
            "seo_tags": "true"
        }

        try:
            sess = self._get_session()
            resp = sess.get(PEXELS_SEARCH_URL, params=params, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"[PexelsDownloader] Статус {resp.status_code} для запроса '{clean_q}': {resp.text[:100]}")
                return []

            data = resp.json()
            raw_media = data.get("data", [])
            results = []

            for item in raw_media:
                attrs = item.get("attributes", {})
                video_files = attrs.get("video_files") or []
                if not video_files and "video" in attrs:
                    video_files = attrs["video"].get("video_files", [])

                if not video_files:
                    continue

                # Ищем лучшее 1080p (Full HD) или 720p качество
                best_link = None
                best_width = 0
                preview_thumb = ""
                
                # Извлечение ссылки на превью-обложку (Pexels может хранить её в image, video_pictures или video.thumbnail)
                if isinstance(attrs.get("image"), str) and attrs.get("image").startswith("http"):
                    preview_thumb = attrs.get("image")
                elif attrs.get("video_pictures") and isinstance(attrs["video_pictures"], list):
                    for vp in attrs["video_pictures"]:
                        if isinstance(vp, dict) and vp.get("picture"):
                            preview_thumb = vp["picture"]
                            break
                elif isinstance(attrs.get("video"), dict):
                    v_dict = attrs["video"]
                    if isinstance(v_dict.get("image"), str) and v_dict.get("image").startswith("http"):
                        preview_thumb = v_dict.get("image")
                    elif isinstance(v_dict.get("thumbnail"), dict):
                        t_dict = v_dict["thumbnail"]
                        preview_thumb = t_dict.get("medium") or t_dict.get("large") or t_dict.get("small") or ""
                    elif isinstance(v_dict.get("thumbnail"), str) and v_dict.get("thumbnail").startswith("http"):
                        preview_thumb = v_dict.get("thumbnail")
                    elif v_dict.get("video_pictures") and isinstance(v_dict["video_pictures"], list):
                        for vp in v_dict["video_pictures"]:
                            if isinstance(vp, dict) and vp.get("picture"):
                                preview_thumb = vp["picture"]
                                break

                # Сортируем файлы: предпочитаем 1920x1080, затем 1280x720, затем 4K
                for vf in video_files:
                    w = vf.get("width") or 0
                    h = vf.get("height") or 0
                    link = vf.get("link")
                    if not link:
                        continue

                    # Если горизонтальное видео
                    if w > h:
                        # 1080p - идеал
                        if w == 1920:
                            best_link = link
                            best_width = w
                            break
                        # если еще не нашли 1080p, берем 1280 или максимальное до 2560
                        elif w >= 1280 and best_width < 1920:
                            best_link = link
                            best_width = w
                        elif best_link is None:
                            best_link = link
                            best_width = w

                if best_link:
                    results.append({
                        "id": item.get("id"),
                        "title": attrs.get("title") or clean_q,
                        "duration": attrs.get("duration") or 0,
                        "width": best_width,
                        "preview_url": preview_thumb,
                        "download_url": best_link,
                    })

                if len(results) >= limit:
                    break

            return results

        except Exception as e:
            logger.error(f"[PexelsDownloader] Ошибка поиска для '{clean_q}': {e}")
            return []

    def download_video_file(
        self,
        url: str,
        dest_path: Path,
        timeout: int = 60
    ) -> bool:
        """
        Скачивает видеофайл MP4 потоком по прямому URL.
        """
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            sess = self._get_session()
            resp = sess.get(url, stream=True, timeout=timeout)
            if resp.status_code == 200:
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                return dest_path.exists() and dest_path.stat().st_size > 10000
            else:
                logger.warning(f"[PexelsDownloader] Ошибка скачивания {url}: HTTP {resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"[PexelsDownloader] Исключение при скачивании {url}: {e}")
            return False

    def fetch_image_bytes(self, url: str) -> Optional[bytes]:
        """
        Скачивает байты превью-обложки через сессию с прокси,
        чтобы миниатюра гарантированно отображалась в браузере даже без VPN.
        """
        if not url or not url.startswith("http"):
            return None
        try:
            sess = self._get_session()
            r = sess.get(url, timeout=6)
            if r.status_code == 200 and r.content:
                return r.content
        except Exception as e:
            logger.debug(f"[PexelsDownloader] Не удалось загрузить байты превью {url}: {e}")
        return None

    @staticmethod
    def generate_broll_queries(scene_texts: List[str], style_context: str = "", batch_size: int = 15) -> List[str]:
        """
        Генерирует лаконичные английские стоковые поисковые теги (2-4 слова)
        для каждой сцены через Gemini с пакетной обработкой (по 15 сцен),
        чтобы гарантировать 100% покрытие всех 90+ сцен без обрезания ответа.
        """
        if not scene_texts:
            return []

        gemini = GeminiClient()
        all_queries = []
        total = len(scene_texts)

        for b_start in range(0, total, batch_size):
            b_end = min(b_start + batch_size, total)
            chunk = scene_texts[b_start:b_end]

            formatted_scenes = "\n".join([f"{i+1}. {text[:220]}" for i, text in enumerate(chunk)])

            prompt = f"""You are a professional video editor and B-roll archivist finding stock footage on Pexels.
Given the visual scene descriptions or script excerpts below, output a concise 2-3 word ENGLISH search query for each scene.

CRITICAL RULES:
1. ONLY return the search queries numbered exactly 1 to {len(chunk)}:
1. query
2. query
...
2. Queries must be physical, filmable stock objects/actions (e.g. "tired person laptop", "empty street rain night", "empty fuel gauge", "car dashboard night", "detective writing desk").
3. Keep it in English, 2-3 words. No punctuation, no quotes, no filler words.

Context: {style_context or 'Documentary / Realism / Drama'}

Scenes:
{formatted_scenes}
"""
            try:
                response_text = gemini.generate(prompt=prompt, temperature=0.25)
                chunk_queries = []
                for line in response_text.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    cleaned = re.sub(r'^(?:Scene\s*)?\d+[\.\:\)]\s*', '', line).strip().strip('"\'')
                    if cleaned:
                        chunk_queries.append(cleaned)
                
                # Заполняем fallback если вернулось меньше
                while len(chunk_queries) < len(chunk):
                    raw = chunk[len(chunk_queries)][:40]
                    chunk_queries.append(re.sub(r'[^\w\s]', '', raw).strip() or "cinematic documentary")

                all_queries.extend(chunk_queries[:len(chunk)])
            except Exception as e:
                logger.error(f"[PexelsDownloader] Ошибка генерации пакета {b_start}-{b_end}: {e}")
                for item in chunk:
                    all_queries.append("cinematic documentary")

        return all_queries[:total]

    @staticmethod
    def sync_prompts_to_timeline(project_dir: Path, step_seconds: int = 30) -> List[Any]:
        """
        Синхронизирует художественные промпты из Раздела 2 (prompts.md)
        напрямую в scenes.json и timeline.json для пошагового монтажа.
        """
        from modules.image_generator import ImageGenerator
        from modules.scene_parser import SceneBlock, save_scenes
        from modules.timeline_builder import TimelineBuilder

        prompts_file = project_dir / "prompts.md"
        if not prompts_file.exists():
            return []

        content = prompts_file.read_text(encoding="utf-8")
        parsed_scenes = ImageGenerator.parse_prompts_from_markdown(content)
        if not parsed_scenes:
            return []

        tl_builder = TimelineBuilder(project_dir)
        existing_scenes = {s.index: s for s in tl_builder.load_timeline()}

        scene_blocks: List[SceneBlock] = []
        for sc in parsed_scenes:
            idx = sc.get("index", 1)
            title = sc.get("title", f"Сцена {idx}")
            prompt_text = sc.get("prompt", "")
            
            # Сохраняем существующий visual_path если он уже был скачан
            existing = existing_scenes.get(idx)
            visual_path = existing.visual_path if existing else None
            effect = existing.effect if existing else "ken_burns_in"

            # Проверяем, есть ли готовый файл на диске
            if not visual_path:
                for candidate in [
                    project_dir / "visuals" / f"scene_{idx:03d}.mp4",
                    project_dir / "visuals" / f"scene_{idx:03d}.jpg",
                    project_dir / "visuals" / f"scene_{idx:03d}.png",
                ]:
                    if candidate.exists():
                        visual_path = str(candidate)
                        break

            sb = SceneBlock(
                index=idx,
                title=title,
                text=prompt_text,  # Используем богатое художественное описание кадра!
                duration=float(step_seconds),
                search_query=existing.search_query if (existing and existing.search_query) else "",
                visual_path=visual_path,
                effect=effect
            )
            scene_blocks.append(sb)

        save_scenes(scene_blocks, project_dir)
        tl_builder.save_timeline(scene_blocks)
        return scene_blocks

    @staticmethod
    def load_cached_candidates(project_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
        """Загружает сохраненные варианты видео из pexels_candidates.json."""
        cache_file = project_dir / "pexels_candidates.json"
        if not cache_file.exists():
            return {}
        try:
            import json
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def save_cached_candidates(project_dir: Path, data: Dict[str, List[Dict[str, Any]]]):
        """Сохраняет найденные варианты видео в pexels_candidates.json."""
        cache_file = project_dir / "pexels_candidates.json"
        try:
            import json
            cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"[PexelsDownloader] Ошибка сохранения кандидатов: {e}")

    def batch_search_candidates(
        self,
        scenes: List[Any],
        project_dir: Path,
        limit_per_scene: int = 3,
        overwrite: bool = False,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Фоновый пакетный пред-поиск кандидатов видео Pexels для всех переданных сцен.
        Находит по 3 варианта для каждой сцены и сохраняет в pexels_candidates.json.
        """
        cached = self.load_cached_candidates(project_dir)
        total = len(scenes)

        for i, s in enumerate(scenes):
            idx = getattr(s, "index", i + 1)
            q = getattr(s, "search_query", "").strip() or "cinematic documentary"
            key = str(idx)

            if key in cached and cached[key] and not overwrite:
                if progress_callback:
                    pct = int((i + 1) / total * 100)
                    progress_callback(pct, f"Кадр #{idx}: уже найдены варианты")
                continue

            if progress_callback:
                pct = int((i + 1) / total * 100)
                progress_callback(pct, f"Кадр #{idx}/{total}: поиск на Pexels: '{q}'...")

            vids = self.search_videos(q, limit=limit_per_scene)
            if not vids:
                short_q = " ".join(q.split()[:2])
                if short_q != q:
                    vids = self.search_videos(short_q, limit=limit_per_scene)

            cached[key] = vids

        self.save_cached_candidates(project_dir, cached)
        return cached
