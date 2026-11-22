import re
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Optional
from curl_cffi import requests
from PIL import Image
import io
import config

class WebImageSearcher:
    """
    Универсальный поисковик и загрузчик реальных изображений и архивных кадров.
    Поддерживает:
      - Bing Images (без API-ключей, высокое разрешение 1080p+)
      - Yandex Images (без API-ключей, криминальная хроника и лица)
      - Google Custom Search API (через бесплатный ключ из .env)
      - Wikimedia Commons (архивы, карты, документы)
      - Pexels (атмосферный b-roll)
    """

    def __init__(self):
        self.session = requests.Session(impersonate="chrome120")

    def search(
        self,
        query: str,
        engine: str = "all",
        limit: int = 12
    ) -> List[Dict[str, Any]]:
        """
        Главный метод поиска.
        engine: 'all' | 'bing' | 'yandex' | 'google' | 'wikimedia' | 'pexels'
        """
        query = query.strip()
        if not query:
            return []

        results: List[Dict[str, Any]] = []

        if engine == "bing":
            results = self.search_bing(query, limit=limit)
        elif engine == "yandex":
            results = self.search_yandex(query, limit=limit)
        elif engine == "google":
            results = self.search_google_api(query, limit=limit)
        elif engine == "wikimedia":
            results = self.search_wikimedia(query, limit=limit)
        elif engine == "pexels":
            results = self.search_pexels(query, limit=limit)
        else:
            # "all" - агрегированный мульти-поиск
            # Сначала Bing и Yandex (работают всегда без ключей)
            bing_res = self.search_bing(query, limit=limit // 2 + 2)
            results.extend(bing_res)

            yandex_res = self.search_yandex(query, limit=limit // 2 + 2)
            results.extend(yandex_res)

            # Если настроен Google API
            if config.GOOGLE_SEARCH_API_KEY and config.GOOGLE_SEARCH_CX:
                google_res = self.search_google_api(query, limit=6)
                results.extend(google_res)

            # Wikimedia для исторического контекста
            wiki_res = self.search_wikimedia(query, limit=4)
            results.extend(wiki_res)

        # Дедупликация по URL
        seen_urls = set()
        unique_results = []
        for r in results:
            url = r.get("image_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)

        return unique_results[:limit]

    def search_bing(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        """
        Парсинг Bing Images (высокое разрешение, 1080p, новости США и мира).
        """
        results = []
        try:
            url = f"https://www.bing.com/images/search?q={urllib.parse.quote(query)}&form=HDRSC2&first=1"
            resp = self.session.get(url, timeout=12)
            if resp.status_code == 200:
                # Извлекаем JSON параметры картинок: murl (original), turl (thumbnail), t (title)
                # Пример: m="{&quot;murl&quot;:&quot;https://...&quot;,&quot;turl&quot;:&quot;https://...&quot;,&quot;t&quot;:&quot;...&quot;}"
                blocks = re.findall(r'm=\"({.*?})\"', resp.text)
                for b in blocks:
                    clean_json = b.replace("&quot;", '"').replace("&#39;", "'").replace("&amp;", "&")
                    murl_m = re.search(r'\"murl\":\"(https?://[^\"]+)\"', clean_json)
                    turl_m = re.search(r'\"turl\":\"(https?://[^\"]+)\"', clean_json)
                    title_m = re.search(r'\"t\":\"([^\"]+)\"', clean_json)

                    if murl_m:
                        img_url = murl_m.group(1)
                        thumb_url = turl_m.group(1) if turl_m else img_url
                        title = title_m.group(1) if title_m else query
                        results.append({
                            "title": title,
                            "image_url": img_url,
                            "thumb_url": thumb_url,
                            "source": "Bing Images",
                            "engine": "bing"
                        })
                        if len(results) >= limit:
                            break
        except Exception as e:
            print(f"[WebImageSearcher] Ошибка поиска в Bing: {e}")

        return results

    def search_yandex(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        """
        Парсинг Яндекс Картинки (идеально для лиц и криминальной хроники).
        """
        results = []
        try:
            url = f"https://yandex.ru/images/search?text={urllib.parse.quote(query)}"
            resp = self.session.get(url, timeout=12)
            if resp.status_code == 200:
                # В Яндекс данные лежат в data-bem с url
                matches = re.findall(r'&quot;url&quot;:&quot;(https?://[^&]+)&quot;', resp.text)
                # Фильтруем картинки
                for url in matches:
                    if any(url.lower().endswith(ext) or ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        results.append({
                            "title": query,
                            "image_url": url,
                            "thumb_url": url,
                            "source": "Яндекс Картинки",
                            "engine": "yandex"
                        })
                        if len(results) >= limit:
                            break
        except Exception as e:
            print(f"[WebImageSearcher] Ошибка поиска в Яндекс: {e}")

        return results

    def search_google_api(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Поиск через официальный Google Custom Search JSON API.
        """
        results = []
        api_key = config.GOOGLE_SEARCH_API_KEY
        cx = config.GOOGLE_SEARCH_CX

        if not api_key or not cx:
            return results

        try:
            url = (
                f"https://www.googleapis.com/customsearch/v1"
                f"?q={urllib.parse.quote(query)}"
                f"&searchType=image"
                f"&key={api_key}"
                f"&cx={cx}"
                f"&num={min(limit, 10)}"
            )
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                for item in items:
                    img_url = item.get("link", "")
                    thumb_url = item.get("image", {}).get("thumbnailLink", img_url)
                    title = item.get("title", query)
                    width = item.get("image", {}).get("width")
                    height = item.get("image", {}).get("height")
                    meta = f"{width}x{height}" if width and height else ""

                    if img_url:
                        results.append({
                            "title": f"{title} ({meta})" if meta else title,
                            "image_url": img_url,
                            "thumb_url": thumb_url,
                            "source": "Google Images (API)",
                            "engine": "google"
                        })
        except Exception as e:
            print(f"[WebImageSearcher] Ошибка Google Custom Search API: {e}")

        return results

    def search_wikimedia(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        """
        Поиск архивных и исторических фото в Wikimedia Commons.
        """
        results = []
        try:
            url = (
                f"https://commons.wikimedia.org/w/api.php?action=query"
                f"&generator=search&gsrsearch={urllib.parse.quote(query)}"
                f"&gsrnamespace=6&prop=imageinfo&iiprop=url|size|mime"
                f"&format=json&gsrlimit={limit}"
            )
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                pages = data.get("query", {}).get("pages", {})
                for pid, pinfo in pages.items():
                    infos = pinfo.get("imageinfo", [])
                    if infos:
                        img_info = infos[0]
                        img_url = img_info.get("url", "")
                        title = pinfo.get("title", "").replace("File:", "")
                        if img_url:
                            results.append({
                                "title": title,
                                "image_url": img_url,
                                "thumb_url": img_url,
                                "source": "Wikimedia Commons",
                                "engine": "wikimedia"
                            })
        except Exception as e:
            print(f"[WebImageSearcher] Ошибка Wikimedia Commons: {e}")

        return results

    def search_pexels(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        """
        Поиск стоковых кинематографичных фото на Pexels.
        """
        results = []
        api_key = config.PEXELS_API_KEY
        if not api_key:
            return results

        try:
            url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(query)}&per_page={limit}"
            resp = self.session.get(url, headers={"Authorization": api_key}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                photos = data.get("photos", [])
                for p in photos:
                    img_url = p.get("src", {}).get("large2x") or p.get("src", {}).get("original")
                    thumb_url = p.get("src", {}).get("medium") or img_url
                    alt = p.get("alt") or query
                    if img_url:
                        results.append({
                            "title": alt,
                            "image_url": img_url,
                            "thumb_url": thumb_url,
                            "source": "Pexels B-Roll",
                            "engine": "pexels"
                        })
        except Exception as e:
            print(f"[WebImageSearcher] Ошибка Pexels: {e}")

        return results

    def download_image(self, image_url: str, save_path: Path, thumb_url: Optional[str] = None) -> Path:
        """
        Скачивает изображение по URL с автоматическим fallback на превью при таймаутах.
        Проверяет валидность файла через Pillow и сохраняет на диск.
        """
        save_path.parent.mkdir(parents=True, exist_ok=True)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        }

        urls_to_try = [image_url]
        if thumb_url and thumb_url != image_url:
            urls_to_try.append(thumb_url)

        last_err = None
        for u in urls_to_try:
            # Попытка 1: через curl_cffi session
            try:
                resp = self.session.get(u, headers=headers, timeout=7)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    img = Image.open(io.BytesIO(resp.content))
                    img.verify()
                    save_path.write_bytes(resp.content)
                    return save_path
            except Exception as e:
                last_err = e

            # Попытка 2: через стандартный urllib
            try:
                req = urllib.request.Request(u, headers=headers)
                with urllib.request.urlopen(req, timeout=7) as r:
                    content = r.read()
                    if len(content) > 1000:
                        img = Image.open(io.BytesIO(content))
                        img.verify()
                        save_path.write_bytes(content)
                        return save_path
            except Exception as e:
                last_err = e

        raise ValueError(f"Не удалось скачать изображение: {last_err}")
