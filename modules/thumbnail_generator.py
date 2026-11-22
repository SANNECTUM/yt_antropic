import os
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw, ImageFont, ImageOps
import numpy as np

def create_split_screen(img1_path: str, img2_path: str, target_size=(1280, 720), divider_width=4, divider_color=(255, 255, 255)) -> Image.Image:
    """
    Автоматически собирает сплит-скрин (коллаж 50/50) из двух отдельных фотографий.
    """
    target_w, target_h = target_size
    half_w = target_w // 2

    def crop_half(path):
        im = Image.open(path).convert("RGB")
        ratio = half_w / target_h
        im_ratio = im.width / im.height
        if im_ratio > ratio:
            new_w = int(im.height * ratio)
            off = (im.width - new_w) // 2
            im = im.crop((off, 0, off + new_w, im.height))
        else:
            new_h = int(im.width / ratio)
            off = int((im.height - new_h) * 0.25)
            off = max(0, min(off, im.height - new_h))
            im = im.crop((0, off, im.width, off + new_h))
        return im.resize((half_w, target_h), Image.Resampling.LANCZOS)

    left_img = crop_half(img1_path)
    right_img = crop_half(img2_path)

    collage = Image.new("RGB", target_size)
    collage.paste(left_img, (0, 0))
    collage.paste(right_img, (half_w, 0))

    if divider_width > 0:
        draw = ImageDraw.Draw(collage)
        x_start = half_w - divider_width // 2
        draw.rectangle([x_start, 0, x_start + divider_width, target_h], fill=divider_color)

    return collage


def create_thumbnail_style_1(
    input_image_path: str,
    output_image_path: str,
    line1_text: str = "ПОГ*БИЛ РАДИ",
    line2_text: str = "ЛЮБОВНИЦЫ И ДЕНЕГ",
    font_choice: str = "ariblk",
    glow_color=(255, 20, 20),
    target_size=(1280, 720)
):
    """
    Стиль №1: Драматический мрачный True Crime
    - Ч/б затемненный фон
    - Цветные герои с красным неоновым ореолом
    - Плавный черный градиент снизу
    - Яркий неоновый алый + белый текст Arial Black
    """
    import rembg

    img = Image.open(input_image_path).convert("RGBA")
    target_w, target_h = target_size
    img_ratio = img.width / img.height
    target_ratio = target_w / target_h

    if img_ratio > target_ratio:
        new_w = int(img.height * target_ratio)
        offset = (img.width - new_w) // 2
        img = img.crop((offset, 0, offset + new_w, img.height))
    else:
        new_h = int(img.width / target_ratio)
        offset = int((img.height - new_h) * 0.25)
        offset = max(0, min(offset, img.height - new_h))
        img = img.crop((0, offset, img.width, offset + new_h))

    img = img.resize(target_size, Image.Resampling.LANCZOS)

    session = rembg.new_session("u2netp")
    foreground = rembg.remove(img, session=session)

    bg_gray = ImageOps.grayscale(img.convert("RGB")).convert("RGB")
    bg_dark = ImageEnhance.Brightness(bg_gray).enhance(0.42)
    bg_contrast = ImageEnhance.Contrast(bg_dark).enhance(1.35)
    bg_blur = bg_contrast.filter(ImageFilter.GaussianBlur(radius=4)).convert("RGBA")

    alpha = foreground.split()[3]
    red_layer = Image.new("RGBA", target_size, (*glow_color, 255))
    glow_wide = alpha.filter(ImageFilter.GaussianBlur(radius=30))
    glow_tight = alpha.filter(ImageFilter.GaussianBlur(radius=8))

    w_arr = np.array(glow_wide, dtype=np.float32)
    t_arr = np.array(glow_tight, dtype=np.float32)
    combined = np.clip(w_arr * 0.95 + t_arr * 1.5, 0, 255).astype(np.uint8)
    glow_mask = Image.fromarray(combined)

    glow_layer = Image.new("RGBA", target_size, (0, 0, 0, 0))
    glow_layer.paste(red_layer, (0, 0), glow_mask)

    fg_rgb = foreground.convert("RGB")
    fg_contrast = ImageEnhance.Contrast(fg_rgb).enhance(1.15)
    fg_sharp = ImageEnhance.Sharpness(fg_contrast).enhance(1.3)
    fg_final = fg_sharp.convert("RGBA")
    fg_final.putalpha(alpha)

    composite = Image.alpha_composite(bg_blur, glow_layer)
    composite = Image.alpha_composite(composite, fg_final)

    grad = Image.new("RGBA", target_size, (0, 0, 0, 0))
    draw_grad = ImageDraw.Draw(grad)
    start_y = int(target_h * 0.48)
    for y in range(start_y, target_h):
        p = (y - start_y) / (target_h - start_y)
        a = int(255 * (p ** 1.25))
        draw_grad.line([(0, y), (target_w, y)], fill=(0, 0, 0, a))

    composite = Image.alpha_composite(composite, grad)

    font_file = "C:/Windows/Fonts/ariblk.ttf"
    draw = ImageDraw.Draw(composite)
    max_w = int(target_w * 0.92)

    font_size = 72
    for s in range(76, 38, -2):
        f = ImageFont.truetype(font_file, s)
        w1 = draw.textlength(line1_text, font=f)
        w2 = draw.textlength(line2_text, font=f)
        if max(w1, w2) <= max_w:
            font_size = s
            font = f
            break

    bbox1 = draw.textbbox((0, 0), line1_text, font=font)
    h1 = bbox1[3] - bbox1[1]
    bbox2 = draw.textbbox((0, 0), line2_text, font=font)
    h2 = bbox2[3] - bbox2[1]

    spacing = int(font_size * 0.22)
    total_h = h1 + h2 + spacing
    y_start = target_h - int(target_h * 0.055) - total_h

    def draw_thick(text, y, fill_col):
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        x = (target_w - w) // 2
        draw.text((x, y), text, font=font, fill=(0, 0, 0), stroke_width=6, stroke_fill=(0, 0, 0))
        draw.text((x, y), text, font=font, fill=fill_col, stroke_width=2, stroke_fill=fill_col)

    draw_thick(line1_text.upper(), y_start, (255, 20, 45, 255))
    draw_thick(line2_text.upper(), y_start + h1 + spacing, (255, 255, 255, 255))

    final_output = composite.convert("RGB")
    os.makedirs(os.path.dirname(os.path.abspath(output_image_path)), exist_ok=True)
    final_output.save(output_image_path, "JPEG", quality=95)
    return output_image_path


