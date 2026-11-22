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

from modules.scene_parser import SceneBlock, load_scenes, save_scenes
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

    def render_scene_clip(self, scene: SceneBlock, force: bool = False) -> Optional[Path]:
        """
        Рендерит клип для одной сцены.
        Возвращает Path к MP4 или None если кадр не назначен.
        """
        if not scene.visual_path:
            return None
        source = Path(scene.visual_path)
        if not source.exists():
            return None

        out = self.render_dir / f"clip_{scene.index:03d}.mp4"
        if out.exists() and not force:
            return out

        render_clip(
            source_path=source,
            output_path=out,
            duration=scene.effective_duration,
            effect=scene.effect,
        )
        return out if out.exists() else None

    def render_all_scene_clips(
        self,
        scenes: List[SceneBlock],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        force: bool = False,
    ) -> List[Path]:
        """Рендерит клипы для всех сцен с заполненным visual_path."""
        clips: List[Path] = []
        total = len([s for s in scenes if s.visual_path])
        done = 0
        for s in scenes:
            clip = self.render_scene_clip(s, force=force)
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
    ) -> Path:
        """
        Рендерит и склеивает все клипы в единый видеоряд (без аудио).
        Возвращает путь к render/videotrack.mp4.
        """
        output = self.render_dir / "videotrack.mp4"

        # 1. Рендерим все клипы
        total_scenes = len([s for s in scenes if s.visual_path])
        done = 0

        clip_paths: List[Path] = []
        for s in scenes:
            if not s.visual_path:
                continue
            if progress_callback:
                progress_callback(0.05 + 0.75 * (done / max(total_scenes, 1)),
                                  f"Рендер клипа {done + 1}/{total_scenes}: {s.title[:40]}")
            p = self.render_scene_clip(s, force=force)
            if p:
                clip_paths.append(p)
            done += 1

        if not clip_paths:
            raise RuntimeError("Нет ни одного клипа для склейки. Назначьте кадры сценам.")

        # 2. Concat через FFmpeg (быстрее moviepy для финальной склейки)
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

        if not output.exists() or output.stat().st_size < 5000:
            raise RuntimeError("Ошибка при создании видеоряда.")

        if progress_callback:
            progress_callback(1.0, f"Видеоряд готов ({output.stat().st_size // (1024 * 1024)} MB)")

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
        Если audio_path=None — сохраняет видеоряд с тишиной.
        """
        videotrack = self.render_dir / "videotrack.mp4"
        if not videotrack.exists():
            raise FileNotFoundError("Сначала выполните build_videotrack().")

        output = self.project_dir / "final_video.mp4"

        if progress_callback:
            progress_callback(0.3, "Сведение видео с аудиодорожкой...")

        if audio_path and audio_path.exists():
            # Получаем длительность видеотрека
            dur_cmd = [self.ffmpeg, "-i", str(videotrack), "-f", "null", "-"]
            dur_res = subprocess.run(dur_cmd, capture_output=True, text=True, errors="ignore")
            import re
            m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", dur_res.stderr)
            video_dur = 0.0
            if m:
                video_dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))

            # Быстрое сведение без лишнего перекодирования видеоряда
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
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
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
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                "-pix_fmt", "yuv420p",
                str(output),
            ]

        subprocess.run(cmd, capture_output=True, errors="ignore")

        if not output.exists() or output.stat().st_size < 10000:
            raise RuntimeError("Ошибка финального рендера видео.")

        if progress_callback:
            progress_callback(1.0, f"Готово! ({output.stat().st_size // (1024 * 1024)} MB)")

        return output

    # ------------------------------------------------------------------ #
    # Утилита: суммарная длительность таймлайна
    # ------------------------------------------------------------------ #

    @staticmethod
    def total_duration(scenes: List[SceneBlock]) -> float:
        return sum(s.effective_duration for s in scenes if s.visual_path)
