"""产品反馈保存、幂等提交与私有截图读取。"""

import asyncio
import hashlib
import warnings
from io import BytesIO
from uuid import UUID, uuid5

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from yuxi.repositories.product_feedback_repository import ProductFeedbackRepository
from yuxi.storage.minio.client import MinIOClient
from yuxi.utils.datetime_utils import utc_now_naive

FEEDBACK_BUCKET = "product-feedback"


class ProductFeedbackService:
    """截图在私有对象桶中保存，反馈成功由数据库提交确认。"""

    def __init__(self, db, storage=None):
        self.db = db
        self.repo = ProductFeedbackRepository(db)
        self.storage = storage or MinIOClient()

    async def upload(self, feedback_id, slot, user, data):
        """上传单张截图，同编号、位置和内容的重试返回同一回执。"""
        clean, media_type, extension = await asyncio.to_thread(prepare_feedback_image, data)
        digest = hashlib.sha256(clean).hexdigest()
        row = await self.repo.locked(feedback_id)
        if row and row.user_id != user.id:
            raise HTTPException(404, "反馈不存在")
        if row is None:
            row = await self.repo.create(feedback_id, user.id)
        previous = next((image for image in row.images if image["slot"] == slot), None)
        if previous:
            if previous["digest"] != digest:
                raise HTTPException(409, "图片已变更，请重新提交反馈")
            return {"upload_id": previous["id"], "slot": slot}
        if row.status != "draft":
            raise HTTPException(409, "反馈已经提交")
        image_id = str(uuid5(UUID(feedback_id), f"{slot}:{digest}"))
        object_name = f"{user.id}/{feedback_id}/{image_id}.{extension}"
        await self.storage.aupload_file(FEEDBACK_BUCKET, object_name, clean, content_type=media_type)
        row.images = [
            *row.images,
            {"id": image_id, "slot": slot, "digest": digest, "object": object_name, "media_type": media_type},
        ]
        await self.db.commit()
        return {"upload_id": image_id, "slot": slot}

    async def submit(self, feedback_id, user, content, image_ids):
        """同提交编号只保存一个最终结果；不同内容的重放返回冲突。"""
        row = await self.repo.locked(feedback_id)
        if row and row.user_id != user.id:
            raise HTTPException(404, "反馈不存在")
        if row is None:
            row = await self.repo.create(feedback_id, user.id)
        actual_ids = [image["id"] for image in sorted(row.images, key=lambda image: image["slot"])]
        if image_ids != actual_ids:
            raise HTTPException(422, "图片尚未上传完成，请重试")
        if row.status == "submitted":
            if row.content != content:
                raise HTTPException(409, "该提交编号已保存其他内容")
        else:
            row.content = content
            row.status = "submitted"
            row.submitted_at = utc_now_naive()
            await self.db.commit()
        return feedback_view(row)

    async def read(self, feedback_id, user):
        """本人和管理人员可以读取反馈，其他账号返回不存在。"""
        row = await self.repo.get(feedback_id)
        if not row or (row.user_id != user.id and user.role not in {"admin", "superadmin"}):
            raise HTTPException(404, "反馈不存在")
        return row

    async def image(self, feedback_id, image_id, user):
        """权限核对通过后读取私有截图，不返回对象存储地址。"""
        row = await self.read(feedback_id, user)
        image = next((item for item in row.images if item["id"] == image_id), None)
        if image is None:
            raise HTTPException(404, "图片不存在")
        data = await self.storage.adownload_file(FEEDBACK_BUCKET, image["object"])
        return data, image["media_type"]


def feedback_view(row):
    """只投影意见和受鉴权保护的图片路径。"""
    return {
        "id": row.id,
        "status": row.status,
        "content": row.content,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "images": [
            {"id": image["id"], "path": f"/api/product-feedback/{row.id}/images/{image['id']}"}
            for image in sorted(row.images, key=lambda image: image["slot"])
        ],
    }


def prepare_feedback_image(data):
    """实际解码并重编码截图，限制尺寸并移除原文件元信息。"""
    if not data or len(data) > 5 * 1024 * 1024:
        raise HTTPException(422, "每张图片需小于等于5MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"} or source.width * source.height > 20_000_000:
                    raise ValueError("unsupported image")
                source.load()
                image = ImageOps.exif_transpose(source)
                image.thumbnail((2048, 2048))
                output = BytesIO()
                image.convert("RGB").save(output, format="JPEG", quality=88)
                return output.getvalue(), "image/jpeg", "jpg"
    except (
        ValueError,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as exc:
        raise HTTPException(422, "请选择有效的PNG、JPEG或WebP图片（不超过2000万像素）") from exc
