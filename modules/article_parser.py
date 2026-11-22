import re
import io
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urljoin, urlparse

import trafilatura
from curl_cffi import requests
from bs4 import BeautifulSoup
from PIL import Image

class ArticleParser:
    """
    Интеллектуальный парсер статей, текста и фотографий с веб-страниц для сбора первоисточников сценария.
    Поддерживает обход блокировок, автоматическое зеркалирование (Wayback Machine),
    защиту от Cloudflare/DPI через маскировку TLS (curl_cffi) и извлечение фото с подписями.
    """

    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    }

    SKIP_IMAGE_PATTERNS = [
        'logo', 'icon', 'avatar', 'soc-icon', 'toolbar', 'loading', 'spinner', 
        'banner', 'widget', 'pixel', 'analytics', 'counter', '.svg', '.gif',
        'facebook', 'instagram', 'twitter', 'telegram', 'threads', 'tiktok',
        'wayback-toolbar', '1x1'
    ]

    @classmethod
    def _fetch_html(cls, url: str, direct_timeout: int = 6) -> Tuple[Optional[str], str, str, str]:
        """
        Загружает HTML страницы:
        1. Напрямую через curl_cffi с имперсонацией браузера Chrome.
        2. Через Microlink Reader API (обходит блокировки РКН/DPI и Cloudflare).
        3. Через глобальный веб-архив (Wayback Machine).
        Возвращает: (html, source_method, effective_url, err_msg)
        """
        clean_url = url.strip()
        if not clean_url.startswith(('http://', 'https://')):
            clean_url = 'https://' + clean_url

        html: Optional[str] = None
        source_method = "direct"
        effective_url = clean_url
        err_msg = ""

        # Стратегия 1: Прямая загрузка через curl_cffi с имперсонацией браузера Chrome
        try:
            r = requests.get(
                clean_url, 
                impersonate="chrome120", 
                headers=cls.DEFAULT_HEADERS, 
                timeout=direct_timeout,
                allow_redirects=True
            )
            if r.status_code == 200 and len(r.text) > 500:
                html = r.text
            else:
                err_msg = f"HTTP {r.status_code}"
        except Exception as e:
            err_msg = str(e)

        # Стратегия 2: Облачный прокси-ридер Microlink (обходит блокировки провайдеров и Fastly/DPI)
        if not html:
            try:
                import json
                import urllib.request
                ml_api = f"https://api.microlink.io/?url={clean_url}&data.html.selector=html"
                req = urllib.request.Request(ml_api, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=16) as resp:
                    if resp.status == 200:
                        payload = json.loads(resp.read().decode('utf-8'))
                        ml_html = payload.get("data", {}).get("html", "")
                        if ml_html and len(ml_html) > 500:
                            html = ml_html
                            source_method = "microlink_proxy"
                            effective_url = payload.get("data", {}).get("url") or clean_url
            except Exception as e:
                pass

        # Стратегия 3: Если сайт заблокирован и прокси недоступен, проверяем снимок из Wayback Machine
        if not html:
            try:
                wb_api = f"https://archive.org/wayback/available?url={clean_url}"
                wb_res = requests.get(wb_api, impersonate="chrome120", timeout=8)
                if wb_res.status_code == 200:
                    data = wb_res.json()
                    snapshot = data.get("archived_snapshots", {}).get("closest", {})
                    if snapshot.get("available") and snapshot.get("url"):
                        snap_url = snapshot["url"]
                        snap_res = requests.get(snap_url, impersonate="chrome120", timeout=15)
                        if snap_res.status_code == 200 and len(snap_res.text) > 500:
                            html = snap_res.text
                            source_method = "wayback_mirror"
                            effective_url = snap_url
            except Exception as e:
                pass

        return html, source_method, effective_url, err_msg

    @classmethod
    def parse_url(cls, url: str, direct_timeout: int = 7) -> Dict[str, Any]:
        """
        Парсит веб-страницу по URL, извлекает заголовок и чистый текст статьи.
        """
        clean_url = url.strip()
        if not clean_url:
            return {"success": False, "error": "URL не может быть пустым."}

        html, source_method, effective_url, err_msg = cls._fetch_html(clean_url, direct_timeout=direct_timeout)

        if not html:
            return {
                "success": False, 
                "error": f"Не удалось загрузить страницу (сайт заблокирован или недоступен: {err_msg}). Попробуйте скопировать текст вручную."
            }

        # Извлечение чистого текста через trafilatura (удаляет шапки, меню, рекламу)
        extracted_text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            favor_recall=True
        )

        # Извлечение заголовка статьи
        meta = trafilatura.extract_metadata(html)
        title = meta.title if meta and meta.title else ""
        if not title:
            soup = BeautifulSoup(html, 'html.parser')
            title_tag = soup.find('h1') or soup.find('title')
            if title_tag:
                title = title_tag.get_text().strip()

        # Резервное извлечение через BeautifulSoup, если trafilatura выдала слишком короткий фрагмент
        if not extracted_text or len(extracted_text.strip()) < 150:
            soup = BeautifulSoup(html, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'svg']):
                tag.decompose()
            paras = [p.get_text().strip() for p in soup.find_all(['p', 'h1', 'h2', 'h3', 'blockquote'])]
            extracted_text = '\n\n'.join(p for p in paras if len(p) > 25)
            source_method += "+bs4_fallback"

        if not extracted_text or len(extracted_text.strip()) < 50:
            return {
                "success": False,
                "error": "Не удалось обнаружить основной текст статьи на этой странице."
            }

        cleaned = extracted_text.strip()
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        return {
            "success": True,
            "url": clean_url,
            "title": title.strip(),
            "text": cleaned,
            "chars": len(cleaned),
            "words": len(cleaned.split()),
            "source_method": source_method
        }

    @classmethod
    def parse_article_images(cls, url: str, direct_timeout: int = 7) -> Dict[str, Any]:
        """
        Извлекает все реальные иллюстрации и архивные фото со статьи с их подписями (captions).
        Фильтрует аватары, логотипы, рекламные баннеры и служебные иконки.
        """
        clean_url = url.strip()
        if not clean_url:
            return {"success": False, "error": "URL не указан.", "photos": []}

        html, source_method, effective_url, err_msg = cls._fetch_html(clean_url, direct_timeout=direct_timeout)

        if not html:
            return {
                "success": False,
                "error": f"Не удалось загрузить страницу для поиска фото ({err_msg}).",
                "photos": []
            }

        soup = BeautifulSoup(html, 'html.parser')

        # Заголовок страницы / статьи
        meta = trafilatura.extract_metadata(html)
        title = meta.title if meta and meta.title else ""
        if not title:
            title_tag = soup.find('h1') or soup.find('title')
            title = title_tag.get_text().strip() if title_tag else "Статья"

        # Находим контейнер статьи для отсечения виджетов "Читайте также" и футеров
        article_container = soup.find('article') or soup.find('main') or soup.find(class_=re.compile(r'post|article|content|entry', re.I)) or soup

        # Ищем все figure и img внутри статьи
        seen_urls = set()
        photos: List[Dict[str, Any]] = []

        # 1. Сначала проверяем figure-теги (наиболее надежные контентные иллюстрации с подписями)
        for fig in article_container.find_all('figure'):
            img = fig.find('img')
            if not img:
                continue

            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if not src:
                continue

            src = urljoin(effective_url, src)
            src_lower = src.lower()
            if any(p in src_lower for p in cls.SKIP_IMAGE_PATTERNS):
                continue

            if src in seen_urls:
                continue
            seen_urls.add(src)

            # Подпись к фото
            cap_el = fig.find('figcaption')
            caption = cap_el.get_text().strip() if cap_el else ''
            if not caption:
                caption = img.get('alt', '').strip() or img.get('title', '').strip()

            p_idx = len(photos) + 1
            # Формируем имя файла
            slug_cap = re.sub(r'[^a-zA-Zа-яА-Я0-9]', '_', caption[:30]).strip('_').lower() if caption else f"photo_{p_idx:02d}"
            slug_cap = re.sub(r'_+', '_', slug_cap)
            filename_sug = f"article_{p_idx:02d}_{slug_cap}.jpg"

            photos.append({
                "index": p_idx,
                "url": src,
                "caption": caption if caption else f"Иллюстрация #{p_idx}",
                "filename": filename_sug
            })

        # 2. Если в figure ничего не нашлось, проверяем все теги img внутри статьи
        if len(photos) < 3:
            for img in article_container.find_all('img'):
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if not src:
                    continue

                src = urljoin(effective_url, src)
                src_lower = src.lower()
                if any(p in src_lower for p in cls.SKIP_IMAGE_PATTERNS):
                    continue

                if src in seen_urls:
                    continue
                seen_urls.add(src)

                caption = img.get('alt', '').strip() or img.get('title', '').strip()

                p_idx = len(photos) + 1
                slug_cap = re.sub(r'[^a-zA-Zа-яА-Я0-9]', '_', caption[:30]).strip('_').lower() if caption else f"photo_{p_idx:02d}"
                slug_cap = re.sub(r'_+', '_', slug_cap)
                filename_sug = f"article_{p_idx:02d}_{slug_cap}.jpg"

                photos.append({
                    "index": p_idx,
                    "url": src,
                    "caption": caption if caption else f"Иллюстрация #{p_idx}",
                    "filename": filename_sug
                })

        return {
            "success": True,
            "url": clean_url,
            "title": title,
            "photos": photos,
            "count": len(photos),
            "source_method": source_method
        }

    @classmethod
    def download_image(cls, img_url: str, save_path: Path, timeout: int = 10) -> bool:
        """
        Скачивает изображение по URL, валидирует через PIL и сохраняет в проект.
        При блокировке прямого хостинга/CDN автоматически использует распределенный кэш wsrv.nl.
        """
        save_path.parent.mkdir(parents=True, exist_ok=True)
        img_bytes = None

        # 1. Попытка прямой загрузки
        try:
            r = requests.get(
                img_url, 
                impersonate="chrome120", 
                timeout=timeout,
                allow_redirects=True
            )
            if r.status_code == 200 and len(r.content) > 500:
                img_bytes = r.content
        except Exception:
            pass

        # 2. Если прямой CDN заблокирован провайдером (например, storage.ghost.io / Fastly),
        # используем всемирный Cloudflare image proxy wsrv.nl
        if not img_bytes:
            try:
                import urllib.request
                proxy_url = f"https://wsrv.nl/?url={img_url}&output=jpg"
                req = urllib.request.Request(proxy_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status == 200:
                        data = resp.read()
                        if len(data) > 500:
                            img_bytes = data
            except Exception:
                pass

        if not img_bytes:
            return False

        try:
            # Валидируем изображение через Pillow
            img = Image.open(io.BytesIO(img_bytes))
            
            # Если сохраняем как JPEG, приводим любые режимы (RGBA, P, LA и т.д.) к RGB
            if save_path.suffix.lower() in ('.jpg', '.jpeg'):
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(save_path, "JPEG", quality=92)
            else:
                save_path.write_bytes(img_bytes)

            return True
        except Exception:
            return False
