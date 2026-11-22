import streamlit as st
import os
import asyncio
import re
import math
from pathlib import Path
from typing import List, Dict, Any, Optional
import config
import importlib
import modules.project_manager
importlib.reload(modules.project_manager)
from modules.project_manager import ProjectManager
from modules.script_generator import ScriptGenerator
import modules.prompt_generator
importlib.reload(modules.prompt_generator)
from modules.prompt_generator import PromptGenerator
import modules.image_generator
importlib.reload(modules.image_generator)
from modules.image_generator import ImageGenerator
import modules.tts_synthesizer
importlib.reload(modules.tts_synthesizer)
from modules.tts_synthesizer import TTSSynthesizer
from modules.web_image_search import WebImageSearcher
import modules.video_editor
importlib.reload(modules.video_editor)
from modules.video_editor import VideoEditor
from modules.packaging_generator import PackagingGenerator
from modules.article_parser import ArticleParser
import modules.pipeline_runner
importlib.reload(modules.pipeline_runner)
from modules.pipeline_runner import VideoPipelineRunner
import modules.scene_parser
importlib.reload(modules.scene_parser)
from modules.scene_parser import (
    SceneParser, SceneBlock, save_scenes, load_scenes,
    build_ai_image_prompt, craft_smart_ai_prompt,
    SD_STYLE_PRESETS, DEFAULT_STYLE_NAME
)
import modules.timeline_builder
importlib.reload(modules.timeline_builder)
from modules.timeline_builder import TimelineBuilder
import modules.fooocus_client
importlib.reload(modules.fooocus_client)
from modules.fooocus_client import FooocusClient
import modules.pexels_downloader
importlib.reload(modules.pexels_downloader)
from modules.pexels_downloader import PexelsDownloader, detect_local_proxy
from modules.thumbnail_generator import create_thumbnail_style_1, create_thumbnail_style_2_collage, create_thumbnail_style_3
import modules.audio_aligner
importlib.reload(modules.audio_aligner)
from modules.audio_aligner import AudioSceneAligner, get_audio_duration, format_duration

