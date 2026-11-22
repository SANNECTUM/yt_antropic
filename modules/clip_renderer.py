"""
clip_renderer.py
Рендерит один клип (фото или видео) с выбранным эффектом через moviepy 2.x.
Поддерживаемые эффекты:
  - ken_burns_in   : плавный наезд 1.0 → 1.12
  - ken_burns_out  : плавный отъезд 1.12 → 1.0
  - pan_left       : панорама слева направо при фиксированном зуме 1.08
  - pan_right      : панорама справа налево при фиксированном зуме 1.08
  - fade           : статичный кадр с FadeIn/FadeOut
  - slide_left     : SlideIn слева
  - slide_right    : SlideIn справа
  - none           : статичный кадр без эффектов
"""

import numpy as np
from pathlib import Path
from typing import Optional, Tuple

from moviepy import ImageClip, VideoFileClip, CompositeVideoClip
from moviepy.video.fx import FadeIn, FadeOut, Resize


RESOLUTION = (1920, 1080)
FPS = 30


def _crop_to_ratio(frame: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """Кадрирует numpy-массив в центре к нужному соотношению сторон."""
    h, w = frame.shape[:2]
    target_ratio = target_w / target_h
    cur_ratio = w / h
    if cur_ratio > target_ratio:
        new_w = int(h * target_ratio)
        off = (w - new_w) // 2
        frame = frame[:, off:off + new_w]
    else:
        new_h = int(w / target_ratio)
        off = (h - new_h) // 2
        frame = frame[off:off + new_h, :]
    return frame


def _load_base_clip(source_path: Path, duration: float) -> "ImageClip | VideoFileClip":
    """Загружает кадр и приводит к нужному разрешению 16:9."""
    ext = source_path.suffix.lower()
    target_w, target_h = RESOLUTION

    if ext in (".mp4", ".mov", ".avi", ".webm", ".mkv"):
        clip = VideoFileClip(str(source_path))
        # Обрезаем до нужной длительности
        if clip.duration > duration:
            clip = clip.subclipped(0, duration)
        else:
            # Зацикливаем короткий клип
            from moviepy.video.fx import Loop
            clip = clip.with_effects([Loop()])
            clip = clip.with_duration(duration)
        # Масштабируем
        clip_ratio = clip.w / clip.h
        target_ratio = target_w / target_h
        if abs(clip_ratio - target_ratio) < 0.05:
            clip = clip.resized((target_w, target_h))
        else:
            if clip_ratio > target_ratio:
                clip = clip.resized(height=target_h)
                x_off = (clip.w - target_w) // 2
                from moviepy.video.fx import Crop
                clip = clip.with_effects([Crop(x1=x_off, y1=0, x2=x_off + target_w, y2=target_h)])
            else:
                clip = clip.resized(width=target_w)
                y_off = (clip.h - target_h) // 2
                from moviepy.video.fx import Crop
                clip = clip.with_effects([Crop(x1=0, y1=y_off, x2=target_w, y2=y_off + target_h)])
        return clip.with_fps(FPS)

    else:
        # Фото
        clip = ImageClip(str(source_path)).with_duration(duration).with_fps(FPS)
        # Масштаб + кадрирование
        clip_ratio = clip.w / clip.h
        target_ratio = target_w / target_h
        if clip_ratio > target_ratio:
            clip = clip.resized(height=target_h)
            x_off = (clip.w - target_w) // 2
            from moviepy.video.fx import Crop
            clip = clip.with_effects([Crop(x1=x_off, y1=0, x2=x_off + target_w, y2=target_h)])
        else:
            clip = clip.resized(width=target_w)
            y_off = (clip.h - target_h) // 2
            from moviepy.video.fx import Crop
            clip = clip.with_effects([Crop(x1=0, y1=y_off, x2=target_w, y2=y_off + target_h)])
        return clip


def render_clip(
    source_path: Path,
    output_path: Path,
    duration: float,
    effect: str = "ken_burns_in",
    fade_in: float = 0.4,
    fade_out: float = 0.4,
    resolution: Tuple[int, int] = RESOLUTION,
    fps: int = FPS,
) -> Path:
    """
    Рендерит один клип с указанным эффектом.
    Возвращает путь к готовому MP4.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    target_w, target_h = resolution

    base = _load_base_clip(source_path, duration)

    # ---------------------------------------------------------------- #
    # Применяем эффект
    # ---------------------------------------------------------------- #
    if effect == "ken_burns_in":
        # Zoom In 1.0 → 1.12
        zoom_start = 1.0
        zoom_end = 1.12
        base = base.resized(width=target_w * zoom_end, height=target_h * zoom_end)

        def kb_in_frame(get_frame, t):
            frame = get_frame(t)
            scale = zoom_start + (zoom_end - zoom_start) * (t / duration)
            # кроп из центра до нужного размера
            h, w = frame.shape[:2]
            crop_w = int(w / scale)
            crop_h = int(h / scale)
            x1 = (w - crop_w) // 2
            y1 = (h - crop_h) // 2
            cropped = frame[y1:y1 + crop_h, x1:x1 + crop_w]
            from PIL import Image
            import numpy as np
            img = Image.fromarray(cropped).resize((target_w, target_h), Image.Resampling.LANCZOS)
            return np.array(img)

        base = base.transform(kb_in_frame, apply_to="mask")

    elif effect == "ken_burns_out":
        zoom_start = 1.12
        zoom_end = 1.0
        base = base.resized(width=int(target_w * zoom_start), height=int(target_h * zoom_start))

        def kb_out_frame(get_frame, t):
            frame = get_frame(t)
            scale = zoom_start + (zoom_end - zoom_start) * (t / duration)
            h, w = frame.shape[:2]
            crop_w = int(w / scale)
            crop_h = int(h / scale)
            x1 = (w - crop_w) // 2
            y1 = (h - crop_h) // 2
            cropped = frame[y1:y1 + crop_h, x1:x1 + crop_w]
            from PIL import Image
            import numpy as np
            img = Image.fromarray(cropped).resize((target_w, target_h), Image.Resampling.LANCZOS)
            return np.array(img)

        base = base.transform(kb_out_frame, apply_to="mask")

    elif effect == "pan_left":
        # Немного шире, едем слева направо
        base = base.resized(width=int(target_w * 1.08), height=int(target_h * 1.08))

        def pan_left_frame(get_frame, t):
            frame = get_frame(t)
            h, w = frame.shape[:2]
            max_offset = w - target_w
            x1 = int(max_offset * (t / duration))
            y1 = (h - target_h) // 2
            from PIL import Image
            import numpy as np
            cropped = frame[y1:y1 + target_h, x1:x1 + target_w]
            return cropped

        base = base.transform(pan_left_frame, apply_to="mask")

    elif effect == "pan_right":
        base = base.resized(width=int(target_w * 1.08), height=int(target_h * 1.08))

        def pan_right_frame(get_frame, t):
            frame = get_frame(t)
            h, w = frame.shape[:2]
            max_offset = w - target_w
            x1 = int(max_offset * (1 - t / duration))
            y1 = (h - target_h) // 2
            from PIL import Image
            import numpy as np
            cropped = frame[y1:y1 + target_h, x1:x1 + target_w]
            return cropped

        base = base.transform(pan_right_frame, apply_to="mask")

    elif effect in ("slide_left", "slide_right"):
        direction = "left" if effect == "slide_left" else "right"
        slide_dur = min(0.6, duration * 0.3)

        def slide_frame(get_frame, t):
            frame = get_frame(t)
            if t < slide_dur:
                progress = t / slide_dur
                # ease-out
                progress = 1 - (1 - progress) ** 2
                offset = int((1 - progress) * target_w)
                if direction == "left":
                    offset = -offset
                from PIL import Image
                import numpy as np
                img = Image.fromarray(frame)
                bg = Image.new("RGB", (target_w, target_h), (10, 10, 10))
                bg.paste(img, (offset, 0))
                return np.array(bg)
            return frame

        base = base.transform(slide_frame, apply_to="mask")

    # Fade in / out
    effects_to_apply = []
    if fade_in > 0:
        effects_to_apply.append(FadeIn(fade_in))
    if fade_out > 0 and duration > fade_out * 2:
        effects_to_apply.append(FadeOut(fade_out))
    if effects_to_apply:
        base = base.with_effects(effects_to_apply)

    base.write_videofile(
        str(output_path),
        fps=fps,
        codec="libx264",
        preset="fast",
        ffmpeg_params=["-crf", "20"],
        audio=False,
        logger=None,
    )
    return output_path
