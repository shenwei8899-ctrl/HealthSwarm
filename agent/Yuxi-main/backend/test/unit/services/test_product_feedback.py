"""产品意见图片边界和协议校验。"""

from io import BytesIO

import pytest
from fastapi import HTTPException
from PIL import Image

from yuxi.services.product_feedback_service import prepare_feedback_image


def test_feedback_reencodes_image_and_discards_text_metadata():
    """截图内容可读，原始文件尾随内容不进入对象存储。"""
    original = BytesIO()
    Image.new("RGB", (40, 30), "blue").save(original, format="PNG")
    data, mime, extension = prepare_feedback_image(original.getvalue() + b"synthetic-private-metadata")
    assert b"synthetic-private-metadata" not in data
    with Image.open(BytesIO(data)) as image:
        assert image.size == (40, 30)
        assert image.format == "JPEG"
    assert (mime, extension) == ("image/jpeg", "jpg")


@pytest.mark.parametrize("data", [b"", b"not-a-photo", b"x" * (5 * 1024 * 1024 + 1)])
def test_feedback_rejects_invalid_or_oversized_image(data):
    """伪造后缀和超限图片在对象写入之前失败。"""
    with pytest.raises(HTTPException) as error:
        prepare_feedback_image(data)
    assert error.value.status_code == 422
