"""账号级健康服务声明及明确阅读确认。"""

import hashlib
import json
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from yuxi.repositories.service_notice_repository import ServiceNoticeRepository

NOTICE_VERSION = "2026-11-22-v1"
NOTICE = {
    "version": NOTICE_VERSION,
    "effective_date": "2026-11-22",
    "title": "服务声明与健康提示",
    "sections": [
        {
            "title": "服务范围",
            "text": (
                "本小程序提供的饮食推荐、食材搭配及营养信息仅供参考，不构成医疗建议、诊断或处方，不能替代"
                "执业医师、注册营养师的面诊、用药指导及个体化医学营养治疗。本服务不针对任何特定疾病提供治"
                "疗或治愈方案。"
            ),
        },
        {
            "title": "慢性病与用药提醒",
            "text": (
                "如您患有高血压、糖尿病、高脂血症、痛风、心血管疾病、肾脏疾病等慢性疾病或相关病症，或正在"
                "服药：请勿依据本服务调整、暂停或替换任何药物，用药须严格遵照医生处方与医嘱。显著改变饮食"
                "结构可能影响药效或疾病指标，实施前请先咨询医生或注册营养师。"
            ),
        },
        {
            "title": "紧急情况",
            "text": (
                "如出现胸痛、严重头晕、意识改变、血糖急剧波动、严重过敏、呼吸困难等紧急情况，请立即就医或"
                "联系急救服务，切勿依赖本服务。"
            ),
        },
    ],
    "checkbox_text": "我已阅读并理解上述提示，知悉本服务仅供参考，不能替代药物与医嘱，不针对任何疾病提供治疗方案。",
}
NOTICE_HASH = hashlib.sha256(
    json.dumps(NOTICE, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()


class NoticeAcknowledgement(BaseModel):
    """只接受用户读到的确定版本，不接受代确认账号和时间。"""

    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1, max_length=80)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    acknowledged: Literal[True]


def public_notice():
    """返回固定正文与摘要供注册前及设置查看。"""
    return {**NOTICE, "content_hash": NOTICE_HASH}


def validate_acknowledgement(data):
    """正文变化需要重新阅读，不自动接受客户端旧版本。"""
    if data is None:
        raise HTTPException(403, {"code": "SERVICE_NOTICE_REQUIRED", "message": "请先阅读并确认服务声明与健康提示"})
    if data.version != NOTICE_VERSION or data.content_hash != NOTICE_HASH or data.acknowledged is not True:
        raise HTTPException(409, {"code": "SERVICE_NOTICE_CHANGED", "message": "服务声明已更新，请重新阅读并确认"})


async def notice_status(session, uid):
    """按账号读取当前版本，家庭和健康资料授权不参与判断。"""
    row = await ServiceNoticeRepository(session).current(uid, NOTICE_VERSION)
    accepted = row is not None and row.content_hash == NOTICE_HASH
    return {
        "version": NOTICE_VERSION,
        "content_hash": NOTICE_HASH,
        "acknowledged": accepted,
        "acknowledged_at": row.acknowledged_at.isoformat() + "Z" if accepted else None,
    }


async def acknowledge_notice(session, uid, data):
    """确认与调用方业务事务一起提交，重复操作保留首次时间。"""
    validate_acknowledgement(data)
    await ServiceNoticeRepository(session).acknowledge(uid, NOTICE_VERSION, NOTICE_HASH)
    result = await notice_status(session, uid)
    if not result["acknowledged"]:
        raise HTTPException(409, {"code": "SERVICE_NOTICE_CHANGED", "message": "声明版本内容不一致，请联系管理员"})
    return result


async def require_service_notice(session, uid):
    """仅在新 AI 处理发起边界使用，历史和订单读取不调用。"""
    if not (await notice_status(session, uid))["acknowledged"]:
        raise HTTPException(403, {"code": "SERVICE_NOTICE_REQUIRED", "message": "请先阅读并确认服务声明与健康提示"})
