from io import BytesIO

import pytest
from PIL import Image, ImageChops

from app.imaging import ImageOperationError, transform_image


def encoded_image(size: tuple[int, int] = (12, 8), color: str = "#246b62") -> bytes:
    image = Image.new("RGB", size, color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_resize_preserves_aspect_ratio() -> None:
    result, content_type, size = transform_image(
        encoded_image(), [{"type": "resize", "width": 6, "height": 6}]
    )

    assert content_type == "image/png"
    assert size == (6, 4)
    assert Image.open(BytesIO(result)).size == (6, 4)


def test_crop_uses_the_requested_rectangle() -> None:
    result, _, size = transform_image(
        encoded_image(), [{"type": "crop", "x": 2, "y": 1, "width": 5, "height": 3}]
    )

    assert size == (5, 3)
    assert Image.open(BytesIO(result)).size == (5, 3)


def test_text_watermark_changes_the_image() -> None:
    source = encoded_image(size=(180, 80), color="#ffffff")
    result, _, _ = transform_image(
        source,
        [{"type": "watermark", "text": "IMAGE LAB", "position": "bottom-right"}],
    )

    with Image.open(BytesIO(source)) as original, Image.open(BytesIO(result)) as marked:
        assert (
            ImageChops.difference(original.convert("RGB"), marked.convert("RGB")).getbbox()
            is not None
        )


def test_format_conversion_changes_encoded_format() -> None:
    result, content_type, size = transform_image(
        encoded_image(), [{"type": "format", "format": "webp"}]
    )

    assert content_type == "image/webp"
    assert size == (12, 8)
    assert Image.open(BytesIO(result)).format == "WEBP"


def test_crop_rejects_a_rectangle_outside_the_image() -> None:
    with pytest.raises(ImageOperationError, match="fuera de los límites"):
        transform_image(
            encoded_image(),
            [{"type": "crop", "x": 10, "y": 0, "width": 5, "height": 5}],
        )


def test_operations_are_applied_in_order() -> None:
    result, _, size = transform_image(
        encoded_image(),
        [
            {"type": "crop", "x": 1, "y": 1, "width": 8, "height": 4},
            {"type": "resize", "width": 16, "height": 16},
        ],
    )

    assert size == (16, 8)
    assert Image.open(BytesIO(result)).size == (16, 8)
