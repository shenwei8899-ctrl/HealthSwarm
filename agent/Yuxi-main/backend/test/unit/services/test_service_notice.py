"""声明版本校验及新处理边界的最小业务证据。"""

from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest
from pydantic import ValidationError

from yuxi.services import service_notice_service as service


def payload(**values):
    return service.NoticeAcknowledgement.model_validate(
        {
            "version": service.NOTICE_VERSION,
            "content_hash": service.NOTICE_HASH,
            "acknowledged": True,
            **values,
        }
    )


def test_public_document_preserves_three_sections_and_explicit_wording():
    document = service.public_notice()
    assert len(document["sections"]) == 3
    assert "不构成医疗建议、诊断或处方" in document["sections"][0]["text"]
    assert "请勿依据本服务调整、暂停或替换任何药物" in document["sections"][1]["text"]
    assert "切勿依赖本服务" in document["sections"][2]["text"]
    assert document["checkbox_text"].startswith("我已阅读并理解")


@pytest.mark.parametrize(
    "values", [{"acknowledged": False}, {"actor_uid": "someone"}, {"acknowledged_at": "2026-11-22"}]
)
def test_no_false_acknowledgement_or_client_selected_identity(values):
    with pytest.raises(ValidationError):
        payload(**values)


@pytest.mark.parametrize(
    "data, code",
    [
        (None, "SERVICE_NOTICE_REQUIRED"),
        (payload(version="old"), "SERVICE_NOTICE_CHANGED"),
        (payload(content_hash="0" * 64), "SERVICE_NOTICE_CHANGED"),
    ],
)
def test_missing_and_changed_documents_require_reading_again(data, code):
    with pytest.raises(HTTPException) as error:
        service.validate_acknowledgement(data)
    assert error.value.detail["code"] == code


@pytest.mark.asyncio
async def test_unconfirmed_account_cannot_start_health_processing(monkeypatch):
    status = AsyncMock(return_value={"acknowledged": False})
    monkeypatch.setattr(service, "notice_status", status)
    with pytest.raises(HTTPException) as error:
        await service.require_service_notice(object(), "synthetic-actor")
    assert error.value.detail["code"] == "SERVICE_NOTICE_REQUIRED"
    assert status.await_args.args[1] == "synthetic-actor"


@pytest.mark.asyncio
async def test_confirmed_account_passes_without_a_family(monkeypatch):
    monkeypatch.setattr(service, "notice_status", AsyncMock(return_value={"acknowledged": True}))
    await service.require_service_notice(object(), "synthetic-actor")