def create_thumbnail_style_2_collage(
    input_image_or_tuple,
    output_image_path: str,
    line1_text: str = "ИДЕАЛЬНЫЙ ОТЕЦ",
    line2_text: str = "ОКАЗАЛСЯ Д*ШЕГУБ",
    text_color=(255, 230, 0),
    target_size=(1280, 720)
):
    """
    Стиль №2: Коллаж (Сплит-скрин) + Желтый текст с 8px черной обводкой снизу
    """
    target_w, target_h = target_size

    if isinstance(input_image_or_tuple, (list, tuple)) and len(input_image_or_tuple) == 2:
        img = create_split_screen(input_image_or_tuple[0], input_image_or_tuple[1], target_size=target_size)
    else:
        path = input_image_or_tuple[0] if isinstance(input_image_or_tuple, (list, tuple)) else input_image_or_tuple
        im = Image.open(path).convert("RGB")
        img = im.resize(target_size, Image.Resampling.LANCZOS)

    enh_contrast = ImageEnhance.Contrast(img).enhance(1.12)
    enh_color = ImageEnhance.Color(enh_contrast).enhance(1.08)
    base_img = ImageEnhance.Sharpness(enh_color).enhance(1.30)

    font_file = "C:/Windows/Fonts/ariblk.ttf"

    grad = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    d_grad = ImageDraw.Draw(grad)
    start_y = int(target_h * 0.48)
    for y in range(start_y, target_h):
        p = (y - start_y) / (target_h - start_y)
        a = int(225 * (p ** 1.3))
        d_grad.line([(0, y), (target_w, y)], fill=(0, 0, 0, a))

    comp = Image.alpha_composite(base_img.convert("RGBA"), grad)
    draw = ImageDraw.Draw(comp)

    max_w = int(target_w * 0.92)
    font_size = 72
    for s in range(76, 42, -2):
        f = ImageFont.truetype(font_file, s)
        w1 = draw.textlength(line1_text, font=f)
        w2 = draw.textlength(line2_text, font=f)
        if max(w1, w2) <= max_w:
            font_size = s
            font = f
            break

    bbox1 = draw.textbbox((0, 0), line1_text, font=font)
    h1 = bbox1[3] - bbox1[1]
    bbox2 = draw.textbbox((0, 0), line2_text, font=font)
    h2 = bbox2[3] - bbox2[1]

    spacing = int(font_size * 0.20)
    total_h = h1 + h2 + spacing
    y_start = target_h - int(target_h * 0.05) - total_h

    def draw_yellow_bold(text, y):
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        x = (target_w - w) // 2
        draw.text((x, y), text, font=font, fill=(0, 0, 0), stroke_width=8, stroke_fill=(0, 0, 0))
        draw.text((x, y), text, font=font, fill=text_color, stroke_width=2, stroke_fill=text_color)

    draw_yellow_bold(line1_text.upper(), y_start)
    draw_yellow_bold(line2_text.upper(), y_start + h1 + spacing)

    final_output = comp.convert("RGB")
    os.makedirs(os.path.dirname(os.path.abspath(output_image_path)), exist_ok=True)
    final_output.save(output_image_path, "JPEG", quality=95)
    return output_image_path


