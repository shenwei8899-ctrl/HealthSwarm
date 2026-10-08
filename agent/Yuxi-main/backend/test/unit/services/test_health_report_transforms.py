"""像素位置与角点几何为独立 oracle，不以另一份处理器作为期望值。"""

import io
import math
from uuid import uuid4

import pytest
from PIL import Image
from pydantic import ValidationError

from yuxi.services.health_media_service import prepare_upload
from yuxi.services.health_vision_types import HealthVisionError, ReportPage, ReportPreparationInput


def synthetic_image(orientation=1):
    """四个象限有明确颜色；伪造私有 EXIF 用于检测副本去元数据。"""
    image = Image.new("RGB", (120, 160))
    for box, color in (
        ((0, 0, 60, 80), "red"),
        ((60, 0, 120, 80), "green"),
        ((0, 80, 60, 160), "blue"),
        ((60, 80, 120, 160), "yellow"),
    ):
        image.paste(color, box)
    exif = Image.Exif()
    exif[274], exif[270] = orientation, "synthetic-private-comment"
    output = io.BytesIO()
    image.save(output, "PNG", exif=exif)
    return output.getvalue()


@pytest.mark.parametrize("orientation", range(1, 9))
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_exif_and_quarter_turn_matrix_matches_pixels(orientation, rotation):
    """原象限中心经矩阵映射后的真实像素颜色须一致。"""
    source = synthetic_image(orientation)
    _, pages = prepare_upload(source, "report", ReportPreparationInput(rotation=rotation))
    page = pages[0]
    with Image.open(io.BytesIO(page["data"])) as processed:
        assert processed.size == (page["width"], page["height"])
        assert not processed.getexif() and not processed.info
        a, b, c, d, e, f = page["source_to_processed"]
        for x, y, color in (
            (30, 40, (255, 0, 0)),
            (90, 40, (0, 128, 0)),
            (30, 120, (0, 0, 255)),
            (90, 120, (255, 255, 0)),
        ):
            px, py = a * (x + 0.5) + b * (y + 0.5) + c, d * (x + 0.5) + e * (y + 0.5) + f
            assert processed.getpixel((math.floor(px), math.floor(py))) == color
    assert page["source_space"] == "encoded_image"
    assert (page["source_width"], page["source_height"]) == (120, 160)
    assert page["exif_orientation"] == orientation and page["rotation"] == rotation
    assert Image.open(io.BytesIO(source)).getexif()[270] == "synthetic-private-comment"


@pytest.mark.parametrize("angle", [-10, -2.5, 2.5, 10])
@pytest.mark.parametrize("rotation", [0, 90])
@pytest.mark.parametrize("orientation", range(1, 9))
def test_deskew_canvas_contains_all_source_corners_and_pixels(angle, rotation, orientation):
    """正负人工角度不裁切，已知内点与空白边缘均从像素回读。"""
    _, pages = prepare_upload(
        synthetic_image(orientation), "report", ReportPreparationInput(rotation=rotation, deskew_angle=angle)
    )
    page = pages[0]
    a, b, c, d, e, f = page["source_to_processed"]
    with Image.open(io.BytesIO(page["data"])) as processed:
        for x, y in ((0, 0), (120, 0), (0, 160), (120, 160)):
            px, py = a * x + b * y + c, d * x + e * y + f
            assert -1e-8 <= px <= processed.width + 1e-8 and -1e-8 <= py <= processed.height + 1e-8
        px, py = a * 30.5 + b * 40.5 + c, d * 30.5 + e * 40.5 + f
        assert processed.getpixel((math.floor(px), math.floor(py))) == (255, 0, 0)
        assert processed.getpixel((0, 0)) == (255, 255, 255)
    assert page["deskew_angle"] == angle


@pytest.mark.parametrize("angle", [0, 2.5])
def test_pdf_document_rotation_has_explicit_rendered_pixel_source(angle):
    """PDF 文档方向先渲染；源宽高是两倍页像素，不能冒充 PDF 点坐标。"""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=120, height=160).rotate(90)
    original = io.BytesIO()
    writer.write(original)
    mime, pages = prepare_upload(original.getvalue(), "report", ReportPreparationInput(rotation=90, deskew_angle=angle))
    page = pages[0]
    assert mime == "application/pdf"
    assert page["source_space"] == "pdf_rendered_page"
    assert (page["source_width"], page["source_height"]) == (320, 240)
    radians = math.radians(angle)
    expected = (
        math.ceil(240 * math.cos(radians) + 320 * math.sin(radians)),
        math.ceil(320 * math.cos(radians) + 240 * math.sin(radians)),
    )
    with Image.open(io.BytesIO(page["data"])) as processed:
        assert processed.size == expected and not processed.info
    a, b, c, d, e, f = page["source_to_processed"]
    for x, y in ((0, 0), (320, 0), (0, 240), (320, 240)):
        px, py = a * x + b * y + c, d * x + e * y + f
        assert -1e-8 <= px <= page["width"] + 1e-8 and -1e-8 <= py <= page["height"] + 1e-8


@pytest.mark.parametrize(
    "values",
    [
        {"rotation": 1},
        {"rotation": True},
        {"rotation": "90"},
        {"rotation": 90.0},
        {"deskew_angle": 11},
        {"deskew_angle": -11},
        {"deskew_angle": True},
        {"deskew_angle": float("nan")},
        {"deskew_angle": float("inf")},
    ],
)
def test_invalid_transform_parameters_rejected(values):
    """非有限、超界或偷偷转换类型的参数不进入像素处理。"""
    with pytest.raises(ValidationError):
        ReportPreparationInput(**values)


def test_meal_transform_rejected_and_expanded_pixel_limit(monkeypatch):
    """饮食用途不能借用报告变换，扩展画布仍受原像素额度保护。"""
    with pytest.raises(HealthVisionError, match="report_transform_invalid"):
        prepare_upload(synthetic_image(), "meal", ReportPreparationInput(rotation=90))
    monkeypatch.setattr("yuxi.services.health_media_service.MAX_PIXELS", 20000)
    with pytest.raises(HealthVisionError, match="image_too_large"):
        prepare_upload(synthetic_image(), "report", ReportPreparationInput(deskew_angle=10))


def test_affine_metadata_required_and_legacy_page_stays_readable():
    """已有页面缺少新字段可读取，新的仿射契约不能缺尺寸或含 NaN。"""
    legacy = dict(
        page_index=0,
        width=120,
        height=160,
        transform="identity_after_orientation",
        upload_id=uuid4(),
        upload_page_index=0,
    )
    assert ReportPage(**legacy).source_to_processed is None
    with pytest.raises(ValidationError):
        ReportPage(**{**legacy, "transform": "affine-v1"})
    _, pages = prepare_upload(synthetic_image(), "report")
    valid = {key: value for key, value in pages[0].items() if key != "data"}
    valid.update(upload_id=uuid4(), upload_page_index=0)
    assert ReportPage(**valid).source_to_processed == [1, 0, 0, 0, 1, 0]
    with pytest.raises(ValidationError):
        ReportPage(**{**valid, "source_to_processed": [1, 0, float("nan"), 0, 1, 0]})
