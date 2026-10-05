from __future__ import annotations

import warnings
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError


class ImageOperationError(ValueError):
    """An image or one of its requested operations is invalid."""


def inspect_image(source: bytes) -> tuple[str, tuple[int, int]]:
    if not source:
        raise ImageOperationError("El archivo no contiene una imagen.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(source)) as opened:
                image_format = (opened.format or "").upper()
                opened.load()
                oriented = ImageOps.exif_transpose(opened)
                dimensions = oriented.size
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ImageOperationError("No se pudo leer la imagen. Usa JPEG, PNG o WebP.") from error
    if image_format not in {"JPEG", "PNG", "WEBP"}:
        raise ImageOperationError("Usa una imagen JPEG, PNG o WebP.")
    if dimensions[0] * dimensions[1] > 40_000_000:
        raise ImageOperationError("La imagen es demasiado grande para procesarla.")
    return image_format, dimensions


FORMAT_NAMES = {
    "jpg": ("JPEG", "image/jpeg"),
    "jpeg": ("JPEG", "image/jpeg"),
    "png": ("PNG", "image/png"),
    "webp": ("WEBP", "image/webp"),
}


def _positive_integer(operation: dict[str, Any], name: str) -> int:
    value = operation.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ImageOperationError(f"El valor de {name} debe ser un entero positivo.")
    return value


def _coordinate(operation: dict[str, Any], name: str) -> int:
    value = operation.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ImageOperationError(f"El valor de {name} debe ser un entero igual o mayor que cero.")
    return value


def _watermark(image: Image.Image, operation: dict[str, Any]) -> Image.Image:
    text = operation.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 80:
        raise ImageOperationError("La marca de agua debe tener entre 1 y 80 caracteres.")

    position = operation.get("position", "bottom-right")
    positions = {"top-left", "top-right", "bottom-left", "bottom-right", "center"}
    if position not in positions:
        raise ImageOperationError("La posición de la marca de agua no es válida.")

    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_size = max(12, min(40, base.width // 24))
    font = (
        ImageFont.truetype("DejaVuSans.ttf", font_size)
        if _font_available()
        else ImageFont.load_default()
    )
    bounds = draw.textbbox((0, 0), text, font=font, stroke_width=1)
    text_width = bounds[2] - bounds[0]
    text_height = bounds[3] - bounds[1]
    margin = max(8, base.width // 40)

    if position == "top-left":
        x, y = margin, margin
    elif position == "top-right":
        x, y = base.width - text_width - margin, margin
    elif position == "bottom-left":
        x, y = margin, base.height - text_height - margin
    elif position == "center":
        x, y = (base.width - text_width) // 2, (base.height - text_height) // 2
    else:
        x, y = base.width - text_width - margin, base.height - text_height - margin

    draw.text(
        (max(margin, x), max(margin, y)),
        text,
        fill=(255, 255, 255, 210),
        font=font,
        stroke_width=1,
        stroke_fill=(0, 0, 0, 160),
    )
    return Image.alpha_composite(base, overlay)


def _font_available() -> bool:
    try:
        ImageFont.truetype("DejaVuSans.ttf", 12)
    except OSError:
        return False
    return True


def transform_image(
    source: bytes, operations: list[dict[str, Any]]
) -> tuple[bytes, str, tuple[int, int]]:
    if not operations:
        raise ImageOperationError("Agrega por lo menos una transformación.")

    try:
        with Image.open(BytesIO(source)) as opened:
            opened.load()
            source_format = (opened.format or "PNG").upper()
            image = ImageOps.exif_transpose(opened).copy()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ImageOperationError("No se pudo leer la imagen. Usa JPEG, PNG o WebP.") from error

    output_format = source_format if source_format in {"JPEG", "PNG", "WEBP"} else "PNG"
    for operation in operations:
        kind = operation.get("type")
        if kind == "resize":
            width = _positive_integer(operation, "width")
            height = _positive_integer(operation, "height")
            image = ImageOps.contain(image, (width, height), method=Image.Resampling.LANCZOS)
        elif kind == "crop":
            x = _coordinate(operation, "x")
            y = _coordinate(operation, "y")
            width = _positive_integer(operation, "width")
            height = _positive_integer(operation, "height")
            if x + width > image.width or y + height > image.height:
                raise ImageOperationError(
                    "El recorte solicitado está fuera de los límites de la imagen."
                )
            image = image.crop((x, y, x + width, y + height))
        elif kind == "watermark":
            image = _watermark(image, operation)
        elif kind == "format":
            requested_format = operation.get("format")
            if (
                not isinstance(requested_format, str)
                or requested_format.lower() not in FORMAT_NAMES
            ):
                raise ImageOperationError("El formato debe ser JPEG, PNG o WebP.")
            output_format = FORMAT_NAMES[requested_format.lower()][0]
        else:
            raise ImageOperationError("La operación solicitada no es válida.")

    if output_format == "JPEG" and image.mode in {"RGBA", "LA", "P"}:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        image = background
    elif output_format in {"PNG", "WEBP"} and image.mode not in {"RGB", "RGBA", "L", "LA"}:
        image = image.convert("RGBA")

    output = BytesIO()
    save_options: dict[str, Any] = {}
    if output_format in {"JPEG", "WEBP"}:
        save_options["quality"] = 85
    image.save(output, format=output_format, **save_options)
    content_type = next(value[1] for value in FORMAT_NAMES.values() if value[0] == output_format)
    return output.getvalue(), content_type, image.size