def create_thumbnail_style_3(
    face_img_path: str,
    item_left_path: str,
    item_right_path: str,
    output_image_path: str,
    line1_text: str = "БАНДА ПОДРОСТКОВ",
    line2_text: str = "СТАЛА КИЛЛЕРАМИ",
    font_file: str = "C:/Windows/Fonts/impact.ttf",
    target_size=(1280, 720)
):
    """
    Стиль №3: Центральное лицо героя + 2 предмета улики/преступления по бокам
    - Черная плашка сверху с ярко-желтым текстом
    - Слева: предмет 1
    - Справа: предмет 2
    - По центру: вырезанный силуэт героя с глубокой тенью
    """
    import rembg

    target_w, target_h = target_size

    # 1. Рассчитываем верхнюю плашку под текст
    test_draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font_size = 72
    font = ImageFont.truetype(font_file, font_size)

    for s in range(78, 44, -2):
        f = ImageFont.truetype(font_file, s)
        w1 = test_draw.textlength(line1_text, font=f)
        w2 = test_draw.textlength(line2_text, font=f)
        if max(w1, w2) <= int(target_w * 0.94):
            font_size = s
            font = f
            break

    bbox1 = test_draw.textbbox((0, 0), line1_text, font=font)
    h1 = bbox1[3] - bbox1[1]
    bbox2 = test_draw.textbbox((0, 0), line2_text, font=font)
    h2 = bbox2[3] - bbox2[1]

    spacing = int(font_size * 0.14)
    pad_top = 18
    pad_bottom = 18
    banner_h = pad_top + h1 + spacing + h2 + pad_bottom

    # 2. Подготовка фоновых предметов (левый и правый)
    bg_h = target_h - banner_h
    half_w = target_w // 2

    def prep_item(path, w, h):
        im = Image.open(path).convert("RGB")
        ratio = w / h
        im_r = im.width / im.height
        if im_r > ratio:
            nw = int(im.height * ratio)
            off = (im.width - nw) // 2
            im = im.crop((off, 0, off + nw, im.height))
        else:
            nh = int(im.width / ratio)
            off = (im.height - nh) // 2
            im = im.crop((0, off, im.width, off + nh))
        im = im.resize((w, h), Image.Resampling.LANCZOS)
        im = ImageEnhance.Contrast(im).enhance(1.15)
        im = ImageEnhance.Brightness(im).enhance(0.75)
        return im

    left_bg = prep_item(item_left_path, half_w, bg_h)
    right_bg = prep_item(item_right_path, half_w, bg_h)

    canvas = Image.new("RGB", (target_w, target_h), (10, 10, 10))
    canvas.paste(left_bg, (0, banner_h))
    canvas.paste(right_bg, (half_w, banner_h))

    d_canvas = ImageDraw.Draw(canvas)
    d_canvas.line([(half_w, banner_h), (half_w, target_h)], fill=(0, 0, 0), width=3)

    # 3. Сегментация лица героя
    face_raw = Image.open(face_img_path).convert("RGBA")
    session = rembg.new_session("u2netp")
    fg_face = rembg.remove(face_raw, session=session)

    face_target_h = int(bg_h * 1.28)
    face_scale = face_target_h / fg_face.height
    face_w = int(fg_face.width * face_scale)
    fg_face = fg_face.resize((face_w, face_target_h), Image.Resampling.LANCZOS)

    fg_rgb = fg_face.convert("RGB")
    fg_rgb = ImageEnhance.Contrast(fg_rgb).enhance(1.18)
    fg_rgb = ImageEnhance.Sharpness(fg_rgb).enhance(1.35)
    fg_face_enh = fg_rgb.convert("RGBA")
    fg_face_enh.putalpha(fg_face.split()[3])

    face_x = (target_w - face_w) // 2
    face_y = target_h - face_target_h

    face_alpha = fg_face_enh.split()[3]
    shadow_mask = face_alpha.filter(ImageFilter.GaussianBlur(radius=18))
    shadow_layer = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    shadow_black = Image.new("RGBA", (face_w, face_target_h), (0, 0, 0, 210))
    shadow_layer.paste(shadow_black, (face_x, face_y), shadow_mask)

    comp = Image.alpha_composite(canvas.convert("RGBA"), shadow_layer)
    comp.paste(fg_face_enh, (face_x, face_y), fg_face_enh)

    # 4. Верхняя черная плашка и желтый текст
    draw = ImageDraw.Draw(comp)
    draw.rectangle([0, 0, target_w, banner_h], fill=(12, 12, 12, 255))

    def draw_line(text, y):
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        x = (target_w - w) // 2
        draw.text((x, y), text, font=font, fill=(255, 230, 0, 255))

    draw_line(line1_text.upper(), pad_top)
    draw_line(line2_text.upper(), pad_top + h1 + spacing)

    final_output = comp.convert("RGB")
    os.makedirs(os.path.dirname(os.path.abspath(output_image_path)), exist_ok=True)
    final_output.save(output_image_path, "JPEG", quality=95)
    return output_image_path
