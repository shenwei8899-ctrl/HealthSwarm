"""私有上传真实类型验证及报告页处理副本。"""

import io
import math
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from yuxi.services.health_vision_types import HealthVisionError, ReportPreparationInput

MAX_PIXELS = 25_000_000


def prepare_upload(
    data: bytes, purpose: str, preparation: ReportPreparationInput | None = None
) -> tuple[str, list[dict]]:
    """清除图像元数据，PDF 按原始页序渲染且拒绝加密。"""
    preparation = preparation or ReportPreparationInput()
    if purpose == "meal" and (preparation.rotation or preparation.deskew_angle):
        raise HealthVisionError("report_transform_invalid", "旋转和去倾斜参数仅用于报告处理副本")
    if data.startswith(b"%PDF-"):
        if purpose != "report":
            raise HealthVisionError("unsupported_type", "饮食识图只接受图片", 415)
        if len(data) > 20 * 1024 * 1024:
            raise HealthVisionError("file_too_large", "PDF 不能超过 20MB", 413)
        import pypdfium2 as pdfium
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 20:
                raise HealthVisionError("invalid_pdf", "PDF 须未加密且为 1 至 20 页")
            pages = []
            with pdfium.PdfDocument(data) as document:
                for index in range(len(document)):
                    page = document[index]
                    if page.get_width() * page.get_height() * 4 > MAX_PIXELS:
                        raise HealthVisionError("page_too_large", "PDF 页面尺寸过大")
                    bitmap = page.render(scale=2)
                    image = bitmap.to_pil().convert("RGB")
                    pages.append(_clean_page(image, index, preparation, image.size, 1, "pdf_rendered_page"))
                    if sum(len(item["data"]) for item in pages) > 50 * 1024 * 1024:
                        raise HealthVisionError("processed_file_too_large", "处理后的页图超过 50MB，请拆分报告", 413)
                    image.close()
                    bitmap.close()
                    page.close()
            return "application/pdf", pages
        except HealthVisionError:
            raise
        except Exception:
            raise HealthVisionError("invalid_pdf", "PDF 无法解析，请上传未加密的有效报告") from None
    if len(data) > 10 * 1024 * 1024:
        raise HealthVisionError("file_too_large", "单张图片不能超过 10MB", 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as original:
                if original.format not in {"JPEG", "PNG", "WEBP"} or getattr(original, "n_frames", 1) != 1:
                    raise HealthVisionError("unsupported_type", "只接受 JPG、PNG、WebP 静态图片", 415)
                if min(original.size) < 100:
                    raise HealthVisionError("image_too_small", "图片边长至少为 100 像素，请重新拍摄")
                if original.width * original.height > MAX_PIXELS:
                    raise HealthVisionError("image_too_large", "图片像素尺寸过大", 413)
                mime = Image.MIME[original.format]
                orientation = original.getexif().get(274, 1)
                if orientation not in range(1, 9):
                    orientation = 1
                image = ImageOps.exif_transpose(original).convert("RGB")
                page = _clean_page(image, 0, preparation, original.size, orientation, "encoded_image")
                image.close()
                return mime, [page]
    except HealthVisionError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HealthVisionError("unsupported_type", "文件不是有效图片或像素尺寸过大", 415) from None


def _clean_page(image, index, preparation, source_size, orientation, source_space) -> dict:
    """扩大画布保存处理图；矩阵作用于源像素边缘坐标，不裁切报告。"""
    source_width, source_height = source_size
    exif_matrix = {
        1: [1, 0, 0, 0, 1, 0],
        2: [-1, 0, source_width, 0, 1, 0],
        3: [-1, 0, source_width, 0, -1, source_height],
        4: [1, 0, 0, 0, -1, source_height],
        5: [0, 1, 0, 1, 0, 0],
        6: [0, -1, source_height, 1, 0, 0],
        7: [0, -1, source_height, -1, 0, source_width],
        8: [0, 1, 0, -1, 0, source_width],
    }[orientation]
    angle = math.radians(preparation.rotation + preparation.deskew_angle)
    cosine, sine = round(math.cos(angle), 12), round(math.sin(angle), 12)
    corners = [
        (cosine * x - sine * y, sine * x + cosine * y)
        for x, y in [(0, 0), (image.width, 0), (0, image.height), image.size]
    ]
    left, top = min(x for x, y in corners), min(y for x, y in corners)
    size = (math.ceil(max(x for x, y in corners) - left), math.ceil(max(y for x, y in corners) - top))
    if size[0] * size[1] > MAX_PIXELS:
        raise HealthVisionError("image_too_large", "旋转后的处理页像素尺寸过大，请缩小原图", 413)
    if preparation.deskew_angle:
        # Pillow 读取目标到源的逆矩阵；元数据记录源到目标的正矩阵。
        clean = image.transform(
            size,
            Image.Transform.AFFINE,
            (cosine, sine, cosine * left + sine * top, -sine, cosine, -sine * left + cosine * top),
            resample=Image.Resampling.BICUBIC,
            fillcolor="white",
        )
    elif preparation.rotation:
        clean = image.transpose(
            {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}[
                preparation.rotation
            ]
        )
    else:
        clean = Image.new("RGB", image.size)
        clean.paste(image)
    a, b, c, d, e, f = exif_matrix
    matrix = [
        cosine * a - sine * d,
        cosine * b - sine * e,
        cosine * c - sine * f - left,
        sine * a + cosine * d,
        sine * b + cosine * e,
        sine * c + cosine * f - top,
    ]
    output = io.BytesIO()
    sanitized = Image.new("RGB", clean.size)
    sanitized.paste(clean)
    sanitized.save(output, format="PNG")
    sanitized.close()
    clean.close()
    return {
        "page_index": index,
        "width": size[0],
        "height": size[1],
        "rotation": preparation.rotation,
        "deskew_angle": preparation.deskew_angle,
        "transform": "affine-v1",
        "source_space": source_space,
        "source_width": source_width,
        "source_height": source_height,
        "exif_orientation": orientation,
        "source_to_processed": matrix,
        "data": output.getvalue(),
    }
