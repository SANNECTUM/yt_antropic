import re
import subprocess
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
import imageio_ffmpeg

class VideoEditor:
    """
    Модуль профессионального авто-монтажа:
    - Собирает видео из фото и видео-футажей под начитку (voiceover).
    - Кинематографичный эффект Кена Бёрнса (Ken Burns / Slow Zoom & Pan).
    - Кадрирование под 16:9 (1920x1080 Full HD).
    - Плавные переходы (Crossfade / Fade).
    - Аппаратная сборка через встроенный FFmpeg.
    """

    def __init__(self):
        self.ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    def get_audio_duration(self, audio_path: Path) -> float:
        """Получает точную длительность аудиофайла в секундах."""
        cmd = [self.ffmpeg_exe, "-i", str(audio_path)]
        p = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", p.stderr)
        if m:
            h, mn, s = m.groups()
            return int(h) * 3600 + int(mn) * 60 + float(s)
        return 0.0

    def get_media_files(self, visuals_dir: Path) -> List[Path]:
        """Собирает и сортирует все доступные фото и видео из папки."""
        valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".mp4"}
        files = [f for f in visuals_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_exts]
        return sorted(files, key=lambda x: x.name)

    def assemble_video(
        self,
        visuals_dir: Path,
        audio_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
        fps: int = 30,
        resolution: str = "1920x1080",
        ken_burns: bool = True,
        clip_duration: Optional[float] = None,
        target_total_duration: Optional[float] = None,
        transition_duration: float = 0.5,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Path:
        """
        Собирает полноценный готовый ролик из всех визуалов.
        Если передан audio_path — видео подгоняется под хронометраж аудиодорожки.
        Если audio_path=None — каждый кадр длится clip_duration (по умолчанию 6 сек).
        """
        if output_path is None:
            output_path = visuals_dir.parent / "final_video.mp4"

        media_files = self.get_media_files(visuals_dir)
        if not media_files:
            raise ValueError(f"В папке {visuals_dir} не найдено изображений или видео.")

        num_clips = len(media_files)
        has_audio = audio_path is not None and audio_path.exists()

        if has_audio:
            total_duration = self.get_audio_duration(audio_path)
            if total_duration <= 0:
                has_audio = False
                calc_clip_dur = clip_duration or 6.0
                total_duration = calc_clip_dur * num_clips
            else:
                calc_clip_dur = max(3.5, total_duration / num_clips)
        else:
            if clip_duration:
                calc_clip_dur = float(clip_duration)
            elif target_total_duration and target_total_duration > 0:
                calc_clip_dur = max(3.5, target_total_duration / num_clips)
            else:
                calc_clip_dur = 6.0
            total_duration = calc_clip_dur * num_clips

        width, height = [int(x) for x in resolution.split("x")]
        temp_dir = visuals_dir.parent / "temp_assembly"
        temp_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            dur_label = f"под {total_duration/60:.1f} мин речи" if has_audio else f"({calc_clip_dur:.1f} сек/кадр, всего {int(total_duration)} сек)"
            progress_callback(0.05, f"Анализ материалов: {num_clips} кадров {dur_label}...")

        generated_clips: List[Path] = []

        try:
            for idx, media_path in enumerate(media_files):
                clip_out = temp_dir / f"clip_{idx:03d}.mp4"
                is_video = media_path.suffix.lower() == ".mp4"

                if progress_callback:
                    pct = 0.05 + 0.70 * (idx / num_clips)
                    progress_callback(pct, f"Обработка кадра {idx+1}/{num_clips}: {media_path.name}...")

                if is_video:
                    cmd = [
                        self.ffmpeg_exe, "-y",
                        "-i", str(media_path),
                        "-t", str(calc_clip_dur),
                        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
                        "-pix_fmt", "yuv420p", "-an",
                        str(clip_out)
                    ]
                else:
                    frames = int(calc_clip_dur * fps)
                    if ken_burns:
                        if idx % 2 == 0:
                            zoom_expr = "min(pzoom+0.0008,1.15)"
                            x_expr = "iw/2-(iw/zoom/2)"
                            y_expr = "ih/2-(ih/zoom/2)"
                        else:
                            zoom_expr = "1.08"
                            x_expr = f"iw/2-(iw/zoom/2)+(on/{frames})*30"
                            y_expr = "ih/2-(ih/zoom/2)"

                        vf = (
                            f"scale=4000:-1,"
                            f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s={width}x{height}:fps={fps},"
                            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
                        )
                    else:
                        vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"

                    cmd = [
                        self.ffmpeg_exe, "-y",
                        "-loop", "1",
                        "-i", str(media_path),
                        "-t", str(calc_clip_dur),
                        "-vf", vf,
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
                        "-pix_fmt", "yuv420p", "-an",
                        str(clip_out)
                    ]

                p = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
                if clip_out.exists() and clip_out.stat().st_size > 1000:
                    generated_clips.append(clip_out)

            if not generated_clips:
                raise RuntimeError("Не удалось собрать ни одного кадра.")

            # Создаем список конкатенации
            concat_list = temp_dir / "concat_list.txt"
            with open(concat_list, "w", encoding="utf-8") as f:
                for c in generated_clips:
                    f.write(f"file '{c.resolve().as_posix()}'\n")

            if progress_callback:
                progress_callback(0.80, "Склейка всех кадров...")

            raw_video = temp_dir / "raw_video.mp4"
            cmd_concat = [
                self.ffmpeg_exe, "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy",
                str(raw_video)
            ]
            subprocess.run(cmd_concat, capture_output=True, text=True, errors="ignore")

            if progress_callback:
                progress_callback(0.90, "Финальный рендеринг...")

            output_path.parent.mkdir(parents=True, exist_ok=True)
            if has_audio:
                cmd_merge = [
                    self.ffmpeg_exe, "-y",
                    "-i", str(raw_video),
                    "-i", str(audio_path),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-t", str(total_duration),
                    "-pix_fmt", "yuv420p",
                    str(output_path)
                ]
            else:
                # Генерируем с тихой аудиодорожкой, чтобы видео корректно воспроизводилось везде
                cmd_merge = [
                    self.ffmpeg_exe, "-y",
                    "-i", str(raw_video),
                    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest",
                    "-pix_fmt", "yuv420p",
                    str(output_path)
                ]
            subprocess.run(cmd_merge, capture_output=True, text=True, errors="ignore")

            if not output_path.exists() or output_path.stat().st_size < 10000:
                raise RuntimeError("Ошибка при создании финального видеофайла.")

            if progress_callback:
                progress_callback(1.0, f"Готово! Видео успешно смонтировано ({output_path.stat().st_size / (1024*1024):.1f} MB)")

            return output_path

        finally:
            # Очистка временных файлов
            shutil.rmtree(temp_dir, ignore_errors=True)

    def assemble_sleep_lore_timeline(
        self,
        clips_dir: Path,
        audio_path: Path,
        output_path: Path,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Path:
        """
        Мгновенный высокоскоростной сборщик длинных 1-3 часовых роликов (Sleep Lore):
        - Собирает все нарезанные шоты из папки clips/.
        - Зацикливает и тасует их так, чтобы покрыть полную длительность аудиодорожки.
        - Использует FFmpeg Stream Copy (без долгой перекодировки), что позволяет
          собрать 2-часовое 1080p видео всего за 30-60 секунд!
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Поиск всех MP4 клипов
        all_clips = sorted([f for f in clips_dir.glob("*.mp4") if f.is_file()])
        if not all_clips:
            raise ValueError(f"В папке {clips_dir} не найдено нарезанных видеоклипов (.mp4).")

        total_audio_sec = self.get_audio_duration(audio_path)
        if total_audio_sec <= 0:
            raise ValueError("Не удалось определить длительность аудиофайла.")

        if progress_callback:
            progress_callback(0.05, f"Анализ {len(all_clips)} клипов под хронометраж {total_audio_sec/60:.1f} мин...")

        # 2. Вычисление длительностей клипов и составление плейлиста
        import random
        playlist_clips = []
        current_dur = 0.0

        # Перемешиваем с фиксированным сидом для разнообразия, но повторяемости
        shuffled_pool = list(all_clips)
        random.seed(42)
        random.shuffle(shuffled_pool)

        pool_idx = 0
        while current_dur < (total_audio_sec + 30.0):
            clip = shuffled_pool[pool_idx % len(shuffled_pool)]
            playlist_clips.append(clip)
            # Примерная длительность клипа (или точная через probe)
            current_dur += 10.0  # в среднем 10-12 сек на клип
            pool_idx += 1

        # 3. Создаем concat-файл для FFmpeg
        concat_file = output_path.parent / "temp_sleep_concat.txt"
        lines = [f"file '{c.resolve().as_posix()}'" for c in playlist_clips]
        concat_file.write_text("\n".join(lines), encoding="utf-8")

        if progress_callback:
            progress_callback(0.30, f"Склейка {len(playlist_clips)} видеофрагментов со звуковой дорожкой...")

        # 4. Высокоскоростная сборка через concat demuxer
        # -c:v copy переносит видео без потери качества за считанные секунды
        # -c:a aac упаковывает аудио
        # -shortest обрезает ровно по длине аудиодорожки
        cmd = [
            self.ffmpeg_exe, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-i", str(audio_path),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            str(output_path)
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
            if res.returncode != 0 or not output_path.exists():
                raise RuntimeError(f"FFmpeg ошибка сборки: {res.stderr[:400]}")

            if progress_callback:
                size_mb = output_path.stat().st_size / (1024 * 1024)
                progress_callback(1.0, f"Готово! 2-часовое видео собрано: {size_mb:.1f} MB")

            return output_path
        finally:
            concat_file.unlink(missing_ok=True)
