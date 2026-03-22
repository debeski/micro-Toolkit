from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PIL.ImageQt import ImageQt
from PySide6.QtGui import QPixmap

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:
    pass

try:
    from PIL.ExifTags import TAGS
except Exception:
    TAGS = {}

try:
    from dateutil import parser as date_parser
except Exception:
    date_parser = None


SUPPORTED_IMAGE_FILTER = "Image Files (*.jpg *.jpeg *.png *.webp *.heic *.HEIC *.tiff *.bmp)"


def resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    package_root = Path(__file__).resolve().parents[1]
    return str(package_root / "assets" / relative_path)


def load_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        resource_path("fonts/DejaVuSans-Bold.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for font_path in candidates:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, font_size)
            except Exception:
                continue
    return ImageFont.load_default()


def pil_to_pixmap(image: Image.Image, max_size: tuple[int, int] = (640, 420)) -> QPixmap:
    preview = image.copy()
    preview.thumbnail(max_size, Image.Resampling.LANCZOS)
    qimage = ImageQt(preview.convert("RGBA"))
    return QPixmap.fromImage(qimage)


def get_exif_date(image: Image.Image):
    try:
        exif = image.getexif()
        if exif:
            exif_ifd = exif.get_ifd(0x8769)
            if exif_ifd:
                for tag_id in (36867, 36868):
                    if tag_id in exif_ifd:
                        return exif_ifd[tag_id]
            if 306 in exif:
                return exif[306]
        if hasattr(image, "_getexif") and image._getexif():
            legacy = image._getexif()
            for tag_id in (36867, 36868, 306):
                if tag_id in legacy:
                    return legacy[tag_id]
    except Exception:
        return None
    return None


def format_date(value) -> str:
    if not value:
        return datetime.now().strftime("%Y-%m-%d")
    try:
        text = str(value)
        if ":" in text[:10]:
            parts = text.split(" ")[0].split(":")
            if len(parts) == 3:
                return f"{parts[0]}-{parts[1]}-{parts[2]}"
        if date_parser is not None:
            return date_parser.parse(text).strftime("%Y-%m-%d")
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d")


def apply_tag(image: Image.Image, name: str, date_type: str, custom_date_str: str | None = None) -> Image.Image:
    rgba_image = image.convert("RGBA")
    if date_type == "taken":
        final_date = format_date(get_exif_date(image))
    elif date_type == "custom":
        final_date = format_date(custom_date_str)
    else:
        final_date = datetime.now().strftime("%Y-%m-%d")

    width, height = rgba_image.size
    base_size = max(width, height)
    font_size = max(int(base_size * 0.02), 12)
    font = load_font(font_size)
    full_text = f"{name.upper()} - {final_date}"

    drawing = ImageDraw.Draw(rgba_image)
    text_bbox = drawing.textbbox((0, 0), full_text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]

    padding = int(font_size * 0.8)
    rect_width = text_width + padding * 2
    rect_height = text_height + padding * 2
    margin = int(base_size * 0.02)

    rect_x1 = width - rect_width - margin
    rect_y1 = height - rect_height - margin
    rect_x2 = width - margin
    rect_y2 = height - margin

    region = rgba_image.crop((rect_x1, rect_y1, rect_x2, rect_y2)).convert("L")
    pixels = list(region.getdata())
    avg_luminance = sum(pixels) / len(pixels) if pixels else 128

    if avg_luminance > 140:
        background_fill = (0, 0, 0, 160)
        background_outline = (255, 255, 255, 30)
        text_fill = (255, 255, 255, 240)
    else:
        background_fill = (255, 255, 255, 80)
        background_outline = (255, 255, 255, 100)
        text_fill = (255, 255, 255, 240)

    overlay = Image.new("RGBA", rgba_image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    corner_radius = int(font_size * 0.5)
    overlay_draw.rounded_rectangle(
        [rect_x1, rect_y1, rect_x2, rect_y2],
        radius=corner_radius,
        fill=background_fill,
        outline=background_outline,
        width=1,
    )
    overlay_draw.text((rect_x1 + padding, rect_y1 + padding), full_text, font=font, fill=text_fill)
    return Image.alpha_composite(rgba_image, overlay).convert("RGB")


def transform_image(
    image: Image.Image,
    *,
    rotate_value: str | None = None,
    resize_enabled: bool = False,
    resize_type: str = "pixels",
    width_value: str = "",
    height_value: str = "",
    format_value: str | None = None,
) -> tuple[Image.Image, str | None]:
    transformed = image.convert("RGBA")

    if rotate_value:
        if "90" in rotate_value:
            transformed = transformed.rotate(-90, expand=True)
        elif "180" in rotate_value:
            transformed = transformed.rotate(180, expand=True)
        elif "270" in rotate_value:
            transformed = transformed.rotate(-270, expand=True)

    if resize_enabled and width_value.strip() and height_value.strip():
        width_number = float(width_value)
        height_number = float(height_value)
        if resize_type == "percent":
            new_width = int(transformed.width * (width_number / 100.0))
            new_height = int(transformed.height * (height_number / 100.0))
        else:
            new_width = int(width_number)
            new_height = int(height_number)
        if new_width > 0 and new_height > 0 and (new_width != transformed.width or new_height != transformed.height):
            transformed = transformed.resize((new_width, new_height), Image.Resampling.LANCZOS)

    target_format = format_value.lower() if format_value else None
    if transformed.mode == "RGBA" and target_format in {"jpg", "jpeg"}:
        transformed = transformed.convert("RGB")
    elif transformed.mode == "RGBA" and target_format is None:
        transformed = transformed.convert("RGB")
    elif transformed.mode != "RGB" and target_format in {"jpg", "jpeg", "png", "webp"}:
        transformed = transformed.convert("RGB")

    return transformed, target_format


def safe_output_extension(original_path: str, requested_format: str | None = None) -> str:
    if requested_format:
        extension = "." + requested_format.lower().lstrip(".")
    else:
        extension = Path(original_path).suffix.lower() or ".jpg"
    if extension == ".heic":
        return ".jpg"
    if extension == ".jpeg":
        return ".jpg"
    return extension
