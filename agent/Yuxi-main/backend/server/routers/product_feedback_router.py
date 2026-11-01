"""账号产品反馈与私有截图协议。"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Path, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_admin_user, get_db, get_required_user
from yuxi.services.product_feedback_service import ProductFeedbackService, feedback_view
from yuxi.storage.postgres.models_business import User
from yuxi.utils.upload_utils import read_upload_with_limit


def private_response(response: Response):
    """意见正文和截图均禁止共享缓存。"""
    response.headers["Cache-Control"] = "private, no-store"


product_feedback = APIRouter(
    prefix="/product-feedback",
    tags=["product-feedback"],
    dependencies=[Depends(private_response)],
)


class SubmitProductFeedback(BaseModel):
    """只接收客户端提交编号、意见与当前编号的图片回执。"""

    model_config = ConfigDict(extra="forbid")
    id: UUID
    content: str = Field(min_length=1, max_length=200)
    image_ids: list[UUID] = Field(default_factory=list, max_length=3)

    @field_validator("content", mode="before")
    @classmethod
    def trim_content(cls, value):
        """空白不构成有效意见，长度按实际提交内容验证。"""
        return value.strip() if isinstance(value, str) else value


@product_feedback.post("/{feedback_id}/images/{slot}")
async def upload_feedback_image(
    feedback_id: UUID,
    slot: int = Path(ge=0, le=2),
    file: UploadFile = File(...),
    user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """逐张上传截图以兼容微信单文件 multipart。"""
    data = await read_upload_with_limit(file, max_size_bytes=5 * 1024 * 1024, too_large_message="每张图片不能超过5MB")
    return await ProductFeedbackService(db).upload(str(feedback_id), slot, user, data)


@product_feedback.post("")
async def submit_feedback(
    payload: SubmitProductFeedback,
    user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """数据库提交成功后返回稳定反馈编号。"""
    return await ProductFeedbackService(db).submit(
        str(payload.id),
        user,
        payload.content,
        [str(image_id) for image_id in payload.image_ids],
    )


@product_feedback.get("")
async def list_feedback(
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """管理员分页查询已收到的产品意见。"""
    rows = await ProductFeedbackService(db).repo.submitted(offset, limit)
    return {"items": [{**feedback_view(row), "user_id": row.user_id} for row in rows]}


@product_feedback.get("/{feedback_id}")
async def read_feedback(
    feedback_id: UUID,
    user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """回读已经保存的意见，受账号归属约束。"""
    return feedback_view(await ProductFeedbackService(db).read(str(feedback_id), user))


@product_feedback.get("/{feedback_id}/images/{image_id}")
async def read_feedback_image(
    feedback_id: UUID,
    image_id: UUID,
    user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """私有截图经鉴权读取并禁止共享缓存。"""
    data, media_type = await ProductFeedbackService(db).image(str(feedback_id), str(image_id), user)
    return Response(
        data, media_type=media_type, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    )