st.set_page_config(
    page_title="YouTube Studio Assistant (Gemini)",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🎬 YouTube Production Assistant")
st.caption("Генератор сценариев удержания (Google Gemini) • Промпты для Nano Banana / Kling • Студийная озвучка (TTS) • Упаковка (CTR & Обложки)")

# Боковая панель: выбор проекта и настройки
with st.sidebar:
    st.header("📁 Проекты")
    projects = ProjectManager.list_projects()
    
    project_mode = st.radio("Действие", ["Выбрать существующий", "Создать новый"], index=0 if projects else 1)
    
    if project_mode == "Создать новый" or not projects:
        new_project_name = st.text_input("Название нового проекта", placeholder="например, cold_cases_alibi")
        if st.button("Создать проект", width="stretch") and new_project_name.strip():
            pm = ProjectManager(new_project_name.strip())
            st.success(f"Проект {pm.slug} создан!")
            st.rerun()
        current_project = new_project_name.strip() if new_project_name.strip() else (projects[0] if projects else "default")
        pm = ProjectManager(current_project)
    else:
        selected_slug = st.selectbox("Текущий проект", projects, index=0)
        pm = ProjectManager(selected_slug)
        st.info(f"Папка проекта: `{pm.project_dir.name}`")

    st.divider()
    st.header("⚡ Google Gemini API")
    current_key = config.get_gemini_api_key()
    if current_key:
        config.GEMINI_API_KEY = current_key
        os.environ["GEMINI_API_KEY"] = current_key

    has_key = bool(config.GEMINI_API_KEY)
    if has_key:
        st.success("🟢 API ключ активен")
    else:
        st.error("🔴 GEMINI_API_KEY не найден")
        st.caption("Введите ключ ниже или укажите в Secrets на Streamlit Cloud:")

    key_input = st.text_input(
        "🔑 Gemini API Ключ:",
        value=config.GEMINI_API_KEY or st.session_state.get("user_gemini_key", ""),
        type="password",
        placeholder="AIzaSy...",
        key="gemini_key_input_sidebar",
        help="Ключ можно ввести прямо здесь — он сохранится для вашей сессии"
    )
    if key_input and key_input.strip() != config.GEMINI_API_KEY:
        config.GEMINI_API_KEY = key_input.strip()
        os.environ["GEMINI_API_KEY"] = key_input.strip()
        st.session_state["user_gemini_key"] = key_input.strip()
        st.rerun()
        
    available_models = [
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.8-flash",
        "✏️ Другая модель (ввести вручную)"
    ]
    selected_option = st.selectbox(
        "Модель Gemini", 
        available_models, 
        index=0,
        help="gemini-3.5-flash-lite — новейшая супер-быстрая модель Google (ответ за 1-2 сек). При необходимости система автоматически использует резервные модели."
    )
    if selected_option == "✏️ Другая модель (ввести вручную)":
        model_name = st.text_input("Введите точное имя модели", value="gemini-3.5-flash-lite")
    else:
        model_name = selected_option

tab_autopilot, tab_stepwise, tab_script, tab_prompts, tab_tts, tab_thumbnails, tab_files = st.tabs([
    "🚀 0. Автопилот (1 клик)",
    "🎬 Пошаговый монтаж",
    "📝 1. Сценарий", 
    "🍌 2. Промпты и Визуал", 
    "🎙️ 3. Озвучка (TTS)", 
    "🖼️ 4. Обложки (3 Стиля)",
    "📂 5. Файлы проекта"
])

# Вкладка 0: Автопилот (Видео под ключ)
with tab_autopilot:
    st.subheader("🚀 0. Сквозной Автопилот: создание готового видео в 1 клик")
    st.caption("Автоматический конвейер полного цикла: Тема ➔ Сценарий (Gemini) ➔ Озвучка (TTS) ➔ Генерация кадров 16:9 ➔ Монтаж 1080p Ken Burns ➔ Обложка и SEO-описание")

    project_meta = pm.load_meta()
    saved_topic = project_meta.get("topic", "")
    saved_genre = project_meta.get("genre", "Детективное расследование / True Crime")
    saved_minutes = project_meta.get("minutes", 5)

    c_ap1, c_ap2 = st.columns([2, 1])
    with c_ap1:
        auto_topic = st.text_input("Тема ролика / Центральный конфликт:", value=saved_topic, placeholder="например: Тайна исчезновения рейса MH370, Крах империи Enron, Как создавался iPhone...", key="auto_topic_input")
        auto_materials = st.text_area("Исходные факты / текст статьи (опционально):", value=pm.load_raw_material() or "", height=140, placeholder="Вставьте сюда текст статьи, заметки или факты. Если поле пустое, Gemini соберет всю фактуру самостоятельно по теме.", key="auto_mat_input")
    with c_ap2:
        genre_list = [
            "Детективное расследование / True Crime",
            "Бизнес, деньги и крах корпораций (в стиле Magnates Media)",
            "Наука, космос и будущее (в стиле Kurzgesagt / Veritasium)",
            "Историческая документалистика (в стиле Lemmino)",
            "Технологии и ИИ",
            "Психология и общество (в стиле JCS)"
        ]
        g_def_idx = genre_list.index(saved_genre) if saved_genre in genre_list else 0
        auto_genre = st.selectbox("Жанр ролика:", genre_list, index=g_def_idx, key="auto_genre_sel")
        auto_minutes = st.select_slider("Хронометраж ролика (мин):", options=[3, 5, 8, 10, 15], value=min(5, saved_minutes), key="auto_min_slider", help="3-5 минут идеально для быстрого теста и динамичного контента (собирается за 1-2 минуты). 10-15 минут — для длинных глубоких документалок.")

    with st.expander("⚙️ Настройки конвейера и визуала", expanded=False):
        c_tts_flag, c_sc = st.columns([1.5, 1])
        with c_tts_flag:
            auto_include_tts = st.checkbox(
                "🎙️ Включить озвучку диктором (TTS) в конвейер",
                value=False,
                key="auto_include_tts_check",
                help="По умолчанию озвучка ОТКЛЮЧЕНА для мгновенной генерации (~20-30 сек). Включите, если хотите сразу синтезировать начитку диктора."
            )
            if auto_include_tts:
                c_eng, c_vc = st.columns(2)
                with c_eng:
                    pipeline_engine = st.radio("Движок:", ["⚡ Edge TTS", "🌟 Google AI Studio"], index=0, key="auto_eng_rad")
                with c_vc:
                    if "Edge" in pipeline_engine:
                        pipeline_voice = st.selectbox("Голос:", ["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"], index=0, key="auto_edge_v")
                        voice_id = "ru-RU-DmitryNeural" if "Dmitry" in pipeline_voice else "ru-RU-SvetlanaNeural"
                        engine_code = "edge"
                    else:
                        pipeline_voice = st.selectbox("Голос Gemini:", ["Milo (Podcast)", "Nika (Podcast)", "Charon", "Fenrir"], index=0, key="auto_gem_v")
                        voice_id = pipeline_voice.split()[0]
                        engine_code = "gemini"
            else:
                engine_code = "edge"
                voice_id = "ru-RU-DmitryNeural"
                st.caption("⚡ Режим турбо-сборки: сценарий + раскадровка 16:9 + монтаж 1080p Ken Burns + обложка и SEO за ~20-30 секунд.")

        with c_sc:
            auto_scene_count = st.slider("Количество кадров (16:9):", min_value=4, max_value=16, value=6, key="auto_sc_slider", help="Сколько иллюстраций сгенерировать. Кадры равномерно распределятся по хронометражу с кинематографичным зумом.")

    btn_run_autopilot = st.button("🚀 ЗАПУСТИТЬ АВТО-КОНВЕЙЕР ВИДЕО", type="primary", use_container_width=True, key="btn_run_autopilot")

    if btn_run_autopilot:
        if not auto_topic.strip() and not auto_materials.strip():
            st.error("Пожалуйста, укажите хотя бы тему ролика или вставьте материалы.")
        else:
            progress_bar = st.progress(0, text="Инициализация конвейера...")
            status_box = st.empty()

            def on_pipe_progress(pct: float, msg: str):
                progress_bar.progress(int(pct * 100), text=f"Прогресс конвейера: {int(pct * 100)}%")
                status_box.info(f"⚙️ {msg}")

            try:
                runner = VideoPipelineRunner(pm, model_name=model_name)
                res = runner.run_full_pipeline(
                    topic=auto_topic.strip(),
                    source_materials=auto_materials.strip(),
                    genre=auto_genre,
                    target_minutes=int(auto_minutes),
                    include_tts=auto_include_tts,
                    tts_engine=engine_code,
                    tts_voice=voice_id,
                    num_visual_scenes=int(auto_scene_count),
                    progress_callback=on_pipe_progress
                )
                progress_bar.progress(100, text="✅ Видеокомплект успешно создан!")
                status_box.empty()
                st.balloons()
                st.success(f"🎉 Конвейер успешно завершен за {res['elapsed_seconds']} сек! Ролик {res['video_size_mb']} MB готов к публикации.")
                st.rerun()
            except Exception as pipe_err:
                status_box.empty()
                st.error(f"Ошибка в работе конвейера: {pipe_err}")

    # Блок готового релиза
    final_video = pm.project_dir / "final_video.mp4"
    final_thumb = pm.project_dir / "thumbnail.jpg"
    try:
        final_titles = pm.load_titles() if hasattr(pm, "load_titles") else ""
        final_desc = pm.load_description() if hasattr(pm, "load_description") else ""
    except Exception:
        final_titles = ""
        final_desc = ""

    if final_video.exists() and final_video.stat().st_size > 10000:
        st.divider()
        st.subheader("📦 Готовый релизный комплект проекта:")
        
        c_res_v, c_res_t = st.columns([1.5, 1])
        with c_res_v:
            st.markdown("#### 🎬 Готовое смонтированное видео (1080p)")
            st.video(str(final_video))
            with open(final_video, "rb") as vf:
                st.download_button(
                    "⬇️ Скачать готовое видео (MP4)",
                    data=vf.read(),
                    file_name=f"{pm.slug}_final.mp4",
                    mime="video/mp4",
                    type="primary",
                    use_container_width=True,
                    key="dl_auto_video"
                )

        with c_res_t:
            st.markdown("#### 🖼️ Финальная обложка (YouTube Thumbnail)")
            if final_thumb.exists():
                st.image(str(final_thumb), use_container_width=True)
                with open(final_thumb, "rb") as tf:
                    st.download_button(
                        "⬇️ Скачать обложку (JPG)",
                        data=tf.read(),
                        file_name=f"{pm.slug}_thumb.jpg",
                        mime="image/jpeg",
                        use_container_width=True,
                        key="dl_auto_thumb"
                    )

        if final_titles or final_desc:
            st.markdown("#### 🎯 Заголовки (CTR) и SEO-описание")
            c_seo1, c_seo2 = st.columns(2)
            with c_seo1:
                st.text_area("Варианты названий ролика:", value=final_titles or "", height=160, key="auto_titles_area")
            with c_seo2:
                st.text_area("Описание с таймкодами для YouTube:", value=final_desc or "", height=160, key="auto_desc_area")

    st.divider()

# ===================================================================
# Вкладка: Пошаговый монтаж (3 шага)
# ===================================================================
with tab_stepwise:
    st.subheader("🎬 Пошаговый монтаж: Сценарий → Кадры → Озвучка")
    st.caption("Контролируемый конвейер: каждый шаг проверяется и утверждается вами перед следующим.")

    # Инициализируем TimelineBuilder
    tl_builder = TimelineBuilder(pm.project_dir)

    # ---- Прогресс шагов ----
    step1_done = (pm.project_dir / "scenes.json").exists()
    step2_done = (pm.project_dir / "render" / "videotrack.mp4").exists()
    step3_done = (pm.project_dir / "final_video.mp4").exists()

    col_s1, col_s2, col_s3 = st.columns(3)
    col_s1.metric("Шаг 1: Сцены", "✅ Готово" if step1_done else "⏳ Нужно выполнить")
    col_s2.metric("Шаг 2: Монтаж", "✅ Готово" if step2_done else "⏳ Нужно выполнить")
    col_s3.metric("Шаг 3: Озвучка", "✅ Готово" if step3_done else "⏳ Нужно выполнить")

    # Быстрый блок скачивания готового видео в самом верху (если видео уже смонтировано)
    final_v_top = pm.project_dir / "final_video.mp4"
    if final_v_top.exists() and final_v_top.stat().st_size > 10000:
        with st.container(border=True):
            col_fvt1, col_fvt2 = st.columns([2, 1.2])
            with col_fvt1:
                st.markdown("### 🎉 Готовое видео доступно для скачивания!")
                st.caption(f"Файл: `{pm.slug}_final.mp4` • Хронометраж: {format_duration(get_audio_duration(final_v_top))} • Размер: {final_v_top.stat().st_size // (1024*1024)} MB")
            with col_fvt2:
                with open(final_v_top, "rb") as f_top:
                    st.download_button(
                        "📥 СКАЧАТЬ ГОТОВОЕ ВИДЕО (MP4)",
                        data=f_top.read(),
                        file_name=f"{pm.slug}_final.mp4",
                        mime="video/mp4",
                        type="primary",
                        use_container_width=True,
                        key="sw_dl_final_top_banner"
                    )

    st.divider()

    # ================================================================
    # ШАГ 1: Сценарий → Сцены
    # ================================================================
    with st.expander("📝 Шаг 1: Сценарий → Нарезка на сцены", expanded=not step1_done):
        script_for_scenes = pm.load_script()
        if not script_for_scenes.strip():
            st.warning("Сначала напишите сценарий во вкладке **📝 1. Сценарий** — он появится здесь автоматически.")
        else:
            st.info(f"Сценарий найден: **{len(script_for_scenes.split())} слов**.")
            topic_for_scenes = pm.load_meta().get("topic", "")

            # ============================================================
            # 🎙️ РЕЖИМ 1: AUDIO-FIRST (РАСКАДРОВКА ПОД ГОТОВУЮ ОЗВУЧКУ)
            # ============================================================
            with st.container(border=True):
                st.markdown("### 🎙️ Режим 1: Раскадровка под готовую озвучку (Audio-First)")
                st.caption(
                    "Загрузите готовый MP3/WAV файл из **Google AI Studio** — система точно измерит хронометраж диктора "
                    "и сформирует кадры так, чтобы **видеоряд секунда-в-секунду совпадал с речью диктора без рассинхрона!**"
                )

                # Поиск имеющихся аудиофайлов в проекте
                available_audio_files = []
                for ext in ("*.mp3", "*.wav", "*.m4a", "*.ogg"):
                    available_audio_files.extend(list(pm.audio_dir.glob(ext)))
                    available_audio_files.extend(list(pm.project_dir.glob(ext)))
                # Убираем дубликаты
                available_audio_files = list({f.resolve(): f for f in available_audio_files}.values())

                c_af_up, c_af_pick = st.columns([1.5, 1])
                with c_af_up:
                    af_uploaded = st.file_uploader(
                        "📥 Загрузить MP3/WAV озвучку из Google AI Studio:",
                        type=["mp3", "wav", "m4a", "ogg"],
                        key="af_file_uploader_step1"
                    )
                    if af_uploaded:
                        saved_af = pm.audio_dir / af_uploaded.name
                        saved_af.write_bytes(af_uploaded.getvalue())
                        st.success(f"Файл `{saved_af.name}` сохранён в проект!")
                        if saved_af not in available_audio_files:
                            available_audio_files.insert(0, saved_af)

                selected_af_path = None
                with c_af_pick:
                    if available_audio_files:
                        af_names = [f.name for f in available_audio_files]
                        chosen_af_name = st.selectbox(
                            "Выбрать активную озвучку:",
                            af_names,
                            index=0,
                            key="af_chosen_audio_select"
                        )
                        selected_af_path = available_audio_files[af_names.index(chosen_af_name)]
                    else:
                        st.info("В проекте пока нет аудиофайлов. Перетащите файл слева.")

                if selected_af_path and selected_af_path.exists():
                    af_dur = get_audio_duration(selected_af_path)
                    st.success(f"⏱️ **Точная длительность озвучки:** `{format_duration(af_dur)}` ({af_dur:.1f} сек)")

                    c_af_cfg1, c_af_cfg2 = st.columns([1.2, 1])
                    with c_af_cfg1:
                        af_target_sec = st.slider(
                            "Желаемая длительность одного кадра:",
                            min_value=10,
                            max_value=35,
                            value=18,
                            step=1,
                            format="%d сек",
                            key="af_target_sec_slider",
                            help="Каждые 15-20 секунд видеоряд будет сменяться под тему речи диктора"
                        )
                        af_calc_scenes = max(1, round(af_dur / af_target_sec))
                        st.caption(f"Будет создано ровно **{af_calc_scenes} кадров** под хронометраж `{format_duration(af_dur)}`")

                    with c_af_cfg2:
                        af_use_gemini = st.checkbox(
                            "✨ Точные B-Roll теги под каждую реплику (Gemini)",
                            value=True,
                            key="af_use_gemini_chk",
                            help="Gemini сопоставит текст каждой реплики с точным английским B-roll запросом для Pexels"
                        )

                    if st.button("🎯 СФОРМИРОВАТЬ РАСКАДРОВКУ С ТОЧНЫМИ ТАЙМКОДАМИ (100% СОВПАДЕНИЕ ЗВУКА И ВИДЕО)", type="primary", use_container_width=True, key="btn_run_audio_align"):
                        p_bar_af = st.progress(0, text="Инициализация выравнивания сценария под аудио...")
                        status_af = st.empty()

                        def on_af_prog(pct, msg):
                            p_bar_af.progress(int(pct * 100), text=msg)
                            status_af.info(f"⚙️ {msg}")

                        try:
                            aligned_scenes = AudioSceneAligner.align_script_to_audio(
                                script_text=script_for_scenes,
                                audio_path=selected_af_path,
                                target_scene_duration=float(af_target_sec),
                                use_gemini=af_use_gemini,
                                style_context=topic_for_scenes,
                                progress_callback=on_af_prog
                            )
                            AudioSceneAligner.apply_alignment_to_project(pm.project_dir, aligned_scenes, selected_af_path)
                            status_af.empty()
                            p_bar_af.progress(100, text="✅ Раскадровка успешно создана!")
                            st.balloons()
                            st.success(f"🎉 Готово! Создано **{len(aligned_scenes)} сцен**. Суммарный хронометраж видеоряда строго равен звуку: **{format_duration(af_dur)}**.")
                            st.rerun()
                        except Exception as afe:
                            st.error(f"Ошибка при синхронизации: {afe}")

            # ============================================================
            # РЕЖИМ 2: КЛАССИЧЕСКАЯ НАРЕЗКА (БЕЗ ГОТОВОЙ ОЗВУЧКИ)
            # ============================================================
            with st.expander("⚙️ Режим 2: Альтернативная нарезка (без готового аудиофайла)", expanded=False):
                col_sp1, col_sp2 = st.columns([2, 1])
                with col_sp1:
                    parse_strategy_label = st.radio(
                        "Стратегия нарезки текста:",
                        [
                            "⏱️ Каждые 30 секунд (для стоковых видео Pexels)",
                            "📑 По главам / актам сценария (авто)",
                            "📄 По объему текста (слов на сцену)"
                        ],
                        index=0,
                        key="sw_strat_choice"
                    )
                with col_sp2:
                    if "30 секунд" in parse_strategy_label:
                        step_sec_sw = st.selectbox("Интервал смены видео:", [30, 15, 20, 45, 60], index=0, format_func=lambda x: f"{x} сек")
                        words_per_scene_sw = 200
                    elif "объему" in parse_strategy_label:
                        words_per_scene_sw = st.number_input("Слов/сцена (абзацное деление)", 100, 500, 200, 50, key="sw_wps")
                        step_sec_sw = 30
                    else:
                        words_per_scene_sw = 200
                        step_sec_sw = 30

                col_parse_act1, col_parse_act2 = st.columns([1, 1])
                with col_parse_act1:
                    btn_parse = st.button("✂️ Нарезать сценарий (по времени текста)", type="secondary", key="sw_btn_parse", use_container_width=True)
                with col_parse_act2:
                    has_prompts_file = (pm.project_dir / "prompts.md").exists()
                    btn_sync_from_tab2 = st.button(
                        "🔄 Загрузить кадры из Раздела 2 (Промпты и Визуал)",
                        disabled=not has_prompts_file,
                        help="Импортирует готовые 30-секундные кадры с подробными художественными описаниями из prompts.md",
                        use_container_width=True,
                        key="sw_sync_prompts_btn"
                    )

                if btn_parse:
                    parser = SceneParser(topic=topic_for_scenes)
                    if "30 секунд" in parse_strategy_label:
                        scenes_parsed = parser.parse(script_for_scenes, strategy="time_slices", interval_seconds=step_sec_sw)
                    elif "объему" in parse_strategy_label:
                        scenes_parsed = parser.parse(script_for_scenes, strategy="paragraphs", words_per_scene=words_per_scene_sw)
                    else:
                        scenes_parsed = parser.parse(script_for_scenes, strategy="auto")
                    save_scenes(scenes_parsed, pm.project_dir)
                    tl_builder.save_timeline(scenes_parsed)
                    st.success(f"✅ Нарезано **{len(scenes_parsed)} сцен**! Переходите к Шагу 2.")
                    st.rerun()

                if btn_sync_from_tab2:
                    with st.spinner("Загрузка раскадровки и художественных промптов из Раздела 2..."):
                        synced_scenes = PexelsDownloader.sync_prompts_to_timeline(pm.project_dir)
                        if synced_scenes:
                            st.success(f"✅ Успешно загружено **{len(synced_scenes)} кадров** с подробными описаниями из Раздела 2!")
                            st.rerun()
                        else:
                            st.error("Не удалось прочитать кадры из prompts.md. Убедитесь, что раскадровка создана в Разделе 2.")

            # Превью уже нарезанных сцен
            if step1_done:
                scenes_sw = load_scenes(pm.project_dir)
                st.markdown(f"**Текущая нарезка: {len(scenes_sw)} сцен** (суммарно ~{sum(s.duration for s in scenes_sw)/60:.1f} мин)")
                with st.expander(f"📋 Показать список всех {len(scenes_sw)} сцен", expanded=False):
                    for s in scenes_sw:
                        with st.container(border=True):
                            c1, c2 = st.columns([1, 4])
                            c1.markdown(f"**#{s.index}**  \n`{s.effective_duration:.0f} сек`")
                            c2.markdown(f"**{s.title}**  \n{s.text[:120]}{'...' if len(s.text) > 120 else ''}")

    st.divider()

    # ================================================================
    # ШАГ 2: Покадровый монтаж
    # ================================================================
    with st.expander("🖼️ Шаг 2: Покадровый монтаж (подбор кадров + эффекты)", expanded=step1_done and not step2_done):
        if not step1_done:
            st.warning("Сначала выполните Шаг 1: нарежьте сценарий на сцены.")
        else:
            scenes_sw = tl_builder.load_timeline()
            searcher_sw = WebImageSearcher()
            ig_sw = ImageGenerator()

            st.caption(f"Настройте каждую сцену: подберите кадр и выберите эффект. Суммарный хронометраж: **{TimelineBuilder.total_duration(scenes_sw)/60:.1f} мин**.")

            EFFECTS_MAP = {
                "🎥 Ken Burns: наезд (Zoom In)": "ken_burns_in",
                "🎥 Ken Burns: отъезд (Zoom Out)": "ken_burns_out",
                "🎥 Панорама влево": "pan_left",
                "🎥 Панорама вправо": "pan_right",
                "✨ Плавное появление (Fade)": "fade",
                "◀️ Слайд слева": "slide_left",
                "▶️ Слайд справа": "slide_right",
                "— Без эффекта": "none",
            }
            EFFECT_LABELS = {v: k for k, v in EFFECTS_MAP.items()}

            # ========================================================
            # 🎬 ПАКЕТНЫЙ АВТОПОДБОР И СКАЧИВАНИЕ B-ROLL С PEXELS
            # ========================================================
            with st.container(border=True):
                st.markdown("### 🎬 Пакетное скачивание стоковых Full HD видео (Pexels)")
                st.caption("Автоматически подбирает кинематографичные горизонтальные 16:9 видеоролики (MP4) под каждую сцену без официального API-ключа.")

                detected_px = detect_local_proxy()
                px_status_col1, px_status_col2, px_status_col3 = st.columns([2, 1.2, 1])
                with px_status_col1:
                    custom_proxy_val = st.text_input(
                        "Прокси для Pexels (если в РФ):",
                        value=st.session_state.get("pexels_proxy_input", detected_px or ""),
                        placeholder="например: socks5://127.0.0.1:10808 или оставьте пустым при включенном VPN",
                        key="px_proxy_field"
                    )
                    st.session_state["pexels_proxy_input"] = custom_proxy_val
                with px_status_col2:
                    st.write("")
                    st.write("")
                    if st.button("🔌 Проверить связь с Pexels", key="btn_test_pexels"):
                        with st.spinner("Проверка соединения с Pexels..."):
                            tester = PexelsDownloader(proxy=custom_proxy_val or None)
                            test_vids = tester.search_videos("dark street", limit=1)
                            if test_vids:
                                st.session_state["pexels_conn_ok"] = True
                                st.success("🟢 Pexels на связи!")
                            else:
                                st.session_state["pexels_conn_ok"] = False
                                st.warning("⚠️ Pexels не ответил. Проверьте VPN/прокси.")
                with px_status_col3:
                    st.write("")
                    st.write("")
                    is_ok = st.session_state.get("pexels_conn_ok")
                    if is_ok is True:
                        st.info("Статус: **🟢 Доступен**")
                    elif is_ok is False:
                        st.error("Статус: **🔴 Нет связи**")
                    else:
                        st.caption("Нажмите 'Проверить' для теста")

                col_px_act1, col_px_act2, col_px_act3 = st.columns([1, 1, 1.4])
                with col_px_act1:
                    if st.button(f"✨ 1. B-Roll теги для {len(scenes_sw)} сцен", use_container_width=True, key="btn_gen_px_tags"):
                        with st.spinner(f"Gemini анализирует {len(scenes_sw)} сцен и формулирует английские B-Roll теги..."):
                            try:
                                queries = PexelsDownloader.generate_broll_queries(
                                    [s.text for s in scenes_sw],
                                    style_context=pm.load_meta().get("topic", "")
                                )
                                for i, s in enumerate(scenes_sw):
                                    if i < len(queries):
                                        s.search_query = queries[i]
                                tl_builder.save_timeline(scenes_sw)
                                save_scenes(scenes_sw, pm.project_dir)
                                st.success(f"✅ Готово! Сформировано {len(queries)} тегов для Pexels.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Ошибка генерации тегов: {e}")

                with col_px_act2:
                    btn_batch_search_candidates = st.button(
                        f"🔍 2. Пред-поиск вариантов (без скачивания)",
                        help="Автоматически находит по 3-4 видео для каждой сцены в фоне. Вам останется только выбрать подходящее в карточках!",
                        use_container_width=True,
                        key="btn_batch_search_cand"
                    )

                with col_px_act3:
                    download_all_btn = st.button(
                        f"🚀 3. АВТОПИЛОТ: СКАЧАТЬ ПЕРВОЕ ВИДЕО ДЛЯ ВСЕХ СЦЕН",
                        type="primary",
                        help="Полный автомат: ищет видео для каждой сцены, сразу скачивает первый (лучший) ролик в 1080p и монтирует в проект!",
                        use_container_width=True,
                        key="btn_download_all_px"
                    )

                overwrite_existing = st.checkbox("Перезаписывать уже найденное/скачанное", value=False, key="px_overwrite")

                if btn_batch_search_candidates:
                    px_downloader = PexelsDownloader(proxy=custom_proxy_val or None)
                    p_bar_cand = st.progress(0, text="Пакетный поиск вариантов видео на Pexels...")
                    def on_cand_prog(pct: int, msg: str):
                        p_bar_cand.progress(pct, text=msg)
                    px_downloader.batch_search_candidates(
                        scenes_sw,
                        pm.project_dir,
                        limit_per_scene=3,
                        overwrite=overwrite_existing,
                        progress_callback=on_cand_prog
                    )
                    st.success(f"🎉 Варианты найдены для всех сцен! Они уже отображаются в карточках ниже — просто выбирайте нужное видео.")
                    st.rerun()

                if download_all_btn:
                    px_downloader = PexelsDownloader(proxy=custom_proxy_val or None)
                    p_bar = st.progress(0, text="Запуск автопилота Pexels...")

                    # Автоматически генерируем теги из художественных описаний, если они еще не созданы
                    need_tags = any(not s.search_query.strip() or s.search_query.strip() == "cinematic documentary" for s in scenes_sw)
                    if need_tags:
                        p_bar.progress(5, text="Генерация точных B-roll тегов из художественных описаний через Gemini...")
                        queries = PexelsDownloader.generate_broll_queries(
                            [s.text for s in scenes_sw],
                            style_context=pm.load_meta().get("topic", "")
                        )
                        for i, s in enumerate(scenes_sw):
                            if i < len(queries):
                                s.search_query = queries[i]
                        tl_builder.save_timeline(scenes_sw)
                        save_scenes(scenes_sw, pm.project_dir)

                    success_count = 0
                    total_sc = len(scenes_sw)
                    all_cached_cand = PexelsDownloader.load_cached_candidates(pm.project_dir)

                    for idx, s in enumerate(scenes_sw):
                        dest_file = pm.visuals_dir / f"scene_{s.index:03d}.mp4"
                        if dest_file.exists() and not overwrite_existing:
                            s.visual_path = str(dest_file)
                            success_count += 1
                            p_bar.progress(int((idx + 1) / total_sc * 100), text=f"Сцена {s.index}/{total_sc}: видео уже есть ({dest_file.name})")
                            continue

                        q = s.search_query.strip() or "cinematic documentary"
                        p_bar.progress(int((idx + 1) / total_sc * 100), text=f"Сцена {s.index}/{total_sc}: автопоиск Pexels: '{q}'...")

                        vids = px_downloader.search_videos(q, limit=3)
                        if not vids:
                            simple_q = " ".join(q.split()[:2])
                            if simple_q != q:
                                vids = px_downloader.search_videos(simple_q, limit=2)

                        if vids:
                            all_cached_cand[str(s.index)] = vids
                            top_vid = vids[0]  # Сразу берем первое в списке!
                            p_bar.progress(int((idx + 1) / total_sc * 100), text=f"Сцена {s.index}/{total_sc}: скачивание первого видео (1080p MP4)...")
                            ok = px_downloader.download_video_file(top_vid["download_url"], dest_file)
                            if ok:
                                s.visual_path = str(dest_file)
                                success_count += 1
                        else:
                            import logging
                            logging.warning(f"Не найдено видео на Pexels для сцены {s.index} ('{q}')")

                    PexelsDownloader.save_cached_candidates(pm.project_dir, all_cached_cand)
                    tl_builder.save_timeline(scenes_sw)
                    save_scenes(scenes_sw, pm.project_dir)
                    p_bar.progress(100, text=f"✅ Готово! Первое видео скачано для {success_count} из {total_sc} сцен.")
                    st.success(f"🎉 Автопилот завершён! Первое видео успешно скачано и привязано для **{success_count} / {total_sc} сцен**.")
                    st.rerun()

            scenes_changed = False

            fc_inst = FooocusClient()
            is_fc_on = fc_inst.is_running()

            # Пагинация для больших проектов (90+ сцен) - ускоряет загрузку в 10 раз!
            PAGE_SIZE = 15
            total_scenes_cnt = len(scenes_sw)
            if total_scenes_cnt > PAGE_SIZE:
                num_pages = math.ceil(total_scenes_cnt / PAGE_SIZE)
                page_options = [f"Кадры {p*PAGE_SIZE + 1} – {min((p+1)*PAGE_SIZE, total_scenes_cnt)}" for p in range(num_pages)]
                page_options.append(f"Показать все {total_scenes_cnt} кадров (медленнее)")

                col_pg1, col_pg2 = st.columns([2, 3])
                with col_pg1:
                    selected_page_str = st.selectbox("📄 Страница раскадровки:", page_options, index=0, key="sw_page_select")
                with col_pg2:
                    st.write("")
                    st.write("")
                    if st.button("🔍 Найти варианты видео для кадров этой страницы (в 1 клик)", key="btn_pg_find_vids", use_container_width=True):
                        with st.spinner("Поиск вариантов видео для кадров этой страницы на Pexels..."):
                            px_downloader = PexelsDownloader(proxy=st.session_state.get("pexels_proxy_input") or None)
                            page_idx = page_options.index(selected_page_str) if "Показать все" not in selected_page_str else 0
                            p_start = page_idx * PAGE_SIZE
                            p_end = min(p_start + PAGE_SIZE, total_scenes_cnt)
                            target_sc = scenes_sw if "Показать все" in selected_page_str else scenes_sw[p_start:p_end]
                            px_downloader.batch_search_candidates(target_sc, pm.project_dir, limit_per_scene=3)
                            st.success("Готово! Варианты загружены.")
                            st.rerun()

                if "Показать все" in selected_page_str:
                    display_scenes = scenes_sw
                else:
                    page_idx = page_options.index(selected_page_str)
                    p_start = page_idx * PAGE_SIZE
                    p_end = min(p_start + PAGE_SIZE, total_scenes_cnt)
                    display_scenes = scenes_sw[p_start:p_end]
                    st.caption(f"Отображены сцены с #{p_start+1} по #{p_end} из {total_scenes_cnt}")
            else:
                display_scenes = scenes_sw

            all_cached_cand = PexelsDownloader.load_cached_candidates(pm.project_dir)

            for s in display_scenes:
                with st.container(border=True):
                    st.markdown(f"#### Сцена {s.index}: {s.title}")
                    
                    left_col, right_col = st.columns([1, 1])
                    
                    with left_col:
                        # Текст сцены
                        st.caption("📄 Текст реплики:")
                        st.text_area("", value=s.text[:300] + ("..." if len(s.text) > 300 else ""),
                                     height=90, disabled=True, key=f"sw_txt_{s.index}", label_visibility="collapsed")

                        # Подбор кадра
                        st.caption("🔍 Подобрать кадр:")
                        search_tabs = st.tabs([
                            "🎬 Pexels B-Roll (Full HD Video)",
                            "🎨 Fooocus (RTX 4060 Ti)",
                            "🔎 Поиск в сети (Яндекс)",
                            "🤖 Быстрый AI",
                            "📁 Загрузить файл"
                        ])

                        # --- ВКЛАДКА 0: PEXELS B-ROLL (FULL HD VIDEO) ---
                        with search_tabs[0]:
                            st.caption("Поиск и скачивание кинематографичных Full HD видеоклипов (16:9):")
                            px_q = st.text_input("Поисковый запрос Pexels (English):", value=s.search_query, key=f"sw_px_q_{s.index}")
                            
                            c_px_act1, c_px_act2 = st.columns([1, 1])
                            with c_px_act1:
                                search_px_btn = st.button("🔎 Найти видео", key=f"sw_px_search_{s.index}", use_container_width=True)
                            with c_px_act2:
                                if st.button("✨ Перегенерировать тег (AI)", key=f"sw_px_regen_{s.index}", use_container_width=True):
                                    with st.spinner("AI подбирает тег..."):
                                        try:
                                            new_q = PexelsDownloader.generate_broll_queries([s.text], style_context=pm.load_meta().get("topic", ""))[0]
                                            s.search_query = new_q
                                            scenes_changed = True
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Ошибка: {e}")

                            if search_px_btn:
                                with st.spinner("Поиск на Pexels..."):
                                    cur_px = PexelsDownloader(proxy=st.session_state.get("pexels_proxy_input") or None)
                                    found_vids = cur_px.search_videos(px_q, limit=4)
                                    for fv in found_vids:
                                        if fv.get("preview_url"):
                                            b_img = cur_px.fetch_image_bytes(fv["preview_url"])
                                            if b_img:
                                                fv["thumb_bytes"] = b_img
                                    st.session_state[f"sw_px_res_{s.index}"] = found_vids
                                    all_cached_cand[str(s.index)] = found_vids
                                    PexelsDownloader.save_cached_candidates(pm.project_dir, all_cached_cand)

                            px_cached = all_cached_cand.get(str(s.index)) or st.session_state.get(f"sw_px_res_{s.index}", [])
                            if px_cached:
                                st.write("Найденные видеоклипы (выберите лучший):")
                                for v_idx, vid in enumerate(px_cached):
                                    with st.container(border=True):
                                        c_vi1, c_vi2 = st.columns([1, 2])
                                        with c_vi1:
                                            p_url = vid.get("preview_url")
                                            if p_url:
                                                st.image(p_url, use_container_width=True)
                                            else:
                                                st.caption("🎬 16:9 Video")
                                        with c_vi2:
                                            st.markdown(f"**{vid.get('title', 'Video')}**")
                                            st.caption(f"⏱️ {vid.get('duration', 0)} сек • Разрешение: {vid.get('width', 0)}p")
                                            if st.button(f"📥 Поставить это видео в сцену", key=f"sw_px_pick_{s.index}_{v_idx}", type="primary"):
                                                with st.spinner("Скачивание Full HD MP4..."):
                                                    cur_px = PexelsDownloader(proxy=st.session_state.get("pexels_proxy_input") or None)
                                                    dest_vid = pm.visuals_dir / f"scene_{s.index:03d}.mp4"
                                                    if cur_px.download_video_file(vid["download_url"], dest_vid):
                                                        s.visual_path = str(dest_vid)
                                                        scenes_changed = True
                                                        st.success(f"Видео `{dest_vid.name}` успешно привязано к сцене {s.index}!")
                                                        st.rerun()
                                                    else:
                                                        st.error("Не удалось скачать видео. Проверьте интернет-соединение.")

                        # --- ВКЛАДКА 1: FOOOCUS (RTX 4060 Ti) ---
                        with search_tabs[1]:
                            if is_fc_on:
                                st.success("🟢 **Fooocus подключен** (RTX 4060 Ti активна) • [Открыть в браузере (7865)](http://127.0.0.1:7865)")
                            else:
                                st.info("⚪ **Fooocus не запущен.** Запустите `start_fooocus.bat` для генерации на видеокарте или используйте кнопку ниже.")

                            # Стиль кадра
                            col_fst1, col_fst2 = st.columns([2, 1])
                            with col_fst1:
                                fc_style = st.selectbox(
                                    "Стиль сцены:",
                                    list(SD_STYLE_PRESETS.keys()),
                                    index=0,
                                    key=f"sw_fc_style_{s.index}"
                                )
                            with col_fst2:
                                st.write("")
                                st.write("")
                                if st.button("✨ Умный промпт", key=f"sw_fc_pgen_{s.index}"):
                                    with st.spinner("Создание промпта..."):
                                        f_pos, f_neg = craft_smart_ai_prompt(s, style_name=fc_style, use_gemini=True)
                                        st.session_state[f"sw_fc_prompt_{s.index}"] = f_pos
                                        st.session_state[f"sw_fc_neg_{s.index}"] = f_neg
                                        st.rerun()

                            # Промпт для Fooocus (мгновенная инициализация без сетевых блокировок)
                            fc_pkey = f"sw_fc_prompt_{s.index}"
                            if fc_pkey not in st.session_state or not st.session_state[fc_pkey]:
                                init_p, init_n = craft_smart_ai_prompt(s, style_name=fc_style, use_gemini=False)
                                st.session_state[fc_pkey] = init_p
                                st.session_state[f"sw_fc_neg_{s.index}"] = init_n

                            fc_cur_prompt = st.text_area(
                                "Промпт для Fooocus (English):",
                                value=st.session_state[fc_pkey],
                                height=80,
                                key=f"sw_fc_prompt_input_{s.index}"
                            )

                            # Кнопки действий с Fooocus
                            col_fbtn1, col_fbtn2 = st.columns(2)
                            with col_fbtn1:
                                if st.button("📥 Забрать последний кадр из Fooocus", key=f"sw_fc_grab_{s.index}", type="primary", use_container_width=True):
                                    latest_img = fc_inst.get_latest_output_image()
                                    if latest_img and latest_img.exists():
                                        img_save = pm.visuals_dir / f"scene_{s.index:03d}{latest_img.suffix}"
                                        import shutil
                                        shutil.copy2(latest_img, img_save)
                                        s.visual_path = str(img_save)
                                        scenes_changed = True
                                        st.success(f"Кадр из Fooocus добавлен: `{latest_img.name}`!")
                                        st.rerun()
                                    else:
                                        st.warning("В папке Fooocus/outputs пока нет картинок. Сгенерируйте кадр в Fooocus!")

                            with col_fbtn2:
                                if is_fc_on:
                                    if st.button("🚀 Сгенерировать через API", key=f"sw_fc_gen_{s.index}", use_container_width=True):
                                        img_save = pm.visuals_dir / f"scene_{s.index:03d}.png"
                                        with st.spinner("Генерация на RTX 4060 Ti..."):
                                            res_p = fc_inst.generate_via_api(
                                                fc_cur_prompt,
                                                img_save,
                                                negative_prompt=st.session_state.get(f"sw_fc_neg_{s.index}", "")
                                            )
                                            if res_p and res_p.exists():
                                                s.visual_path = str(res_p)
                                                scenes_changed = True
                                                st.success("Кадр сгенерирован на RTX 4060 Ti!")
                                                st.rerun()
                                            else:
                                                st.error("Не удалось получить изображение через API. Сгенерируйте в окне Fooocus и нажмите «Забрать последний кадр».")
                                else:
                                    st.caption("💡 Для прямой API-генерации запустите `start_fooocus.bat`.")

                        # --- ВКЛАДКА 2: ПОИСК В СЕТИ (ЯНДЕКС) ---
                        with search_tabs[2]:
                            sq = st.text_input("Поисковый запрос:", value=s.search_query, key=f"sw_sq_{s.index}")
                            c_sb1, c_sb2 = st.columns(2)
                            with c_sb1:
                                search_engine_sw = st.selectbox("Источник:", ["Yandex (Архив/РФ)", "Bing", "Wikimedia"], key=f"sw_eng_{s.index}")
                            with c_sb2:
                                search_limit_sw = st.number_input("Кол-во результатов", 3, 15, 6, key=f"sw_lim_{s.index}")

                            if st.button(f"🔍 Найти кадры", key=f"sw_search_{s.index}"):
                                with st.spinner("Поиск..."):
                                    eng_map = {"Yandex (Архив/РФ)": "yandex", "Bing": "bing", "Wikimedia": "wikimedia"}
                                    results_sw = searcher_sw.search(sq, engine=eng_map[search_engine_sw], limit=search_limit_sw)
                                    st.session_state[f"sw_results_{s.index}"] = results_sw

                            if f"sw_results_{s.index}" in st.session_state:
                                results_sw = st.session_state[f"sw_results_{s.index}"]
                                if results_sw:
                                    img_cols = st.columns(3)
                                    for ri, r in enumerate(results_sw[:6]):
                                        with img_cols[ri % 3]:
                                            thumb = r.get("thumb_url") or r.get("image_url", "")
                                            if thumb:
                                                try:
                                                    st.image(thumb, use_container_width=True)
                                                except Exception:
                                                    st.caption(r.get("title", "")[:30])
                                            if st.button("✅ Выбрать", key=f"sw_pick_{s.index}_{ri}"):
                                                # Скачиваем и сохраняем
                                                img_save = pm.visuals_dir / f"scene_{s.index:03d}.jpg"
                                                try:
                                                    with st.spinner("Загрузка..."):
                                                        searcher_sw.download_image(r["image_url"], img_save, thumb_url=r.get("thumb_url"))
                                                    s.visual_path = str(img_save)
                                                    scenes_changed = True
                                                    st.success("Кадр выбран!")
                                                    st.rerun()
                                                except Exception as e:
                                                    st.error(f"Ошибка: {e}")
                                else:
                                    st.info("Ничего не найдено. Попробуйте другой запрос.")

                        # --- ВКЛАДКА 3: БЫСТРЫЙ AI (ОБЛАКО/РЕЗЕРВ) ---
                        with search_tabs[3]:
                            col_st1, col_st2 = st.columns([2, 1])
                            with col_st1:
                                style_choice = st.selectbox(
                                    "🎨 Кинематографичный стиль (SD Presets):",
                                    list(SD_STYLE_PRESETS.keys()),
                                    index=0,
                                    key=f"sw_style_{s.index}"
                                )
                            with col_st2:
                                st.write("")
                                st.write("")
                                if st.button("✨ Обновить промпт", key=f"sw_aip_gemini_{s.index}"):
                                    with st.spinner("Формирование промпта..."):
                                        smart_pos, smart_neg = craft_smart_ai_prompt(s, style_name=style_choice, use_gemini=True)
                                        st.session_state[f"sw_aip_val_{s.index}"] = smart_pos
                                        st.session_state[f"sw_aip_neg_{s.index}"] = smart_neg
                                        st.rerun()

                            ss_key = f"sw_aip_val_{s.index}"
                            current_pos = st.session_state.get(ss_key, "")
                            old_template = f"Сцена {s.index}" in current_pos and "cinematic 16:9" in current_pos
                            if not current_pos or old_template:
                                current_pos, current_neg = craft_smart_ai_prompt(s, style_name=style_choice, use_gemini=False)
                                st.session_state[ss_key] = current_pos
                                st.session_state[f"sw_aip_neg_{s.index}"] = current_neg

                            ai_prompt = st.text_area(
                                "AI промпт (English / Русский):",
                                value=st.session_state.get(ss_key, current_pos),
                                height=85,
                                key=f"sw_aip_{s.index}"
                            )

                            neg_key = f"sw_aip_neg_{s.index}"
                            default_neg = st.session_state.get(neg_key, SD_STYLE_PRESETS[style_choice]["negative"])
                            with st.expander("🛡️ Фильтр артефактов (Negative Prompt)", expanded=False):
                                ai_neg_prompt = st.text_input(
                                    "Negative prompt:",
                                    value=default_neg,
                                    key=f"sw_aip_neg_input_{s.index}"
                                )

                            col_aib1, col_aib2 = st.columns([1, 2])
                            with col_aib1:
                                if st.button("🔄 Сбросить", key=f"sw_aip_reset_{s.index}"):
                                    st.session_state[f"sw_aip_val_{s.index}"] = ""
                                    st.rerun()
                            with col_aib2:
                                if st.button("🤖 Сгенерировать кадр", key=f"sw_aigen_{s.index}", type="primary"):
                                    img_save = pm.visuals_dir / f"scene_{s.index:03d}.jpg"
                                    with st.spinner("Генерация кадра..."):
                                        try:
                                            ig_sw.generate_single_image(
                                                ai_prompt,
                                                img_save,
                                                negative_prompt=ai_neg_prompt,
                                                title=s.title
                                            )
                                            s.visual_path = str(img_save)
                                            scenes_changed = True
                                            st.success("Кадр готов!")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Ошибка генерации: {e}")

                        # --- ВКЛАДКА 4: ЗАГРУЗИТЬ ФАЙЛ ---
                        with search_tabs[4]:
                            uploaded_sw = st.file_uploader(
                                "Загрузите фото (JPG/PNG) или видеоклип (MP4)",
                                type=["jpg", "jpeg", "png", "mp4", "mov"],
                                key=f"sw_upload_{s.index}"
                            )
                            if uploaded_sw and st.button("💾 Использовать этот файл", key=f"sw_use_upload_{s.index}"):
                                ext = Path(uploaded_sw.name).suffix.lower()
                                save_up = pm.visuals_dir / f"scene_{s.index:03d}{ext}"
                                save_up.write_bytes(uploaded_sw.getvalue())
                                s.visual_path = str(save_up)
                                scenes_changed = True
                                st.success(f"Файл сохранён: {save_up.name}")

                    with right_col:
                        # Превью выбранного кадра
                        st.caption("🎬 Текущий кадр сцены:")
                        if s.visual_path and Path(s.visual_path).exists():
                            vp = Path(s.visual_path)
                            if vp.suffix.lower() == ".mp4":
                                st.video(str(vp))
                            else:
                                st.image(str(vp), use_container_width=True)
                            st.caption(f"`{vp.name}`")
                        else:
                            st.markdown(
                                "<div style='background:#1a1a2e;border-radius:8px;padding:40px;text-align:center;color:#666;font-size:13px;'>Кадр не выбран</div>",
                                unsafe_allow_html=True
                            )

                        # Настройки эффекта и тайминга
                        st.caption("⚙️ Эффект и тайминг:")
                        cur_effect_label = EFFECT_LABELS.get(s.effect, "🎥 Ken Burns: наезд (Zoom In)")
                        new_effect_label = st.selectbox(
                            "Эффект:", list(EFFECTS_MAP.keys()),
                            index=list(EFFECTS_MAP.keys()).index(cur_effect_label) if cur_effect_label in EFFECTS_MAP else 0,
                            key=f"sw_eff_{s.index}"
                        )
                        new_effect = EFFECTS_MAP[new_effect_label]
                        if new_effect != s.effect:
                            s.effect = new_effect
                            scenes_changed = True

                        new_dur = st.number_input(
                            f"Длительность (сек, авто={s.duration:.0f}с):",
                            min_value=2.0, max_value=600.0,
                            value=float(min(s.custom_duration or s.duration, 600.0)),
                            step=0.5, key=f"sw_dur_{s.index}"
                        )
                        if abs(new_dur - (s.custom_duration or s.duration)) > 0.1:
                            s.custom_duration = new_dur
                            scenes_changed = True

            if scenes_changed:
                tl_builder.save_timeline(scenes_sw)
                save_scenes(scenes_sw, pm.project_dir)

            # Кнопка рендера видеоряда
            st.divider()
            scenes_ready = [s for s in scenes_sw if s.visual_path and Path(s.visual_path).exists()]
            scenes_missing = [s for s in scenes_sw if not s.visual_path or not Path(s.visual_path).exists()]

            if scenes_missing:
                st.warning(f"⚠️ Не выбраны кадры для {len(scenes_missing)} сцен: {', '.join([f'#{s.index}' for s in scenes_missing])}. Эти сцены будут пропущены.")

            if scenes_ready:
                col_rb1, col_rb2 = st.columns([2, 1])
                with col_rb1:
                    force_rerender = st.checkbox("🔄 Перерендерить уже готовые клипы", value=False, key="sw_force_render")
                with col_rb2:
                    render_res = st.selectbox("Разрешение:", ["1920x1080 (Full HD)", "1280x720 (HD)"], key="sw_res")

                if st.button("🎬 РЕНДЕРИТЬ ВИДЕОРЯД (без озвучки)", type="primary", use_container_width=True, key="sw_btn_render"):
                    prog_sw = st.progress(0, text="Начинаем рендер...")
                    status_sw = st.empty()

                    def on_tl_prog(pct, msg):
                        prog_sw.progress(int(pct * 100), text=f"{int(pct*100)}%")
                        status_sw.info(f"⚙️ {msg}")

                    try:
                        track = tl_builder.build_videotrack(
                            scenes_sw,
                            progress_callback=on_tl_prog,
                            force=force_rerender
                        )
                        prog_sw.progress(100, "✅ Видеоряд готов!")
                        status_sw.success(f"🎬 Видеоряд создан: `{track.name}` ({track.stat().st_size // (1024*1024)} MB)")
                        st.rerun()
                    except Exception as e:
                        status_sw.error(f"Ошибка рендера: {e}")

            # Превью готового видеоряда
            videotrack = pm.project_dir / "render" / "videotrack.mp4"
            if videotrack.exists():
                st.markdown("#### 🎥 Готовый видеоряд (без озвучки):")
                st.video(str(videotrack))
                with open(videotrack, "rb") as vf:
                    st.download_button("⬇️ Скачать видеоряд (MP4)", data=vf.read(),
                                       file_name=f"{pm.slug}_videotrack.mp4",
                                       mime="video/mp4", key="sw_dl_track")

    st.divider()

    # ================================================================
    # ШАГ 3: Озвучка поверх видеоряда
    # ================================================================
    with st.expander("🎙️ Шаг 3: Озвучка поверх готового видеоряда", expanded=step2_done and not step3_done):
        if not step2_done:
            st.warning("Сначала выполните Шаг 2: отрендерите видеоряд.")
        else:
            st.info("Видеоряд готов. Теперь добавьте озвучку — автоматически или своим файлом.")
            videotrack_sw = pm.project_dir / "render" / "videotrack.mp4"
            st.video(str(videotrack_sw))

            audio_mode_sw = st.radio("Способ озвучки:", [
                "🤖 Auto TTS (синтез голоса Gemini/Edge)",
                "📂 Загрузить готовый MP3"
            ], key="sw_audio_mode")

            audio_path_sw = None

            if audio_mode_sw.startswith("🤖"):
                # Показываем очищенный текст для синтеза
                clean_text_sw = pm.load_voiceover_clean() or pm.load_script()
                if not clean_text_sw.strip():
                    st.warning("Текст сценария не найден. Добавьте сценарий во вкладке «1. Сценарий».")
                else:
                    words_sw = len(clean_text_sw.split())
                    st.caption(f"Текст для озвучки: **{words_sw} слов** (~{words_sw//135} мин)")
                    with st.expander("Просмотреть текст озвучки"):
                        st.text_area("", value=clean_text_sw[:2000] + ("..." if len(clean_text_sw) > 2000 else ""),
                                     height=150, disabled=True, key="sw_vo_preview")

                    c_tts1, c_tts2 = st.columns(2)
                    with c_tts1:
                        tts_eng_sw = st.radio("Движок:", ["⚡ Edge TTS", "🌟 Google Gemini"], key="sw_tts_eng")
                    with c_tts2:
                        if "Edge" in tts_eng_sw:
                            tts_voice_sw = st.selectbox("Голос:", ["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"], key="sw_edge_voice")
                            tts_engine_sw = "edge"
                        else:
                            tts_voice_sw = st.selectbox("Голос:", ["Milo", "Nika", "Charon", "Fenrir"], key="sw_gem_voice")
                            tts_engine_sw = "gemini"

                    if st.button("🎙️ Синтезировать голос диктора", type="primary", key="sw_btn_tts"):
                        tts_out_sw = pm.get_audio_path("voiceover_full.mp3")
                        prog_tts_sw = st.progress(0, text="Начинаем синтез...")

                        def on_tts_sw(cur, tot, prev):
                            if tot > 0:
                                prog_tts_sw.progress(int(cur / tot * 90), text=f"TTS: блок {cur}/{tot}")

                        with st.spinner("Синтез речи..."):
                            try:
                                tts_sw = TTSSynthesizer(voice=tts_voice_sw, engine=tts_engine_sw, concurrency=4)
                                tts_sw.synthesize_to_file(clean_text_sw, tts_out_sw, progress_callback=on_tts_sw)
                                prog_tts_sw.progress(100, "✅ Озвучка готова!")
                                audio_path_sw = tts_out_sw
                                st.success(f"🎙️ Аудио: `{tts_out_sw.name}` ({tts_out_sw.stat().st_size // 1024} KB)")
                            except Exception as e:
                                st.error(f"Ошибка TTS: {e}")

                # Ищем любые доступные аудиофайлы проекта (включая загруженные в Шаге 1)
                all_found_audios = list(pm.audio_dir.glob("*.mp3")) + list(pm.audio_dir.glob("*.wav")) + list(pm.audio_dir.glob("*.m4a"))
                if all_found_audios and not audio_path_sw:
                    audio_path_sw = all_found_audios[0]
                    st.info(f"✅ Используется активный аудиофайл: `{audio_path_sw.name}` ({format_duration(get_audio_duration(audio_path_sw))}). Нажмите «Смонтировать» ниже.")

            else:
                uploaded_audio_sw = st.file_uploader("Загрузите MP3/WAV файл озвучки из Google AI Studio:", type=["mp3", "wav", "m4a", "ogg"], key="sw_up_audio")
                if uploaded_audio_sw:
                    audio_save_sw = pm.get_audio_path(uploaded_audio_sw.name)
                    audio_save_sw.write_bytes(uploaded_audio_sw.getvalue())
                    audio_path_sw = audio_save_sw
                    st.success(f"Файл загружен: {audio_save_sw.name} ({format_duration(get_audio_duration(audio_save_sw))})")
                else:
                    all_found_audios = list(pm.audio_dir.glob("*.mp3")) + list(pm.audio_dir.glob("*.wav")) + list(pm.audio_dir.glob("*.m4a"))
                    if all_found_audios and not audio_path_sw:
                        audio_path_sw = all_found_audios[0]
                        st.info(f"✅ Используется активный аудиофайл: `{audio_path_sw.name}` ({format_duration(get_audio_duration(audio_path_sw))}).")

            # Финальный рендер
            st.divider()
            if st.button("🎬 СМОНТИРОВАТЬ ФИНАЛЬНОЕ ВИДЕО", type="primary", use_container_width=True, key="sw_btn_final"):
                prog_fin = st.progress(0, text="Финальный рендер...")
                st._arrow_time = None

                def on_fin_prog(pct, msg):
                    prog_fin.progress(int(pct * 100), text=msg)

                try:
                    final_path = tl_builder.mix_with_audio(
                        audio_path=audio_path_sw,
                        progress_callback=on_fin_prog
                    )
                    prog_fin.progress(100, "✅ Финальное видео готово!")
                    st.balloons()
                    st.success(f"🎉 Готово! `{final_path.name}` ({final_path.stat().st_size // (1024*1024)} MB)")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка финального рендера: {e}")

    # Блок готового финального видео
    final_sw = pm.project_dir / "final_video.mp4"
    if final_sw.exists() and final_sw.stat().st_size > 10000:
        st.divider()
        st.subheader("🎉 Финальное видео готово!")
        st.video(str(final_sw))
        with open(final_sw, "rb") as fvf:
            st.download_button("⬇️ Скачать финальное видео (MP4)", data=fvf.read(),
                               file_name=f"{pm.slug}_final.mp4", mime="video/mp4",
                               type="primary", use_container_width=True, key="sw_dl_final")

# Вкладка 1: Сценарий
with tab_script:
    st.subheader("1. Написание сценария с формулой удержания")
    
    project_meta = pm.load_meta()
    saved_topic = project_meta.get("topic", "")
    saved_genre = project_meta.get("genre", "Детективное расследование / True Crime")
    saved_minutes = project_meta.get("minutes", 15)

    col_t1, col_t2, col_t3 = st.columns([3, 2, 1])
    with col_t1:
        topic = st.text_input("Тема ролика / Главный конфликт", value=saved_topic, placeholder="например: ИИ-революция, тайна перевала Дятлова, крах Theranos, история SpaceX...")
    with col_t2:
        genre_options = [
            "Детективное расследование / True Crime",
            "Бизнес, деньги и крах корпораций (в стиле Magnates Media)",
            "Наука, космос и будущее (в стиле Kurzgesagt / Veritasium)",
            "Историческая документалистика (в стиле Lemmino)",
            "Технологии и ИИ",
            "Психология и общество (в стиле JCS)",
            "✏️ Другой жанр (ввести вручную)"
        ]
        g_idx = genre_options.index(saved_genre) if saved_genre in genre_options else 0
        selected_genre = st.selectbox("Жанр / Направление", genre_options, index=g_idx)
        if selected_genre == "✏️ Другой жанр (ввести вручную)":
            genre_val = st.text_input("Введите жанр вручную:", value="Документальное видео")
        else:
            genre_val = selected_genre
    with col_t3:
        minutes = st.number_input("Хронометраж (мин)", min_value=3, max_value=60, value=int(saved_minutes), step=5)
        
    # Расчет целевого объема текста
    chars_per_min = 900
    target_total_chars = int(minutes * chars_per_min)
    st.caption(f"🎯 Ориентировочный целевой объем: **~{target_total_chars:,} знаков** (из расчета ~{chars_per_min} знаков / 130-140 слов в минуту для {minutes} мин).")

    saved_raw = pm.load_raw_material()

    # Встроенный парсер статей по ссылке (URL)
    with st.expander("🌐 Автоматический парсер статей по ссылке (URL)", expanded=not bool(saved_raw.strip())):
        st.markdown("**Быстрый импорт статьи прямо в проект**")
        st.caption("Вставьте ссылку на любую статью или расследование в интернете (например, Holod.media, Lenta.ru, Dzen, Коммерсант, Википедия и др.). Система сама обойдет блокировки/DPI, очистит текст от рекламы, меню и навигации и загрузит чистый материал.")

        c_url1, c_url2 = st.columns([4, 1.4])
        with c_url1:
            article_url_input = st.text_input(
                "Ссылка на статью (URL):",
                placeholder="https://holod.media/2026/08/28/roditeli-zamuchili-doch-izgonyaya-besov/",
                key="article_url_input"
            )
        with c_url2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            parse_mode = st.selectbox(
                "Куда загрузить:", 
                ["Заменить исходники", "Добавить в конец"], 
                key="parse_target_mode", 
                label_visibility="collapsed"
            )

        c_pbtn1, c_pbtn2 = st.columns([1.5, 3])
        with c_pbtn1:
            btn_do_parse = st.button("⚡ Спарсить статью", key="btn_do_parse", type="secondary", use_container_width=True)
        with c_pbtn2:
            auto_download_photos = st.checkbox("📸 Сразу скачать все фото статьи в проект (visuals/)", value=True, help="Автоматически найдет все контентные фото и архивные снимки в статье и сохранит их в проект")

        if btn_do_parse:
            if not article_url_input.strip():
                st.warning("Пожалуйста, введите ссылку на статью.")
            else:
                with st.spinner("🔍 Загружаем страницу, обходим блокировки и извлекаем чистый текст статьи..."):
                    parse_res = ArticleParser.parse_url(article_url_input.strip())
                    if parse_res.get("success"):
                        p_title = parse_res.get("title", "")
                        p_text = parse_res.get("text", "")
                        p_chars = parse_res.get("chars", 0)
                        p_words = parse_res.get("words", 0)
                        p_method = parse_res.get("source_method", "")

                        method_label = "напрямую с сайта" if p_method == "direct" else "через зеркало веб-архива (обход блокировки)"

                        if parse_mode == "Заменить исходники" or not saved_raw.strip():
                            new_raw_content = f"# {p_title}\n\nИсточник: {article_url_input.strip()}\n\n{p_text}"
                        else:
                            new_raw_content = f"{saved_raw.strip()}\n\n---\n# {p_title}\nИсточник: {article_url_input.strip()}\n\n{p_text}"

                        pm.save_raw_material(new_raw_content)

                        # Если тема пустая, автоматически заполняем заголовком статьи
                        if not topic.strip() and p_title:
                            pm.save_meta({"topic": p_title, "genre": genre_val, "minutes": int(minutes)})

                        # Автозагрузка фотографий, если включено
                        saved_photos_count = 0
                        if auto_download_photos:
                            with st.spinner("📸 Извлекаем и сохраняем фото статьи..."):
                                img_res = ArticleParser.parse_article_images(article_url_input.strip())
                                if img_res.get("success") and img_res.get("photos"):
                                    for p in img_res["photos"]:
                                        t_path = pm.visuals_dir / p["filename"]
                                        if ArticleParser.download_image(p["url"], t_path):
                                            saved_photos_count += 1

                        photos_msg = f" и скачано **{saved_photos_count}** фото в папку visuals/!" if saved_photos_count > 0 else "!"
                        st.success(f"✅ Статья «{p_title}» успешно спарсена ({method_label})! Извлечено **{p_chars:,}** знаков (**{p_words:,}** слов){photos_msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ Ошибка парсинга: {parse_res.get('error')}")

    raw_input = st.text_area(
        "Исходные материалы (статьи, заметки, расшифровки, ссылки, факты)", 
        value=saved_raw, 
        height=220,
        placeholder="Вставьте сюда любой объем исходного текста или статей, которые вы нашли в интернете. Система автоматически создаст последовательный план глав и напишет непрерывный динамичный сценарий по вашим промптам.",
        help="Вставьте сюда найденную в интернете статью или заметки."
    )
    
    col_save_raw1, col_save_raw2 = st.columns([1, 4])
    with col_save_raw1:
        if st.button("💾 Сохранить материалы", key="save_raw_btn", use_container_width=True):
            pm.save_raw_material(raw_input)
            pm.save_meta({"topic": topic.strip(), "genre": genre_val, "minutes": int(minutes)})
            st.success("Материалы сохранены!")

    st.divider()

    # Пошаговая логика: Шаг 1 (План глав) и Шаг 2 (Поглавная генерация сценария)
    st.markdown("#### 📑 Пошаговая генерация по формуле удержания")
    st.caption("1. Создание структурного плана глав (крючки внимания) → 2. Последовательное написание каждой главы с контролем объема знаков.")

    saved_outline = pm.load_outline()
    
    col_step1, col_step2 = st.columns(2)
    with col_step1:
        st.markdown("**Шаг 1. Структурный план глав**")
        st.caption("Анализирует первоисточники и выстраивает цепь глав без резких обрывов.")
        btn_outline_label = "🔄 Перегенерировать план глав" if saved_outline.strip() else "📋 Создать план глав"
        if st.button(btn_outline_label, key="btn_gen_outline", use_container_width=True):
            if not raw_input.strip() and not topic.strip():
                st.error("Пожалуйста, заполните тему или вставьте исходные материалы.")
            else:
                pm.save_meta({"topic": topic.strip(), "genre": genre_val, "minutes": int(minutes)})
                if raw_input.strip():
                    pm.save_raw_material(raw_input.strip())
                with st.spinner("Gemini анализирует первоисточники и создает интригующий структурный план глав..."):
                    try:
                        sg = ScriptGenerator(model_name=model_name)
                        new_outline = sg.generate_outline(source_materials=raw_input, topic=topic)
                        pm.save_outline(new_outline)
                        st.success("План глав успешно сформирован!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка создания плана глав: {e}")

    with col_step2:
        st.markdown("**Шаг 2. Написание полного текста сценария**")
        st.caption("Пишет главу за главой по авторскому промпту с заданной плотностью знаков.")
        
        # Расчет знаков на главу
        parsed_chapters_count = len(ScriptGenerator.parse_outline_chapters(saved_outline)) if saved_outline.strip() else 5
        if parsed_chapters_count == 0:
            parsed_chapters_count = 5
        recommended_per_chapter = max(800, int(target_total_chars / parsed_chapters_count))

        chars_per_chapter = st.number_input(
            f"Знаков на главу (глав в плане: {parsed_chapters_count})",
            min_value=500,
            max_value=8000,
            value=recommended_per_chapter,
            step=100,
            help="Регулирует объем каждой главы. Суммарный объем = Знаков на главу * Количество глав."
        )

    # Редактор плана глав, если он создан
    if saved_outline.strip():
        with st.expander("📋 Просмотр и редактирование плана глав (outline.txt)", expanded=True):
            edited_outline = st.text_area("План глав (можно корректировать перед генерацией)", value=saved_outline, height=180)
            if edited_outline != saved_outline:
                if st.button("💾 Сохранить изменения в плане"):
                    pm.save_outline(edited_outline)
                    st.success("План сохранен!")
                    st.rerun()

    # Кнопки запуска написания сценария
    current_script = pm.load_script()
    st.write("")
    col_run1, col_run2 = st.columns([1.5, 1])

    with col_run1:
        run_label = "⚡ Сгенерировать сценарий по главам (Полный объем)" if not current_script.strip() else "🔄 Перегенерировать сценарий по главам"
        btn_run_chapters = st.button(run_label, type="primary", use_container_width=True, key="btn_run_chapters")

    with col_run2:
        btn_run_quick = st.button("⏩ Быстрый сценарий в 1 клик", use_container_width=True, key="btn_run_quick", help="Генерирует классический двухколоночный режиссерский сценарий за один запрос")

    # Обработка поглавной генерации
    if btn_run_chapters:
        effective_outline = saved_outline.strip()
        if not effective_outline:
            # Если план еще не был нажат отдельно, генерируем его автоматически на лету
            if not raw_input.strip() and not topic.strip():
                st.error("Пожалуйста, заполните тему или исходные материалы.")
            else:
                pm.save_meta({"topic": topic.strip(), "genre": genre_val, "minutes": int(minutes)})
                if raw_input.strip():
                    pm.save_raw_material(raw_input.strip())
                with st.spinner("Шаг 1: Создаем структурный план глав..."):
                    try:
                        sg = ScriptGenerator(model_name=model_name)
                        effective_outline = sg.generate_outline(source_materials=raw_input, topic=topic)
                        pm.save_outline(effective_outline)
                    except Exception as e:
                        st.error(f"Ошибка создания плана: {e}")
                        effective_outline = ""

        if effective_outline:
            chapters = ScriptGenerator.parse_outline_chapters(effective_outline)
            total_ch = len(chapters) if chapters else 1
            progress_bar = st.progress(0, text=f"Старт написания {total_ch} глав...")

            def on_progress(idx, total, title):
                pct = int((idx / total) * 100)
                progress_bar.progress(pct, text=f"✍️ Пишем главу {idx+1}/{total}: {title[:40]}...")

            try:
                sg = ScriptGenerator(model_name=model_name)
                full_script = sg.generate_script_by_chapters(
                    outline_text=effective_outline,
                    source_materials=raw_input,
                    min_chars_per_chapter=int(chars_per_chapter),
                    progress_callback=on_progress
                )
                progress_bar.progress(100, text="✅ Все главы успешно написаны!")
                pm.save_script(full_script)
                # Автоматически сохраняем чистый текст для озвучки
                pm.save_voiceover_clean(TTSSynthesizer.clean_voiceover_text(full_script))
                st.success(f"🎉 Сценарий успешно создан! Общий объем чистого текста: {len(full_script):,} знаков (~{len(full_script)//chars_per_min} мин начитки).")
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка при написании сценария: {e}")

    # Обработка быстрого сценария в 1 клик
    if btn_run_quick:
        if not raw_input.strip() and not topic.strip():
            st.error("Пожалуйста, укажите тему ролика или исходные материалы.")
        else:
            pm.save_meta({"topic": topic.strip(), "genre": genre_val, "minutes": int(minutes)})
            if raw_input.strip():
                pm.save_raw_material(raw_input.strip())

            with st.spinner("Gemini пишет сценарий с расстановкой актов, пауз и видеоряда..."):
                try:
                    sg = ScriptGenerator(model_name=model_name)
                    script_text = sg.generate_script(
                        topic=topic,
                        source_materials=raw_input,
                        target_minutes=minutes,
                        genre=genre_val
                    )
                    pm.save_script(script_text)
                    st.success("Сценарий успешно создан и сохранен в script.md!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка при обращении к Gemini API: {e}")

    current_script = pm.load_script()
    if current_script:
        st.divider()
        st.subheader("Текущий сценарий (script.md)")
        edited_script = st.text_area("Редактор сценария", value=current_script, height=450)
        if edited_script != current_script:
            if st.button("💾 Сохранить правки в script.md"):
                pm.save_script(edited_script)
                st.success("Правки сохранены!")
                st.rerun()

# Вкладка 2: Промпты для Nano Banana
with tab_prompts:
    st.subheader("2. Промпты для Nano Banana (Фото и Видео 16:9)")
    st.caption("Формирует русскоязычные детальные описания кадров, оптимизированные под генераторы изображений и видео.")

    current_script = pm.load_script()
    if not current_script:
        st.warning("Сначала создайте или сохраните сценарий на первой вкладке.")
    else:
        # Расчет хронометража
        script_words = len(current_script.split())
        est_minutes = script_words / 135.0
        est_total_sec = est_minutes * 60.0

        # Единый визуальный стиль проекта (Style DNA)
        curr_dna = pm.load_style_dna() if hasattr(pm, "load_style_dna") else None

        with st.expander("🎨 Единый визуальный стиль проекта (Style DNA / Библия стиля)", expanded=(curr_dna is not None)):
            st.caption("Гарантирует, что ВСЕ кадры видеоряда будут выглядеть в одной цветовой гамме, снятыми на одну камеру и в одну эпоху.")
            c_dna_btn1, c_dna_btn2 = st.columns([2, 1])
            with c_dna_btn1:
                st.write("**Статус стиля:** " + (f"✅ `{curr_dna.get('style_title')}`" if curr_dna else "⚪ *Стиль еще не определен (будет подобран автоматически)*"))
            with c_dna_btn2:
                if st.button("✨ Авто-определить стиль по сценарию", use_container_width=True):
                    with st.spinner("Gemini анализирует сценарий и определяет Visual Bible..."):
                        try:
                            pg_dna = PromptGenerator(model_name=model_name)
                            new_dna = pg_dna.determine_style_dna(current_script)
                            pm.save_style_dna(new_dna)
                            st.success(f"Единый стиль определен: {new_dna.get('style_title')}!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Ошибка определения стиля: {e}")

            if curr_dna:
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    d_title = st.text_input("Название стиля:", value=curr_dna.get("style_title", ""), key="dna_title_input")
                    d_palette = st.text_input("Цветовая палитра:", value=curr_dna.get("color_palette", ""), key="dna_pal_input")
                    d_light = st.text_input("Характер освещения:", value=curr_dna.get("lighting", ""), key="dna_light_input")
                with col_d2:
                    d_cam = st.text_input("Камера и оптика:", value=curr_dna.get("camera_look", ""), key="dna_cam_input")
                    d_era = st.text_input("Эпоха и атмосфера:", value=curr_dna.get("era_and_mood", ""), key="dna_era_input")
                    d_suffix = st.text_input("Единый суффикс промптов (16:9):", value=curr_dna.get("unified_suffix", ""), key="dna_suf_input")

                if (d_title != curr_dna.get("style_title") or d_palette != curr_dna.get("color_palette") or
                    d_light != curr_dna.get("lighting") or d_cam != curr_dna.get("camera_look") or
                    d_era != curr_dna.get("era_and_mood") or d_suffix != curr_dna.get("unified_suffix")):
                    if st.button("💾 Сохранить изменения стиля", key="save_dna_btn"):
                        curr_dna = {
                            "style_title": d_title,
                            "color_palette": d_palette,
                            "lighting": d_light,
                            "camera_look": d_cam,
                            "era_and_mood": d_era,
                            "unified_suffix": d_suffix
                        }
                        pm.save_style_dna(curr_dna)
                        st.success("Единый стиль сохранён!")
                        st.rerun()

        col_p1, col_p2, col_p3 = st.columns([2, 1.2, 1.5])
        with col_p1:
            visual_styles = [
                "Кинематографичный реализм (35мм пленка, глубокие тени, 4K, формат 16:9)",
                "Холодный детективный триллер (стиль Дэвида Финчера, teal & orange, 16:9)",
                "Эстетика бизнес-документалок (стиль Netflix / Bloomberg, чистый студийный свет, 16:9)",
                "Научная фантастика и космос (неон, глубокий космос, фотореализм 4K, 16:9)",
                "Исторический архив (эффект винтажной пленки, монохром/сепия, легкое зерно, 16:9)",
                "✏️ Свой стиль (ввести вручную)"
            ]
            default_style_idx = 0
            if curr_dna:
                visual_styles.insert(0, f"🎨 Единый стиль проекта: {curr_dna.get('style_title')}")
            selected_style = st.selectbox("Визуальный стиль видеоряда:", visual_styles, index=0)
            if selected_style == "✏️ Свой стиль (ввести вручную)":
                style_val = st.text_input("Введите визуальный стиль:", value="Кинематографичный стиль 16:9, 4K")
            else:
                style_val = selected_style

        with col_p2:
            step_seconds = st.selectbox(
                "Шаг смены кадра:",
                [30, 15, 45, 60],
                index=0,
                format_func=lambda x: f"Каждые {x} сек (стандарт)" if x == 30 else f"Каждые {x} сек"
            )
            est_frames_count = max(1, math.ceil(est_total_sec / step_seconds))
            st.caption(f"📊 ~{est_minutes:.1f} мин речи ➔ **{est_frames_count} кадров**")

        saved_prompts = pm.load_prompts()
        with col_p3:
            st.write("")
            st.write("")
            p_btn_label = f"🔄 Сформировать кадры (по {step_seconds}с)" if saved_prompts.strip() else f"🎬 Сформировать кадры (по {step_seconds}с)"
            gen_prompts_btn = st.button(p_btn_label, type="primary", use_container_width=True)

        if gen_prompts_btn:
            progress_bar_p = st.progress(0, text="Подготовка текста и разбивка по 30 сек...")
            try:
                pg = PromptGenerator(model_name=model_name)
                
                def on_prompt_progress(pct: int, msg: str):
                    progress_bar_p.progress(pct, text=msg)

                prompts_res = pg.generate_prompts(
                    current_script,
                    style=style_val,
                    interval_seconds=step_seconds,
                    only_images=True,
                    style_dna=curr_dna,
                    progress_callback=on_prompt_progress
                )
                pm.save_prompts(prompts_res)
                progress_bar_p.progress(100, text=f"✅ Готово! Сформировано {est_frames_count} кадров в едином стиле.")
                st.success(f"Раскадровка (строго по {step_seconds} сек в едином стиле) успешно создана и сохранена в prompts.md!")
                st.rerun()
            except Exception as e:
                progress_bar_p.empty()
                st.error(f"Ошибка формирования раскадровки: {e}")

        saved_prompts = pm.load_prompts()
        if saved_prompts:
            st.divider()
            st.subheader("🚀 Быстрый запуск в браузере (Gemini Pro & Nano Banana)")
            st.caption("Генерируйте фото и видео в оригинальном качестве без блокировок API и сторонних прокси:")
            
            c_links1, c_links2 = st.columns(2)
            with c_links1:
                st.link_button("🌐 Открыть чат Gemini Web (gemini.google.com)", "https://gemini.google.com/", type="primary", use_container_width=True)
            with c_links2:
                st.link_button("🍌 Открыть Nano Banana Studio", "https://nanobanano.com/", use_container_width=True)

            scenes = ImageGenerator.parse_prompts_from_markdown(saved_prompts)
            v_scenes = [s for s in scenes if s["media_type"] == "ВИДЕО"]
            p_scenes = [s for s in scenes if s["media_type"] == "ФОТО"]

            st.subheader("📦 Быстрое копирование пакетов для браузера (в 1 клик)")
            st.caption("Скопируйте нужный пакет и отправьте в чат Gemini или Nano Banana:")

            c_pack1, c_pack2 = st.columns(2)
            with c_pack1:
                with st.expander(f"📸 Пакет ФОТО для Gemini Web ({len(p_scenes)} кадров)", expanded=True):
                    photo_batch = "Создай серию фотореалистичных кинематографичных изображений в формате 16:9 в детективном стиле Дэвида Финчера (палитра teal & orange, 35мм пленка, 4K) для следующих сцен ролика:\n\n"
                    for s in p_scenes:
                        photo_batch += f"### {s['title']}\n{s['prompt']}\n\n"
                    st.code(photo_batch, language="markdown")

            with c_pack2:
                if v_scenes:
                    with st.expander(f"🎬 Пакет ВИДЕО для Nano Banana ({len(v_scenes)} кадров)", expanded=True):
                        video_batch = "Промпты для генерации видеороликов (Nano Banana Video / Luma / Runway) с динамикой камеры:\n\n"
                        for s in v_scenes:
                            video_batch += f"### {s['title']}\n{s['prompt']}\n\n"
                        st.code(video_batch, language="markdown")
                else:
                    with st.expander(f"🎨 Пакет для Fooocus / Midjourney ({len(p_scenes)} кадров)", expanded=True):
                        sd_batch = f"Серия кинематографичных кадров 16:9 (Стиль: {style_val}):\n\n"
                        for s in p_scenes:
                            sd_batch += f"### {s['title']}\n{s['prompt']}, cinematic 16:9, dramatic lighting, 8k\n\n"
                        st.code(sd_batch, language="markdown")

            # Обложки YouTube
            thumb_match = re.search(r'###\s*ОБЛОЖКА YOUTUBE.*', saved_prompts, re.DOTALL | re.IGNORECASE)
            if thumb_match:
                with st.expander("🎨 Варианты кликабельной обложки YouTube (Thumbnail)", expanded=False):
                    st.markdown(thumb_match.group(0))

            if scenes:
                st.divider()

                # ========================================================
                # 🎬 ПАКЕТНОЕ СКАЧИВАНИЕ PEXELS ПО ПРОМПТАМ РАЗДЕЛА 2
                # ========================================================
                with st.container(border=True):
                    st.markdown(f"### 🎬 Автоматическое скачивание видео с Pexels по этим {len(scenes)} кадрам")
                    st.caption("Берёт созданные выше художественные описания сцен (с учётом стиля и деталей), извлекает из каждого точный B-Roll тег и скачивает Full HD (1080p) MP4 видео прямо в проект.")

                    det_px2 = detect_local_proxy()
                    c_px_p1, c_px_p2 = st.columns([3, 1])
                    with c_px_p1:
                        tab2_proxy = st.text_input(
                            "Прокси для Pexels (если в РФ):",
                            value=st.session_state.get("pexels_proxy_input", det_px2 or ""),
                            placeholder="socks5://127.0.0.1:10808 (или оставьте пустым при включенном VPN)",
                            key="t2_px_proxy"
                        )
                        st.session_state["pexels_proxy_input"] = tab2_proxy
                    with c_px_p2:
                        st.write("")
                        st.write("")
                        if st.button("🔌 Проверить связь", key="btn_t2_test_px"):
                            with st.spinner("Проверка связи с Pexels..."):
                                tester = PexelsDownloader(proxy=tab2_proxy or None)
                                test_vids = tester.search_videos("dark street", limit=1)
                                if test_vids:
                                    st.success("🟢 Pexels доступен!")
                                else:
                                    st.warning("⚠️ Pexels не ответил. Проверьте VPN/прокси.")

                    c_btn_t2_1, c_btn_t2_2, c_btn_t2_3 = st.columns([1, 1.2, 1.2])
                    with c_btn_t2_1:
                        t2_overwrite = st.checkbox("Перезаписать уже найденное/скачанное", value=False, key="t2_px_over")
                    with c_btn_t2_2:
                        btn_t2_find_candidates = st.button(
                            f"🔍 1. НАЙТИ ВАРИАНТЫ ДЛЯ ВСЕХ {len(scenes)} КАДРОВ",
                            help="Автоматически находит по 3-4 видео для каждого кадра в фоне, чтобы вы сразу видели превью!",
                            use_container_width=True,
                            key="btn_t2_find_cand"
                        )
                    with c_btn_t2_3:
                        start_px_t2_btn = st.button(
                            f"🚀 АВТОПИЛОТ: СКАЧАТЬ ПЕРВОЕ ВИДЕО ДЛЯ ВСЕХ {len(scenes)} КАДРОВ",
                            type="primary",
                            help="Полный автомат: находит видео по художественному описанию, сразу скачивает первый (лучший) ролик в 1080p и привязывает к кадрам!",
                            use_container_width=True,
                            key="btn_t2_start_px"
                        )

                    if btn_t2_find_candidates:
                        px_dl = PexelsDownloader(proxy=tab2_proxy or None)
                        p_bar2 = st.progress(0, text="Извлечение B-roll тегов из промптов...")
                        prompt_texts = [sc.get("prompt", "") for sc in scenes]
                        broll_queries = px_dl.generate_broll_queries(prompt_texts, style_context=curr_dna.get("style_title") if curr_dna else "")

                        from modules.scene_parser import SceneBlock
                        temp_blocks = []
                        for s_idx, sc in enumerate(scenes):
                            sc_num = sc.get("index", s_idx + 1)
                            q_val = broll_queries[s_idx] if s_idx < len(broll_queries) else "cinematic documentary"
                            temp_blocks.append(SceneBlock(index=sc_num, title=sc.get("title", ""), text=sc.get("prompt", ""), duration=30.0, search_query=q_val))

                        def on_t2_cand_prog(pct: int, msg: str):
                            p_bar2.progress(pct, text=msg)

                        px_dl.batch_search_candidates(temp_blocks, pm.project_dir, limit_per_scene=3, overwrite=t2_overwrite, progress_callback=on_t2_cand_prog)
                        PexelsDownloader.sync_prompts_to_timeline(pm.project_dir, step_seconds=step_seconds)
                        st.success(f"🎉 Варианты найдены для всех {len(scenes)} кадров! Они уже отображаются в карточках ниже.")
                        st.rerun()

                    if start_px_t2_btn:
                        px_dl = PexelsDownloader(proxy=tab2_proxy or None)
                        p_bar2 = st.progress(0, text="Извлечение точных B-roll тегов из художественных промптов через Gemini...")

                        # 1. Извлекаем теги из художественных описаний
                        prompt_texts = [sc.get("prompt", "") for sc in scenes]
                        broll_queries = px_dl.generate_broll_queries(prompt_texts, style_context=curr_dna.get("style_title") if curr_dna else "")

                        # 2. Скачиваем видео
                        success_dl = 0
                        total_s = len(scenes)
                        for s_idx, sc in enumerate(scenes):
                            sc_num = sc.get("index", s_idx + 1)
                            dest_v = pm.visuals_dir / f"scene_{sc_num:03d}.mp4"

                            if dest_v.exists() and not t2_overwrite:
                                success_dl += 1
                                p_bar2.progress(int((s_idx + 1) / total_s * 100), text=f"Кадр {sc_num}/{total_s}: видео уже есть ({dest_v.name})")
                                continue

                            q_word = broll_queries[s_idx] if s_idx < len(broll_queries) else "cinematic documentary"
                            p_bar2.progress(int((s_idx + 1) / total_s * 100), text=f"Кадр {sc_num}/{total_s}: поиск на Pexels: '{q_word}'...")

                            found = px_dl.search_videos(q_word, limit=3)
                            if not found:
                                short_q = " ".join(q_word.split()[:2])
                                if short_q != q_word:
                                    found = px_dl.search_videos(short_q, limit=2)

                            if found:
                                p_bar2.progress(int((s_idx + 1) / total_s * 100), text=f"Кадр {sc_num}/{total_s}: загрузка 1080p MP4...")
                                if px_dl.download_video_file(found[0]["download_url"], dest_v):
                                    success_dl += 1

                        # Синхронизируем с таймлайном для пошагового монтажа
                        PexelsDownloader.sync_prompts_to_timeline(pm.project_dir, step_seconds=step_seconds)
                        p_bar2.progress(100, text=f"✅ Готово! Успешно скачано {success_dl} из {total_s} видео.")
                        st.success(f"🎉 Пакетная загрузка завершена! Скачано **{success_dl} / {total_s} роликов**. Они автоматически привязаны к проекту и доступны в Пошаговом монтаже!")
                        st.rerun()

                st.subheader(f"📋 Полная монтажная раскадровка с таймкодами (Кадров: {len(scenes)})")

                filter_choice = st.radio(
                    "Фильтр материалов:",
                    [
                        f"Все материалы ({len(scenes)})",
                        f"🎬 Только ВИДЕО (Nano Banana — {len(v_scenes)} шт)",
                        f"📸 Только ФОТО (Gemini / Nano Banana — {len(p_scenes)} шт)"
                    ],
                    horizontal=True
                )

                if "ВИДЕО" in filter_choice:
                    filtered_scenes = v_scenes
                elif "ФОТО" in filter_choice:
                    filtered_scenes = p_scenes
                else:
                    filtered_scenes = scenes

                st.info(f"Отображено планов: {len(filtered_scenes)}. Нажмите иконку копирования в правом верхнем углу любого блока:")

                t2_page_size = 25
                total_f = len(filtered_scenes)
                if total_f > t2_page_size:
                    n_p2 = math.ceil(total_f / t2_page_size)
                    p2_opts = [f"Кадры {p*t2_page_size + 1} – {min((p+1)*t2_page_size, total_f)}" for p in range(n_p2)]
                    p2_opts.append(f"Показать все ({total_f})")
                    col_t2_p1, col_t2_p2 = st.columns([2, 3])
                    with col_t2_p1:
                        sel_p2 = st.selectbox("📄 Страница раскадровки:", p2_opts, index=0, key="t2_page_sel")
                    if "Показать все" in sel_p2:
                        show_scenes = filtered_scenes
                    else:
                        p2_idx = p2_opts.index(sel_p2)
                        show_scenes = filtered_scenes[p2_idx*t2_page_size : min((p2_idx+1)*t2_page_size, total_f)]
                else:
                    show_scenes = filtered_scenes

                t2_cached_cand = PexelsDownloader.load_cached_candidates(pm.project_dir)

                for sc in show_scenes:
                    m_type = sc["media_type"]
                    badge = "🎬 ВИДЕО (Nano Banana Video)" if m_type == "ВИДЕО" else "📸 ФОТО (Nano Banana Image / Gemini)"

                    with st.expander(f"{badge} — {sc['title']}", expanded=True if sc['index'] <= 3 else False):
                        if sc.get("placement"):
                            st.caption(f"📍 **Куда ставить в ролике:** {sc['placement']}")
                        if sc.get("prompt"):
                            col_pr1, col_pr2 = st.columns([4, 1.2])
                            with col_pr1:
                                st.caption("Промпт для генерации:")
                            with col_pr2:
                                if st.button("🔄 Новый вариант", key=f"btn_re_p_{sc['index']}", use_container_width=True, help="Сгенерировать альтернативный промпт для этого кадра"):
                                    with st.spinner("Создаем альтернативный промпт..."):
                                        try:
                                            pg = PromptGenerator(model_name=model_name)
                                            alt_p = pg.generate_single_prompt(sc['title'], sc['prompt'], style=style_val)
                                            updated_prompts = saved_prompts.replace(sc['prompt'], alt_p)
                                            pm.save_prompts(updated_prompts)
                                            st.success("Промпт кадра обновлен!")
                                            st.rerun()
                                        except Exception as pe:
                                            st.error(f"Ошибка: {pe}")
                            st.code(sc['prompt'], language="text")

                            # Превью прикрепленного видео Pexels (если скачано)
                            v_candidate = pm.visuals_dir / f"scene_{sc['index']:03d}.mp4"
                            if v_candidate.exists():
                                st.caption("🎬 **Текущее прикреплённое видео (Pexels):**")
                                st.video(str(v_candidate))

                            # Показываем найденные варианты Pexels для выбора
                            cands_list = t2_cached_cand.get(str(sc['index']), [])
                            if cands_list:
                                st.caption("🎬 **Варианты видео Pexels (выберите подходящее):**")
                                for c_i, c_v in enumerate(cands_list):
                                    with st.container(border=True):
                                        col_tv1, col_tv2 = st.columns([1, 2])
                                        with col_tv1:
                                            if c_v.get("thumb_bytes"):
                                                st.image(c_v["thumb_bytes"], use_container_width=True)
                                            elif c_v.get("preview_url"):
                                                st.image(c_v["preview_url"], use_container_width=True)
                                        with col_tv2:
                                            st.markdown(f"**{c_v.get('title', 'Video')}**")
                                            st.caption(f"⏱️ {c_v.get('duration', 0)} сек • {c_v.get('width', 0)}p")
                                            if st.button(f"📥 Выбрать вариант #{c_i+1}", key=f"t2_pick_btn_{sc['index']}_{c_i}", type="primary"):
                                                with st.spinner("Скачивание видеоклипа..."):
                                                    dest_f = pm.visuals_dir / f"scene_{sc['index']:03d}.mp4"
                                                    cur_dl = PexelsDownloader(proxy=st.session_state.get("pexels_proxy_input") or None)
                                                    if cur_dl.download_video_file(c_v["download_url"], dest_f):
                                                        PexelsDownloader.sync_prompts_to_timeline(pm.project_dir)
                                                        st.success("Видео выбрано и прикреплено к кадру!")
                                                        st.rerun()

            with st.expander("📄 Посмотреть полный исходный текст раскадровки (prompts.md)"):
                st.markdown(saved_prompts)

        st.divider()
        st.subheader("📸 Парсер архивных фото со страницы статьи / расследования (URL)")
        st.caption("Извлекайте реальные архивные фото, лица участников дела, скриншоты карт и судебную хронику прямо со страницы статьи в интернете (с обходом блокировок и фильтрацией мусора):")

        # Пробуем автоматически извлечь сохраненный URL статьи из raw_material
        default_art_url = ""
        saved_raw_for_url = pm.load_raw_material()
        url_match = re.search(r'Источник:\s*(https?://[^\s]+)', saved_raw_for_url)
        if url_match:
            default_art_url = url_match.group(1).strip()

        c_art_url1, c_art_url2 = st.columns([4, 1.2])
        with c_art_url1:
            article_img_url_input = st.text_input(
                "Ссылка на статью для извлечения фото:",
                value=default_art_url,
                placeholder="https://holod.media/2026/08/28/roditeli-zamuchili-doch-izgonyaya-besov/",
                key="article_img_url_input"
            )
        with c_art_url2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            btn_find_article_photos = st.button("🔍 Найти фото в статье", key="btn_find_article_photos", type="secondary", use_container_width=True)

        if "article_photos_results" not in st.session_state:
            st.session_state.article_photos_results = []
            st.session_state.article_photos_title = ""

        if btn_find_article_photos and article_img_url_input.strip():
            with st.spinner("Загружаем страницу и извлекаем все контентные фото с подписями..."):
                img_res = ArticleParser.parse_article_images(article_img_url_input.strip())
                if img_res.get("success") and img_res.get("photos"):
                    st.session_state.article_photos_results = img_res["photos"]
                    st.session_state.article_photos_title = img_res.get("title", "")
                    st.success(f"Найдено фото в статье: **{len(img_res['photos'])}** шт. ({img_res.get('source_method', '')})")
                else:
                    st.warning(f"Не удалось найти иллюстрации: {img_res.get('error', 'Фотографии не обнаружены.')}")

        if st.session_state.article_photos_results:
            st.markdown(f"**Найдено иллюстраций в статье «{st.session_state.article_photos_title}»: {len(st.session_state.article_photos_results)} шт.**")

            c_bulk1, c_bulk2 = st.columns([2, 3])
            with c_bulk1:
                if st.button(f"📥 Сохранить ВСЕ найденные фото ({len(st.session_state.article_photos_results)} шт) в проект", key="btn_save_all_article_photos", type="primary", use_container_width=True):
                    with st.spinner("Скачиваем и сохраняем все иллюстрации в visuals/..."):
                        saved_count = 0
                        for p in st.session_state.article_photos_results:
                            t_path = pm.visuals_dir / p["filename"]
                            if ArticleParser.download_image(p["url"], t_path):
                                saved_count += 1
                        st.success(f"✅ Успешно сохранено {saved_count} фото в папку visuals/ проекта!")
                        st.rerun()

            photo_cols = st.columns(3)
            for p_idx, p_item in enumerate(st.session_state.article_photos_results):
                with photo_cols[p_idx % 3]:
                    st.image(p_item["url"], use_container_width=True)
                    st.caption(f"**{p_item['caption']}**")

                    c_p_save1, c_p_save2 = st.columns([2, 1])
                    with c_p_save1:
                        target_p_name = st.text_input("Имя файла:", value=p_item["filename"], key=f"art_fname_{p_idx}")
                    with c_p_save2:
                        st.write("")
                        if st.button("📥 В проект", key=f"btn_art_save_{p_idx}", use_container_width=True):
                            t_path = pm.visuals_dir / target_p_name
                            if ArticleParser.download_image(p_item["url"], t_path):
                                st.success(f"Сохранено: {target_p_name}!")
                                st.rerun()
                            else:
                                st.error("Не удалось скачать фото.")

        st.divider()
        st.subheader("🔎 Поиск реальных фото и архивных кадров (Google / Bing / Яндекс / Wiki)")
        st.caption("Мгновенно находите и сохраняйте в проект архивные фото, лица участников дела, вещдоки и B-roll кадры в высоком разрешении без генерации:")

        # Быстрый выбор запроса из раскадровки или произвольный ввод
        scene_titles = ["-- Ввести произвольный запрос --"]
        if saved_prompts and 'scenes' in locals() and scenes:
            scene_titles.extend([f"{s['title']}" for s in scenes])

        c_search1, c_search2, c_search3 = st.columns([3, 2, 1])
        with c_search1:
            selected_scene_preset = st.selectbox("Привязать к сцене из раскадровки:", scene_titles, index=0)
            default_q = ""
            if selected_scene_preset != "-- Ввести произвольный запрос --":
                clean_q = re.sub(r'\(.*?\)', '', selected_scene_preset)
                clean_q = re.sub(r'Сцена\s*\d+:?', '', clean_q).strip('— -:\t')
                default_q = clean_q.strip()

            search_query = st.text_input("Поисковый запрос:", value=default_q, placeholder="например: James Webb telescope space, Silicon Valley documentary, vintage archive photo...")

        with c_search2:
            engine_map = {
                "🚀 Искать везде (Bing + Яндекс + Wiki)": "all",
                "🔍 Bing Images (Full HD, 1080p)": "bing",
                "🔴 Яндекс Картинки (Лица и хроника)": "yandex",
                "🌐 Google Images (Google API)": "google",
                "🏛️ Wikimedia Commons (Архивы)": "wikimedia"
            }
            engine_label = st.selectbox("Поисковая система:", list(engine_map.keys()), index=0)
            selected_engine = engine_map[engine_label]

        with c_search3:
            limit_count = st.number_input("Кол-во фото:", min_value=3, max_value=24, value=9, step=3)
            search_btn = st.button("🔎 Найти фото", type="primary", use_container_width=True)

        if not config.GOOGLE_SEARCH_API_KEY and selected_engine == "google":
            st.warning("⚠️ Ключ Google API не указан в .env. Используйте Bing или Яндекс (работают сразу без ключей) либо добавьте GOOGLE_SEARCH_API_KEY и GOOGLE_SEARCH_CX в .env.")

        if "web_search_results" not in st.session_state:
            st.session_state.web_search_results = []

        if search_btn and search_query.strip():
            with st.spinner(f"Ищем кадры по запросу «{search_query}»..."):
                searcher = WebImageSearcher()
                res = searcher.search(search_query.strip(), engine=selected_engine, limit=int(limit_count))
                st.session_state.web_search_results = res
                if not res:
                    st.warning("По данному запросу ничего не найдено. Попробуйте изменить формулировку (например, на английском языке).")

        if st.session_state.web_search_results:
            st.write(f"Найдено фото: **{len(st.session_state.web_search_results)}**")
            search_cols = st.columns(3)
            for s_idx, item in enumerate(st.session_state.web_search_results):
                with search_cols[s_idx % 3]:
                    st.image(item["thumb_url"], use_container_width=True)
                    st.caption(f"**{item['source']}** • {item['title'][:55]}")

                    suggested_name = f"web_{s_idx+1:02d}_{re.sub(r'[^a-zA-Z0-9]', '_', search_query[:15]).strip('_')}.jpg"
                    if selected_scene_preset != "-- Ввести произвольный запрос --":
                        s_idx_m = re.search(r'Сцена\s*(\d+)', selected_scene_preset)
                        if s_idx_m:
                            suggested_name = f"scene_{int(s_idx_m.group(1)):02d}_web_{s_idx+1}.jpg"

                    save_col1, save_col2 = st.columns([2, 1])
                    with save_col1:
                        target_name = st.text_input("Имя файла:", value=suggested_name, key=f"fname_{s_idx}")
                    with save_col2:
                        st.write("")
                        if st.button("📥 В проект", key=f"btn_save_{s_idx}", use_container_width=True):
                            try:
                                searcher = WebImageSearcher()
                                out_path = pm.visuals_dir / target_name
                                searcher.download_image(item["image_url"], out_path, thumb_url=item.get("thumb_url"))
                                st.success(f"Сохранено: {target_name}!")
                                st.rerun()
                            except Exception as dl_err:
                                st.error(f"Ошибка скачивания: {dl_err}")

        st.divider()
        st.subheader("📥 Загрузка готовых файлов в проект (Drag & Drop)")
        st.caption("Перетащите скачанные из Gemini Web или Nano Banana файлы — они автоматически сохранятся в папку visuals/ проекта:")
        
        uploaded_visuals = st.file_uploader(
            "Перетащите файлы сюда (PNG, JPG, WEBP, MP4)",
            type=["png", "jpg", "jpeg", "webp", "mp4"],
            accept_multiple_files=True
        )
        if uploaded_visuals:
            for up_file in uploaded_visuals:
                dest = pm.visuals_dir / up_file.name
                dest.write_bytes(up_file.read())
            st.success(f"Сохранено файлов: {len(uploaded_visuals)}!")
            st.rerun()

        st.divider()
        st.subheader("📁 Галерея медиафайлов проекта")
        st.write(f"Папка на диске: `{pm.visuals_dir.resolve()}`")

        # Галерея файлов из папки visuals
        existing_images = sorted(list(pm.visuals_dir.glob("*.png")) + list(pm.visuals_dir.glob("*.jpg")) + list(pm.visuals_dir.glob("*.jpeg")) + list(pm.visuals_dir.glob("*.webp")))
        existing_videos = sorted(list(pm.visuals_dir.glob("*.mp4")))
        
        if existing_images or existing_videos:
            st.write(f"В проекте: **{len(existing_images)} фото**, **{len(existing_videos)} видео**")
            cols = st.columns(3)
            for idx, img_path in enumerate(existing_images):
                with cols[idx % 3]:
                    st.image(str(img_path), caption=img_path.name, width="stretch")
                    with open(img_path, "rb") as f_img:
                        st.download_button(
                            f"⬇️ Скачать",
                            data=f_img.read(),
                            file_name=img_path.name,
                            mime="image/jpeg",
                            key=f"dl_img_{img_path.name}_{idx}"
                        )
            for v_path in existing_videos:
                st.video(str(v_path))
        else:
            st.info("В папке visuals пока нет файлов. Скопируйте промпты выше, сгенерируйте в Gemini Web / Nano Banana и перетащите сюда.")

# Вкладка 3: Озвучка TTS
with tab_tts:
    st.subheader("3. Студийная озвучка (TTS)")
    st.caption("Автоматически очищает текст от режиссерских пометок и создает готовую дикторскую начитку в MP3")
    
    current_script = pm.load_script()
    if not current_script:
        st.warning("Сценарий не найден. Сначала создайте сценарий на вкладке 1.")
    else:
        c_eng1, c_eng2 = st.columns([1.2, 1.8])
        with c_eng1:
            tts_engine_choice = st.radio(
                "🎙️ Движок озвучки:",
                ["🌟 Google AI Studio (Gemini 3.8 Flash TTS)", "⚡ Microsoft Edge TTS"],
                index=0,
                help="Google AI Studio TTS использует новейшие эмоциональные нейро-голоса Gemini (Charon, Fenrir, Puck и др.) с живой кинематографичной интонацией. Edge TTS — классический бас Дмитрия."
            )
        is_gemini_engine = "Google" in tts_engine_choice

        with c_eng2:
            if is_gemini_engine:
                voices = TTSSynthesizer.list_available_gemini_voices()
                voice_map = {f"{v['name']}": v['id'] for v in voices}
                selected_voice_label = st.selectbox("Голос Gemini (Google AI Studio):", list(voice_map.keys()), index=0)
                st.caption("ℹ️ *Бесплатный тариф Google AI Studio имеет суточный лимит 10 запросов на аудио. Для безлимитной озвучки без ограничений используйте Edge TTS.*")
            else:
                voices = TTSSynthesizer.list_available_russian_voices()
                voice_map = {f"{v['name']}": v['id'] for v in voices}
                selected_voice_label = st.selectbox("Голос Edge TTS:", list(voice_map.keys()), index=0)
                st.caption("⚡ *Microsoft Edge TTS: полностью бесплатный, без ограничений по длине и числу запросов.*")
            selected_voice_id = voice_map[selected_voice_label]

        # Загружаем или формируем чистый текст для озвучки
        saved_voiceover = pm.load_voiceover_clean()
        if not saved_voiceover:
            saved_voiceover = TTSSynthesizer.clean_voiceover_text(current_script)
            pm.save_voiceover_clean(saved_voiceover)

        st.subheader("📝 Чистый текст диктора для начитки")
        st.caption("Здесь оставлена только человеческая речь: без таблиц, без таймкодов, без пометок SFX и без служебных символов.")

        voiceover_text = st.text_area(
            "Текст, который будет озвучен (можно редактировать перед озвучкой):",
            value=saved_voiceover,
            height=260,
            help="Голос прочитает строго этот текст слово в слово без произнесения знаков и пометок."
        )

        c_v1, c_v2 = st.columns([1, 1])
        with c_v1:
            if st.button("🔄 Обновить текст начитки из сценария"):
                fresh_clean = TTSSynthesizer.clean_voiceover_text(current_script)
                pm.save_voiceover_clean(fresh_clean)
                st.success("Текст начитки заново извлечен и очищен из сценария!")
                st.rerun()
        with c_v2:
            if voiceover_text != saved_voiceover:
                if st.button("💾 Сохранить изменения в тексте начитки"):
                    pm.save_voiceover_clean(voiceover_text)
                    st.success("Изменения сохранены!")
                    st.rerun()

        words = len(voiceover_text.split())
        est_min = round(words / 135, 1)
        st.write(f"📊 Объем для начитки: **{words:,} слов** (примерно **{est_min} мин** непрерывного звучания, {len(voiceover_text):,} знаков)")

        # Выбор режима озвучки: единым файлом или по частям (3-4 части)
        st.markdown("#### 🎧 Режим синтеза речи")
        tts_mode = st.radio(
            "Как озвучивать текст:",
            [
                "⚡ Разбить на 4 части с авто-склейкой в единый MP3 (Рекомендуется для больших текстов)",
                "🎙️ Озвучить весь текст единым потоком (Для небольших текстов до 1500 слов)",
                "🧪 Озвучить тестовый фрагмент (Первые 200 слов для быстрой проверки)"
            ],
            index=0 if words > 1500 else 1,
            help="Режим разбивки на части гарантирует 100% стабильность соединения с Microsoft TTS без тайм-аутов и обрывов длинных файлов."
        )

        num_parts_choice = 4
        if "Разбить на" in tts_mode:
            c_part_opt1, c_part_opt2 = st.columns([1, 2])
            with c_part_opt1:
                num_parts_choice = st.selectbox("Количество частей:", [2, 3, 4, 5], index=2, help="Текст делится строго по границам абзацев без потери слов, каждая часть озвучивается отдельно, а затем они бесшовно склеиваются в единый голос.")

        with st.expander("⚡ Настройки турбо-ускорения озвучки", expanded=False):
            c_sp1, c_sp2 = st.columns(2)
            with c_sp1:
                if is_gemini_engine:
                    tts_concurrency = st.slider("Параллельных потоков Gemini:", min_value=1, max_value=3, value=2, help="Для Google AI Studio Free Tier рекомендуется 1-2 потока во избежание лимитов (3 RPM).")
                else:
                    tts_concurrency = st.slider("Параллельных потоков Edge:", min_value=1, max_value=6, value=4, help="Для Edge TTS 4 потока дают максимальную скорость.")
            with c_sp2:
                tts_use_cache = st.checkbox("Умный кэш фрагментов", value=True, help="Сохраняет аудио готовых блоков. При повторном запуске или правке части текста неизмененные фрагменты загружаются мгновенно (0 сек).")

        dual_voiceover_mode = False
        if is_gemini_engine:
            dual_voiceover_mode = st.checkbox(
                "👥 Озвучить сразу в двух версиях: Milo (Мужской) + Nika (Женский) Podcast",
                value=False,
                help="Сгенерирует 2 полноценных аудиофайла (voiceover_milo.mp3 и voiceover_nika.mp3), чтобы вы могли сравнить оба голоса или использовать их в монтаже."
            )

        btn_start_tts = st.button("🚀 Начать озвучку", type="primary", use_container_width=True)

        if btn_start_tts:
            progress_bar = st.progress(0, text="Подготовка к озвучке...")
            status_text = st.empty()

            if dual_voiceover_mode:
                target_milo = pm.get_audio_path("voiceover_milo.mp3")
                target_nika = pm.get_audio_path("voiceover_nika.mp3")
                target_full = pm.get_audio_path("voiceover_full.mp3")

                try:
                    # 1. Озвучка Milo (Podcast)
                    status_text.info("🎙️ Озвучиваем вариант 1/2: **Milo (Мужской, Podcast)**...")
                    progress_bar.progress(10, text="Озвучиваем версию Milo (Podcast)...")
                    tts_milo = TTSSynthesizer(voice="Milo", engine="gemini", style="podcast", concurrency=tts_concurrency)

                    def on_milo_progress(cur, tot, prev):
                        pct = int((cur / max(1, tot)) * 48)
                        progress_bar.progress(pct, text=f"Milo (Podcast): фрагмент {cur}/{tot} ({pct}%)")

                    tts_milo.synthesize_to_file(voiceover_text, target_milo, progress_callback=on_milo_progress, use_cache=tts_use_cache)

                    # 2. Озвучка Nika (Podcast)
                    status_text.info("🎙️ Озвучиваем вариант 2/2: **Nika (Женский, Podcast)**...")
                    progress_bar.progress(50, text="Озвучиваем версию Nika (Podcast)...")
                    tts_nika = TTSSynthesizer(voice="Nika", engine="gemini", style="podcast", concurrency=tts_concurrency)

                    def on_nika_progress(cur, tot, prev):
                        pct = 50 + int((cur / max(1, tot)) * 48)
                        progress_bar.progress(pct, text=f"Nika (Podcast): фрагмент {cur}/{tot} ({pct}%)")

                    tts_nika.synthesize_to_file(voiceover_text, target_nika, progress_callback=on_nika_progress, use_cache=tts_use_cache)

                    # Копируем Milo как основной голос по умолчанию
                    import shutil
                    shutil.copy2(target_milo, target_full)

                    progress_bar.progress(100, text="✅ Обе озвучки (Milo + Nika) успешно готовы!")
                    status_text.empty()
                    st.success(f"🎉 Готово! Созданы оба файла: {target_milo.name} ({target_milo.stat().st_size // 1024} KB) и {target_nika.name} ({target_nika.stat().st_size // 1024} KB)!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка двойной озвучки: {e}")
                st.stop()

            selected_engine = "gemini" if is_gemini_engine else "edge"
            try:
                tts = TTSSynthesizer(voice=selected_voice_id, concurrency=tts_concurrency, engine=selected_engine)
            except TypeError:
                tts = TTSSynthesizer(voice=selected_voice_id)
                tts.engine = selected_engine
                tts.concurrency = tts_concurrency

            if "тестовый фрагмент" in tts_mode:
                words_list = voiceover_text.split()
                text_to_speak = " ".join(words_list[:200])
                target_path = pm.get_audio_path("test_fragment.mp3")

                def on_tts_progress(current: int, total: int, preview: str):
                    if total > 0:
                        pct = min(int((current / total) * 100), 100)
                        progress_bar.progress(pct, text=f"Озвучено {current} из {total} фрагментов ({pct}%)")
                        if preview:
                            status_text.caption(f"🎙️ Озвучивается: *«{preview}»*")

                try:
                    tts.synthesize_to_file(text_to_speak, target_path, progress_callback=on_tts_progress, use_cache=tts_use_cache)
                    progress_bar.progress(100, text="✅ Тестовый фрагмент готов!")
                    status_text.empty()
                    st.success(f"Аудио успешно записано: {target_path.name} ({target_path.stat().st_size // 1024} KB)")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка озвучки: {e}")

            elif "Разбить на" in tts_mode:
                # Интеллектуальное разделение без потери содержания
                parts_data = TTSSynthesizer.split_into_parts(voiceover_text, num_parts=int(num_parts_choice))
                total_parts = len(parts_data)
                part_files: List[Path] = []

                try:
                    for p_idx, part in enumerate(parts_data):
                        p_num = part["part_index"]
                        p_text = part["text"]
                        p_file = pm.get_audio_path(f"voiceover_part_{p_num}.mp3")
                        part_files.append(p_file)

                        status_text.info(f"🎙️ Озвучиваем часть **{p_num}/{total_parts}** ({part['words']} слов, ~{round(part['words']/135, 1)} мин)...")

                        def on_sub_progress(current: int, total: int, preview: str):
                            overall_pct = int(((p_idx + (current / max(1, total))) / total_parts) * 100)
                            progress_bar.progress(min(overall_pct, 98), text=f"Часть {p_num}/{total_parts}: {current}/{total} ({overall_pct}%)")

                        tts.synthesize_to_file(p_text, p_file, progress_callback=on_sub_progress, use_cache=tts_use_cache)

                    # Бесшовная склейка частей в voiceover_full.mp3 через FFmpeg
                    status_text.info("🎛️ Бесшовная склейка частей в единую непрерывную аудиодорожку voiceover_full.mp3...")
                    full_audio_path = pm.get_audio_path("voiceover_full.mp3")
                    TTSSynthesizer.merge_audio_files(part_files, full_audio_path)

                    progress_bar.progress(100, text="✅ Все части озвучены и объединены в voiceover_full.mp3!")
                    status_text.empty()
                    st.success(f"🎉 Полная озвучка готова! {full_audio_path.name} ({full_audio_path.stat().st_size // 1024} KB, частей: {total_parts})")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка озвучки по частям: {e}")

            else:
                # Озвучка единым файлом
                target_path = pm.get_audio_path("voiceover_full.mp3")

                def on_tts_progress(current: int, total: int, preview: str):
                    if total > 0:
                        pct = min(int((current / total) * 100), 100)
                        progress_bar.progress(pct, text=f"Озвучено {current} из {total} фрагментов ({pct}%)")
                        if preview:
                            status_text.caption(f"🎙️ Озвучивается: *«{preview}»*")

                try:
                    tts.synthesize_to_file(voiceover_text, target_path, progress_callback=on_tts_progress, use_cache=tts_use_cache)
                    progress_bar.progress(100, text="✅ Озвучка успешно завершена!")
                    status_text.empty()
                    st.success(f"Аудио успешно записано: {target_path.name} ({target_path.stat().st_size // 1024} KB)")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка озвучки: {e}")

        # Список созданных аудиофайлов
        audio_files = list(pm.audio_dir.glob("*.mp3"))
        if audio_files:
            st.divider()
            st.subheader("Готовые аудиозаписи проекта:")
            for a_file in audio_files:
                st.write(f"🎵 **{a_file.name}** ({a_file.stat().st_size // 1024} KB)")
                st.audio(str(a_file))
                with open(a_file, "rb") as f:
                    st.download_button(
                        f"⬇️ Скачать {a_file.name}",
                        data=f.read(),
                        file_name=a_file.name,
                        mime="audio/mp3",
                        key=f"dl_{a_file.name}"
                    )

# Вкладка 4: Генератор обложек (3 Стиля)
with tab_thumbnails:
    st.subheader("4. 🖼️ Генератор обложек в 3-х фирменных стилях (True Crime)")
    st.caption("Создавайте кликабельные обложки для 3-х каналов из реальных фотографий за пару кликов.")

    # 1. Помощник Gemini: Генерация названий для 3-х каналов и надписей для обложек
    with st.expander("🤖 ИИ-генератор названий для 3-х каналов и текста обложек (Google Gemini)", expanded=False):
        st.markdown("Gemini проанализирует тему или текст сценария и подготовит 3 заголовка для видео и короткие фразы для каждого стиля обложки:")
        
        current_script = pm.load_script()
        default_ai_text = current_script[:2500] if current_script else (topic if 'topic' in locals() and topic else "")
        ai_input_text = st.text_area(
            "Текст сценария или суть истории:",
            value=default_ai_text,
            height=130,
            placeholder="Вставьте сюда текст выпуска или введите кратко суть (кто кого убил, какая улика подвела, в чем конфликт)...",
            key="thumb_ai_input"
        )
        if st.button("⚡ Сгенерировать названия и текст обложек для 3-х каналов", type="primary", key="btn_gen_3_ch_titles"):
            if not ai_input_text.strip():
                st.error("Пожалуйста, введите текст истории.")
            else:
                with st.spinner("Gemini подбирает кликабельные заголовки и фразы под 3 стиля..."):
                    try:
                        pkg_gen = PackagingGenerator(model_name=model_name)
                        three_pkg_res = pkg_gen.generate_3_styles_package(ai_input_text)
                        st.session_state["three_styles_package_result"] = three_pkg_res
                    except Exception as e:
                        st.error(f"Ошибка: {e}")

        if "three_styles_package_result" in st.session_state:
            st.markdown(st.session_state["three_styles_package_result"])

    st.divider()

    # 2. Выбор стиля
    style_choice = st.radio(
        "Выберите стиль обложки:",
        [
            "🔴 Стиль №1: Красный неон (1 фото — герои с красным ореолом на мрачном ч/б фоне + красно-белый текст)",
            "🟡 Стиль №2: Сплит-скрин (2 фото — цветной коллаж 50/50 + сочный желтый текст с 8px обводкой)",
            "⬛ Стиль №3: Герой + 2 улики (3 фото — лицо по центру + 2 предмета по бокам + плашка сверху)"
        ],
        index=0
    )

    col_inputs, col_preview = st.columns([1, 1], gap="large")

    thumbs_dir = pm.project_dir / "thumbnails"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = Path("scratch")
    temp_dir.mkdir(exist_ok=True)

    with col_inputs:
        st.markdown("#### 1. Загрузка фотографий")

        uploaded_f1 = None
        uploaded_f2 = None
        uploaded_f3 = None

        if "Стиль №1" in style_choice:
            uploaded_f1 = st.file_uploader("Фото героев (семья, пара, портрет):", type=["jpg", "jpeg", "png"], key="upload_s1")
            st.caption("Совет: лучше всего подходят горизонтальные или квадратные фото, где хорошо видны лица и глаза.")
            def_l1, def_l2 = "ПОГ*БИЛ РАДИ", "ЛЮБОВНИЦЫ И ДЕНЕГ"

        elif "Стиль №2" in style_choice:
            col_s2a, col_s2b = st.columns(2)
            with col_s2a:
                uploaded_f1 = st.file_uploader("Фото слева (Преступник/Суд):", type=["jpg", "jpeg", "png"], key="upload_s2_left")
            with col_s2b:
                uploaded_f2 = st.file_uploader("Фото справа (Жертва/Прошлое):", type=["jpg", "jpeg", "png"], key="upload_s2_right")
            uploaded_f_collage = st.file_uploader("ИЛИ готовый склеенный коллаж (1 файл):", type=["jpg", "jpeg", "png"], key="upload_s2_col")
            if uploaded_f_collage:
                uploaded_f1 = uploaded_f_collage
                uploaded_f2 = None
            def_l1, def_l2 = "ИДЕАЛЬНЫЙ ОТЕЦ", "ОКАЗАЛСЯ Д*ШЕГУБ"

        else:
            uploaded_f1 = st.file_uploader("1. Лицо героя (магшот, портрет в суд/камеру):", type=["jpg", "jpeg", "png"], key="upload_s3_face")
            col_s3a, col_s3b = st.columns(2)
            with col_s3a:
                uploaded_f2 = st.file_uploader("2. Улика/предмет слева (оружие, деньги, вещдок):", type=["jpg", "jpeg", "png"], key="upload_s3_left")
            with col_s3b:
                uploaded_f3 = st.file_uploader("3. Улика/сцена справа (CCTV, трекер, дом, полиция):", type=["jpg", "jpeg", "png"], key="upload_s3_right")
            def_l1, def_l2 = "ПРИК*НЧИЛ ЖЕНУ", "И ПРИКИНУЛСЯ ЖЕРТВОЙ"

        st.markdown("#### 2. Текст на обложке")
        c_t1, c_t2 = st.columns(2)
        with c_t1:
            in_line1 = st.text_input("Строка 1 (Завязка):", value=def_l1, key="thumb_text_l1")
        with c_t2:
            in_line2 = st.text_input("Строка 2 (Шокирующий твист):", value=def_l2, key="thumb_text_l2")

        btn_run_thumb = st.button("⚡ Сгенерировать обложку (1280x720)", type="primary", use_container_width=True, key="btn_run_thumb")

    with col_preview:
        st.markdown("#### Результат генерации")

        if btn_run_thumb:
            try:
                with st.spinner("Обработка и генерация обложки..."):
                    if "Стиль №1" in style_choice:
                        if not uploaded_f1:
                            st.error("Пожалуйста, загрузите фотографию для Стиля №1.")
                        else:
                            p1 = temp_dir / f"input_s1_{uploaded_f1.name}"
                            with open(p1, "wb") as f:
                                f.write(uploaded_f1.getbuffer())
                            out_p = thumbs_dir / "thumbnail_style_1.jpg"
                            create_thumbnail_style_1(str(p1), str(out_p), line1_text=in_line1, line2_text=in_line2)
                            st.session_state["last_generated_thumb"] = str(out_p)
                            st.success("Обложка в Стиле №1 успешно создана!")

                    elif "Стиль №2" in style_choice:
                        if uploaded_f1 and uploaded_f2:
                            p1 = temp_dir / f"input_s2_left_{uploaded_f1.name}"
                            p2 = temp_dir / f"input_s2_right_{uploaded_f2.name}"
                            with open(p1, "wb") as f:
                                f.write(uploaded_f1.getbuffer())
                            with open(p2, "wb") as f:
                                f.write(uploaded_f2.getbuffer())
                            out_p = thumbs_dir / "thumbnail_style_2.jpg"
                            create_thumbnail_style_2_collage((str(p1), str(p2)), str(out_p), line1_text=in_line1, line2_text=in_line2)
                            st.session_state["last_generated_thumb"] = str(out_p)
                            st.success("Обложка в Стиле №2 успешно создана!")
                        elif uploaded_f1:
                            p1 = temp_dir / f"input_s2_col_{uploaded_f1.name}"
                            with open(p1, "wb") as f:
                                f.write(uploaded_f1.getbuffer())
                            out_p = thumbs_dir / "thumbnail_style_2.jpg"
                            create_thumbnail_style_2_collage(str(p1), str(out_p), line1_text=in_line1, line2_text=in_line2)
                            st.session_state["last_generated_thumb"] = str(out_p)
                            st.success("Обложка в Стиле №2 успешно создана!")
                        else:
                            st.error("Пожалуйста, загрузите 2 фото (слева и справа) или 1 готовый коллаж.")

                    else:
                        if not (uploaded_f1 and uploaded_f2 and uploaded_f3):
                            st.error("Пожалуйста, загрузите все 3 фотографии (лицо и 2 предмета).")
                        else:
                            p_face = temp_dir / f"input_s3_face_{uploaded_f1.name}"
                            p_left = temp_dir / f"input_s3_left_{uploaded_f2.name}"
                            p_right = temp_dir / f"input_s3_right_{uploaded_f3.name}"
                            with open(p_face, "wb") as f:
                                f.write(uploaded_f1.getbuffer())
                            with open(p_left, "wb") as f:
                                f.write(uploaded_f2.getbuffer())
                            with open(p_right, "wb") as f:
                                f.write(uploaded_f3.getbuffer())
                            out_p = thumbs_dir / "thumbnail_style_3.jpg"
                            create_thumbnail_style_3(str(p_face), str(p_left), str(p_right), str(out_p), line1_text=in_line1, line2_text=in_line2)
                            st.session_state["last_generated_thumb"] = str(out_p)
                            st.success("Обложка в Стиле №3 успешно создана!")
            except Exception as e:
                st.error(f"Ошибка при создании обложки: {e}")

        # Показ последней сгенерированной или существующей обложки
        active_thumb = st.session_state.get("last_generated_thumb")
        if not active_thumb:
            # Ищем любую сохраненную обложку в проекте
            existing_thumbs = list(thumbs_dir.glob("*.jpg"))
            if existing_thumbs:
                active_thumb = str(existing_thumbs[-1])

        if active_thumb and Path(active_thumb).exists():
            st.image(active_thumb, caption="Готовая обложка (YouTube 1280x720)", use_container_width=True)
            with open(active_thumb, "rb") as file_data:
                st.download_button(
                    label="📥 Скачать готовую обложку (JPG)",
                    data=file_data,
                    file_name=Path(active_thumb).name,
                    mime="image/jpeg",
                    use_container_width=True
                )
        else:
            st.info("Здесь появится готовая обложка после нажатия кнопки «Сгенерировать обложку».")

    # Галерея созданных обложек проекта
    saved_project_thumbs = sorted(list(thumbs_dir.glob("*.jpg")))
    if saved_project_thumbs:
        st.divider()
        st.markdown("#### 📂 Все обложки этого проекта:")
        cols_gal = st.columns(min(len(saved_project_thumbs), 3))
        for idx, t_path in enumerate(saved_project_thumbs):
            with cols_gal[idx % len(cols_gal)]:
                st.image(str(t_path), caption=t_path.name, use_container_width=True)
                with open(t_path, "rb") as f_d:
                    st.download_button(
                        label=f"Скачать {t_path.name}",
                        data=f_d,
                        file_name=t_path.name,
                        mime="image/jpeg",
                        key=f"dl_gal_{idx}"
                    )

# Вкладка 5: Файлы проекта
with tab_files:
    st.subheader(f"5. 📂 Файлы и скачивание готового релиза: {pm.slug}")
    st.write(f"Папка на диске: `{pm.project_dir.resolve()}`")

    # Быстрый блок скачивания готового видео (1 файл)
    f_video_tab = pm.project_dir / "final_video.mp4"
    if f_video_tab.exists() and f_video_tab.stat().st_size > 10000:
        with st.container(border=True):
            st.markdown("### 🎬 Главный релизный файл (Финальное видео):")
            c_fv_c1, c_fv_c2 = st.columns([1.5, 1])
            with c_fv_c1:
                st.video(str(f_video_tab))
            with c_fv_c2:
                v_size_mb = f_video_tab.stat().st_size / (1024 * 1024)
                v_dur_str = format_duration(get_audio_duration(f_video_tab))
                st.markdown(f"**Название:** `{pm.slug}_final.mp4`")
                st.markdown(f"**Хронометраж:** `{v_dur_str}`")
                st.markdown(f"**Размер файла:** `{v_size_mb:.1f} MB`")
                st.write("")
                with open(f_video_tab, "rb") as vf_tab:
                    st.download_button(
                        f"📥 СКАЧАТЬ ФИНАЛЬНОЕ ВИДЕО ({v_size_mb:.1f} MB)",
                        data=vf_tab.read(),
                        file_name=f"{pm.slug}_final.mp4",
                        mime="video/mp4",
                        type="primary",
                        use_container_width=True,
                        key="tab_files_dl_final_video"
                    )

    # Скачивание всего проекта единым ZIP-архивом
    with st.expander("📦 Скачать весь проект в 1 ZIP-архив (видео, аудио, сценарий, промпты)", expanded=False):
        import io
        import zipfile
        if st.button("📦 Сформировать ZIP-архив проекта", key="btn_create_project_zip"):
            with st.spinner("Упаковка файлов проекта в ZIP..."):
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in pm.project_dir.rglob("*"):
                        if f.is_file() and not f.name.endswith(".zip"):
                            zf.write(f, arcname=f.relative_to(pm.project_dir))
                zip_buffer.seek(0)
                zip_bytes = zip_buffer.getvalue()
                st.download_button(
                    label=f"⬇️ Скачать архив `{pm.slug}_project.zip` ({len(zip_bytes)//1024} KB)",
                    data=zip_bytes,
                    file_name=f"{pm.slug}_project.zip",
                    mime="application/zip",
                    key="btn_dl_project_zip"
                )

    st.divider()
    st.markdown("#### Список всех файлов проекта на сервере:")
    files = list(pm.project_dir.rglob("*"))
    file_data = []
    for f in files:
        if f.is_file():
            file_data.append({
                "Файл": f.relative_to(pm.project_dir).as_posix(),
                "Размер (КБ)": round(f.stat().st_size / 1024, 1),
            })
    st.dataframe(file_data, width="stretch")
