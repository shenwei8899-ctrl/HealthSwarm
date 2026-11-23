"""注册前声明读取与本人声明确认接口。"""

from fastapi import APIRouter, Depends, Response

from server.utils.auth_middleware import get_db, get_required_user
from yuxi.services.service_notice_service import (
    NoticeAcknowledgement,
    acknowledge_notice,
    notice_status,
    public_notice,
)

service_notice = APIRouter(tags=["service-notice"])


@service_notice.get("/service-notice")
async def read_service_notice(response: Response):
    """未登录也可阅读，不包含账号信息。"""
    response.headers["Cache-Control"] = "no-store"
    return public_notice()


@service_notice.get("/account/service-notice")
async def read_acknowledgement(response: Response, user=Depends(get_required_user), db=Depends(get_db)):
    """确认状态只返回当前认证账号。"""
    response.headers["Cache-Control"] = "no-store"
    return await notice_status(db, user.uid)


@service_notice.post("/account/service-notice")
async def confirm_service_notice(
    data: NoticeAcknowledgement, response: Response, user=Depends(get_required_user), db=Depends(get_db)
):
    """确认记录由请求事务提交。"""
    response.headers["Cache-Control"] = "no-store"
    result = await acknowledge_notice(db, user.uid, data)
    await db.commit()
    return result
