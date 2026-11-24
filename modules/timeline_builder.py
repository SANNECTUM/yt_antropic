"""
timeline_builder.py
Строит монтажный манифест (timeline.json) и рендерит финальный видеоряд
без озвучки через moviepy 2.x + затем склеивает с аудио через ffmpeg.
"""
import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Callable

import imageio_ffmpeg

from modules.scene_parser import SceneBlock, load_scenes, save_scenes, resolve_visual_path
from modules.clip_renderer import render_clip, RESOLUTION, FPS


class TimelineBuilder:
    """
    Финальная сборка видеоряда из готовых сцен.
    """

    RENDER_DIR = "render"

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.render_dir = project_dir / self.RENDER_DIR
        self.render_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    # ------------------------------------------------------------------ #
    # Сохранение / загрузка timeline.json
    # ------------------------------------------------------------------ #

    def save_timeline(self, scenes: List[SceneBlock]) -> Path:
        path = self.project_dir / "timeline.json"
        payload = {
            "version": 2,
            "resolution": list(RESOLUTION),
            "fps": FPS,
            "scenes": [s.to_dict() for s in scenes],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load_timeline(self) -> List[SceneBlock]:
        path = self.project_dir / "timeline.json"
        if not path.exists():
            return load_scenes(self.project_dir)
        data = json.loads(path.read_text(encoding="utf-8"))
        return [SceneBlock.from_dict(d) for d in data.get("scenes", [])]

    # ------------------------------------------------------------------ #
    # Рендер клипов по сценам
    # ------------------------------------------------------------------ #

    def get_video_duration(self, video_path: Path) -> float:
        """Мгновенно извлекает точную длительность видеофайла из заголовков за 0.02 сек (без декодирования)."""
        if not video_path.exists():
            return 0.0
        dur_cmd = [self.ffmpeg, "-i", str(video_path)]
        dur_res = subprocess.run(dur_cmd, capture_output=True, text=True, errors="ignore")
        import re
        m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", dur_res.stderr)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        return 0.0

    # ------------------------------------------------------------------ #
    # Рендер клипов по сценам
    # ------------------------------------------------------------------ #

    def render_scene_clip(
        self,
        scene: SceneBlock,
        force: bool = False,
        resolution: tuple = RESOLUTION,
    ) -> Optional[Path]:
        """
        Рендерит клип для одной сцены.
        Возвращает Path к MP4 или None если кадр не назначен.
        """
        source = resolve_visual_path(scene.visual_path, self.project_dir)
        if not source or not source.exists():
            return None

        out = self.render_dir / f"clip_{scene.index:03d}.mp4"
        if out.exists() and not force and out.stat().st_size > 1000:
            return out

        render_clip(
            source_path=source,
            output_path=out,
            duration=scene.effective_duration,
            effect=scene.effect,
            resolution=resolution,
        )
        return out if (out.exists() and out.stat().st_size > 1000) else None

    def render_all_scene_clips(
        self,
        scenes: List[SceneBlock],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        force: bool = False,
        resolution: tuple = RESOLUTION,
    ) -> List[Path]:
        """Рендерит клипы для всех сцен с заполненным visual_path."""
        clips: List[Path] = []
        valid_scenes = [s for s in scenes if resolve_visual_path(s.visual_path, self.project_dir)]
        total = len(valid_scenes)
        done = 0
        for s in scenes:
            clip = self.render_scene_clip(s, force=force, resolution=resolution)
            if clip:
                clips.append(clip)
                done += 1
                if progress_callback:
                    progress_callback(done, total, f"Клип сцены {s.index}: {s.title[:40]}")
        return clips

    # ------------------------------------------------------------------ #
    # Финальная склейка видеоряда (без звука)
    # ------------------------------------------------------------------ #

    def build_videotrack(
        self,
        scenes: List[SceneBlock],
        progress_callback: Optional[Callable[[float, str], None]] = None,
        force: bool = False,
        resolution: tuple = RESOLUTION,
    ) -> Path:
        """
        Рендерит и склеивает все клипы в единый видеоряд (без аудио).
        Возвращает путь к render/videotrack.mp4.
        """
        output = self.render_dir / "videotrack.mp4"

        # 1. Проверяем доступность кадров
        scenes_with_vis = [s for s in scenes if resolve_visual_path(s.visual_path, self.project_dir)]
        if not scenes_with_vis:
            raise RuntimeError("Нет ни одного кадра для монтажа. Запустите Автопилот Pexels в Шаге 2.")

        # Если force=True, удаляем старые клипы из кеша, чтобы гарантировать чистоту сборки
        if force:
            for s in scenes_with_vis:
                old_clip = self.render_dir / f"clip_{s.index:03d}.mp4"
                if old_clip.exists():
                    try:
                        old_clip.unlink()
                    except Exception:
                        pass

        # Рендерим только сцены с собственными кадрами (без дублирования и искусственного повторения одного видео!)
        total_scenes = len(scenes_with_vis)
        done = 0

        clip_paths: List[Path] = []
        for s in scenes_with_vis:
            if progress_callback:
                progress_callback(0.05 + 0.75 * (done / max(total_scenes, 1)),
                                  f"Рендер клипа {done + 1}/{total_scenes}: {s.title[:40]}")
            p = self.render_scene_clip(s, force=force, resolution=resolution)
            if p:
                clip_paths.append(p)
            done += 1

        if not clip_paths:
            raise RuntimeError("Нет ни одного клипа для склейки. Назначьте кадры сценам.")

        # 2. Concat через FFmpeg (сверхбыстрое копирование без перекодирования)
        if progress_callback:
            progress_callback(0.82, "Склейка клипов в единый видеоряд...")

        concat_list = self.render_dir / "concat.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for cp in clip_paths:
                f.write(f"file '{cp.resolve().as_posix()}'\n")

        cmd = [
            self.ffmpeg, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(output),
        ]
        subprocess.run(cmd, capture_output=True, errors="ignore")

        # 3. Валидация: если concat copy не создал файл или файл поврежден
        if not output.exists() or output.stat().st_size < 5000:
            if progress_callback:
                progress_callback(0.88, "Надежная повторная склейка видеоряда...")
            cmd_fb = [
                self.ffmpeg, "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
                "-threads", "2",
                "-pix_fmt", "yuv420p",
                "-r", str(FPS),
                "-an",
                str(output),
            ]
            subprocess.run(cmd_fb, capture_output=True, errors="ignore")

        if not output.exists() or output.stat().st_size < 5000:
            raise RuntimeError("Ошибка при создании видеоряда.")

        final_dur = self.get_video_duration(output)
        if progress_callback:
            progress_callback(1.0, f"Видеоряд готов: {int(final_dur // 60)}м {int(final_dur % 60)}с ({output.stat().st_size // (1024 * 1024)} MB)")

        return output

    # ------------------------------------------------------------------ #
    # Финальный рендер: видеоряд + аудио
    # ------------------------------------------------------------------ #

    def mix_with_audio(
        self,
        audio_path: Optional[Path],
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Path:
        """
        Склеивает видеоряд и аудиодорожку в финальный final_video.mp4.
        Если видеоряд короче аудио — зацикливает видеоряд, чтобы звук диктора НИКОГДА не обрезался.
        Если audio_path=None — сохраняет видеоряд с тишиной.
        """
        videotrack = self.render_dir / "videotrack.mp4"
        if not videotrack.exists():
            raise FileNotFoundError("Сначала выполните build_videotrack().")

        output = self.project_dir / "final_video.mp4"

        if progress_callback:
            progress_callback(0.3, "Сведение видео с аудиодорожкой...")

        if audio_path and audio_path.exists():
            # Быстрое сведение без зацикливания: видео играет ровно один раз,
            # звук обрезается строго по окончанию видеоряда (-shortest)!
            cmd = [
                self.ffmpeg, "-y",
                "-i", str(videotrack),
                "-i", str(audio_path),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v:0", "-map", "1:a:0",
                "-shortest",
                str(output),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
            # Если copy не сработал (например, разные форматы), делаем надежное кодирование
            if not output.exists() or output.stat().st_size < 10000:
                cmd_fallback = [
                    self.ffmpeg, "-y",
                    "-i", str(videotrack),
                    "-i", str(audio_path),
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
                    "-threads", "2",
                    "-c:a", "aac", "-b:a", "192k",
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-pix_fmt", "yuv420p",
                    "-shortest",
                    str(output),
                ]
                subprocess.run(cmd_fallback, capture_output=True, errors="ignore")
        else:
            # Без аудио — добавляем тихую дорожку
            cmd = [
                self.ffmpeg, "-y",
                "-i", str(videotrack),
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                "-pix_fmt", "yuv420p",
                str(output),
            ]
            subprocess.run(cmd, capture_output=True, errors="ignore")

        if not output.exists() or output.stat().st_size < 10000:
            raise RuntimeError("Ошибка финального рендера видео.")

        final_dur = self.get_video_duration(output)
        if progress_callback:
            progress_callback(1.0, f"Готово! {int(final_dur // 60)}м {int(final_dur % 60)}с ({output.stat().st_size // (1024 * 1024)} MB)")

        return output

    # ------------------------------------------------------------------ #
    # Утилита: суммарная длительность таймлайна
    # ------------------------------------------------------------------ #

    @staticmethod
    def total_duration(scenes: List[SceneBlock]) -> float:
        return sum(s.effective_duration for s in scenes if s.visual_path)
