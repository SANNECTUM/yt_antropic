import sys
import subprocess
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich.table import Table

import config
from modules.project_manager import ProjectManager
from modules.script_generator import ScriptGenerator
from modules.prompt_generator import PromptGenerator
from modules.tts_synthesizer import TTSSynthesizer
from modules.pipeline_runner import VideoPipelineRunner

console = Console()

def print_header():
    has_key = bool(config.GEMINI_API_KEY)
    status_key = "[green]✓ Ключ найден в .env[/green]" if has_key else "[red]✗ Ключ GEMINI_API_KEY не задан в .env![/red]"
    console.print(Panel.fit(
        "[bold cyan]🎬 YOUTUBE PRODUCTION ASSISTANT (Powered by Google Gemini)[/bold cyan]\n"
        "[dim]Автоматизация создания YouTube видео: Сценарии удержания • Промпты для Nano Banana • Озвучка TTS[/dim]\n"
        f"Статус Gemini API: {status_key}",
        border_style="cyan"
    ))

def select_project() -> ProjectManager:
    projects = ProjectManager.list_projects()
    console.print("\n[bold yellow]📁 Доступные проекты:[/bold yellow]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", width=4)
    table.add_column("Имя проекта")
    
    table.add_row("0", "[green]+ Создать новый проект[/green]")
    for idx, p in enumerate(projects, 1):
        table.add_row(str(idx), p)
    
    console.print(table)
    choice = IntPrompt.ask("Выберите проект", default=1 if projects else 0)
    
    if choice == 0 or not projects:
        name = Prompt.ask("Введите название нового проекта (например: true_crime_case)")
        return ProjectManager(name)
    else:
        return ProjectManager(projects[choice - 1])

def step_generate_script(pm: ProjectManager):
    console.print(Panel(f"[bold]Генерация сценария в Gemini для: {pm.slug}[/bold]"))
    
    topic = Prompt.ask("Тема ролика / Центральный конфликт", default="Цифровой свидетель: как фитнес-трекер Fitbit разрушил алиби")
    minutes = IntPrompt.ask("Хронометраж (в минутах)", default=15)
    
    current_raw = pm.load_raw_material()
    if current_raw:
        console.print(f"[green]✓ Найдены сохраненные материалы ({len(current_raw)} символов)[/green]")
        use_saved = Prompt.ask("Использовать сохраненные материалы? (y/n)", default="y")
        if use_saved.lower() == "y":
            materials = current_raw
        else:
            materials = Prompt.ask("Вставьте факты/статьи")
    else:
        console.print("[dim]Вставьте исходные факты, заметки или текст статьи:[/dim]")
        materials = Prompt.ask("Материалы")
        pm.save_raw_material(materials)

    with console.status("[bold green]Google Gemini пишет сценарий с актами и хуками...[/bold green]"):
        try:
            gen = ScriptGenerator()
            script_md = gen.generate_script(topic=topic, source_materials=materials, target_minutes=minutes)
            save_path = pm.save_script(script_md)
            console.print(f"[bold green]✓ Сценарий успешно сохранен в:[/bold green] {save_path}")
        except Exception as e:
            console.print(f"[bold red]Ошибка Gemini API:[/bold red] {e}")

def step_generate_prompts(pm: ProjectManager):
    script_text = pm.load_script()
    if not script_text:
        console.print("[bold red]Сценарий не найден! Сначала создайте script.md[/bold red]")
        return

    with console.status("[bold green]Создаю пакет промптов для Nano Banana и Kling...[/bold green]"):
        try:
            pgen = PromptGenerator()
            prompts_md = pgen.generate_prompts(script_text)
            save_path = pm.save_prompts(prompts_md)
            console.print(f"[bold green]✓ Промпты успешно сохранены в:[/bold green] {save_path}")
        except Exception as e:
            console.print(f"[bold red]Ошибка Gemini API:[/bold red] {e}")

def step_generate_images(pm: ProjectManager):
    from modules.image_generator import ImageGenerator
    prompts_md = pm.load_prompts()
    if not prompts_md:
        console.print("[bold red]Файл prompts.md не найден! Сначала сформируйте промпты (пункт 3).[/bold red]")
        return
        
    scenes = ImageGenerator.parse_prompts_from_markdown(prompts_md)
    if not scenes:
        console.print("[bold red]В prompts.md не найдены сцены для генерации.[/bold red]")
        return

    console.print(f"\n[bold cyan]Найдено {len(scenes)} сцен для генерации изображений.[/bold cyan]")
    console.print("1. Сгенерировать все сцены (16:9)")
    console.print("2. Сгенерировать первые 3 сцены (Быстрый тест)")
    choice = IntPrompt.ask("Выберите вариант", default=2)

    scenes_to_run = scenes[:3] if choice == 2 else scenes
    igen = ImageGenerator()
    with console.status(f"[bold green]Генерирую кадры в папку {pm.visuals_dir.name}...[/bold green]"):
        for sc in scenes_to_run:
            out_p = pm.visuals_dir / sc["filename"]
            console.print(f"Генерация: [bold]{sc['title']}[/bold] -> {out_p.name}")
            try:
                igen.generate_single_image(sc["prompt"], out_p)
            except Exception as e:
                console.print(f"[red]Ошибка: {e}[/red]")
    console.print(f"[bold green]✓ Готово! Все изображения сохранены в:[/bold green] {pm.visuals_dir}")

def step_synthesize_tts(pm: ProjectManager):
    script_text = pm.load_script()
    if not script_text:
        console.print("[bold red]Сценарий не найден! Сначала создайте script.md[/bold red]")
        return

    console.print("\n[bold cyan]Выберите голос для озвучки:[/bold cyan]")
    voices = TTSSynthesizer.list_available_russian_voices()
    for idx, v in enumerate(voices, 1):
        console.print(f"{idx}. {v['name']}")
    
    voice_idx = IntPrompt.ask("Голос", default=1)
    selected_voice = voices[voice_idx - 1]["id"]
    
    tts = TTSSynthesizer(voice=selected_voice)
    cleaned = tts.clean_voiceover_text(script_text)
    word_count = len(cleaned.split())
    console.print(f"[dim]Текст подготовлен: {word_count} слов (~{round(word_count / 135, 1)} мин звучания)[/dim]")

    out_file = pm.get_audio_path("voiceover_full.mp3")
    with console.status(f"[bold green]Синтезирую речь в {out_file.name}...[/bold green]"):
        try:
            tts.synthesize_to_file(cleaned, out_file)
            console.print(f"[bold green]✓ Аудиофайл создан:[/bold green] {out_file} ({out_file.stat().st_size // 1024} KB)")
        except Exception as e:
            console.print(f"[bold red]Ошибка озвучки:[/bold red] {e}")

def step_run_pipeline(pm: ProjectManager):
    console.print(Panel(f"[bold cyan]🚀 Авто-конвейер видео под ключ: {pm.slug}[/bold cyan]"))
    
    topic = Prompt.ask("Тема ролика / Центральный конфликт", default="Тайны и загадки Вселенной: что скрывает темная материя")
    genre = Prompt.ask("Жанр", default="Наука, космос и будущее (в стиле Kurzgesagt / Veritasium)")
    minutes = IntPrompt.ask("Хронометраж (в минутах)", default=3)
    
    current_raw = pm.load_raw_material()
    materials = current_raw or ""
    if not materials:
        ask_mat = Prompt.ask("Есть исходный текст или статья? (y/n)", default="n")
        if ask_mat.lower() == "y":
            materials = Prompt.ask("Вставьте материалы")
            pm.save_raw_material(materials)
            
    with_tts = Prompt.ask("Включить автоматическую озвучку диктором? (y/n)", choices=["y", "n"], default="n")
    include_tts = with_tts.lower() == "y"
    
    tts_engine = "edge"
    tts_voice = "ru-RU-DmitryNeural"
    if include_tts:
        engine_choice = Prompt.ask("Движок озвучки: (1) Edge-TTS безлимитно, (2) Google AI Studio", choices=["1", "2"], default="1")
        tts_engine = "edge" if engine_choice == "1" else "gemini"
        tts_voice = "ru-RU-DmitryNeural" if tts_engine == "edge" else "Milo"
    
    scene_cnt = IntPrompt.ask("Количество кадров (16:9)", default=6)
    
    runner = VideoPipelineRunner(pm)
    with console.status("[bold green]Работает авто-конвейер...[/bold green]") as status:
        def on_prog(pct: float, msg: str):
            status.update(f"[bold green][{int(pct*100)}%] {msg}[/bold green]")
            
        try:
            res = runner.run_full_pipeline(
                topic=topic,
                source_materials=materials,
                genre=genre,
                target_minutes=minutes,
                include_tts=include_tts,
                tts_engine=tts_engine,
                tts_voice=tts_voice,
                num_visual_scenes=scene_cnt,
                progress_callback=on_prog
            )
            console.print(Panel.fit(
                f"[bold green]🎉 Видео успешно создано за {res['elapsed_seconds']} сек![/bold green]\n\n"
                f"🎬 Видеофайл: [cyan]{res['video_path']}[/cyan] ({res['video_size_mb']} MB)\n"
                f"🖼️ Обложка: [cyan]{res['thumbnail_path']}[/cyan]\n"
                f"🎙️ Озвучка: [cyan]{res['audio_path']}[/cyan] ({int(res['audio_duration'])} сек)\n"
                f"🎯 Топ-заголовок: [yellow]{res['top_title']}[/yellow]",
                title="Релиз готов",
                border_style="green"
            ))
        except Exception as e:
            console.print(f"[bold red]Ошибка конвейера:[/bold red] {e}")

def run_web_ui():
    console.print("[bold green]Запускаю Streamlit Web UI в браузере...[/bold green]")
    cmd = [sys.executable, "-m", "streamlit", "run", "web_ui.py"]
    subprocess.run(cmd)

def main():
    print_header()
    while True:
        console.print("\n[bold]ГЛАВНОЕ МЕНЮ:[/bold]")
        console.print("1. 🎬 Выбрать / Создать проект")
        console.print("2. 📝 Сгенерировать сценарий (Gemini)")
        console.print("3. 🎨 Сформировать промпты для Nano Banana & Kling")
        console.print("4. 🖼️ Сгенерировать изображения по промптам (16:9)")
        console.print("5. 🎙️ Озвучить сценарий (TTS в MP3)")
        console.print("6. 🚀 Запустить сквозной авто-конвейер видео (One-Click Pipeline)")
        console.print("7. 🌐 Открыть Web UI в браузере")
        console.print("0. ❌ Выход")

        choice = Prompt.ask("Действие", choices=["1", "2", "3", "4", "5", "6", "7", "0"], default="6")
        if choice == "0":
            console.print("[dim]До встречи![/dim]")
            break
        elif choice == "7":
            run_web_ui()
            break
        else:
            pm = select_project()
            if choice == "2":
                step_generate_script(pm)
            elif choice == "3":
                step_generate_prompts(pm)
            elif choice == "4":
                step_generate_images(pm)
            elif choice == "5":
                step_synthesize_tts(pm)
            elif choice == "6":
                step_run_pipeline(pm)

if __name__ == "__main__":
    main()
