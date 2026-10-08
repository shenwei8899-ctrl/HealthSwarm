"""选择页输入严格校验与人工修改保留的独立 oracle。"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.services.health_vision_tasks import merge_report_pages
from yuxi.services.health_vision_types import ReportPayload, ReportReprocessInput, VisionConfigurationInput


@pytest.mark.parametrize("pages", [[], [1, 1], [-1], [20], [True], ["1"], [1.0]])
def test_invalid_reprocess_pages_rejected(pages):
    """页范围、类型和重复项在 wire DTO 边界拒绝。"""
    with pytest.raises(ValidationError):
        ReportReprocessInput(version=1, draft_id=uuid4(), client_request_id=uuid4(), page_indices=pages)


@pytest.mark.parametrize("version", [0, True, 1.0, "1"])
def test_reprocess_version_is_strict_positive_integer(version):
    """避免布尔值或舍入后的版本参与持久化冲突判断。"""
    with pytest.raises(ValidationError):
        ReportReprocessInput(version=version, draft_id=uuid4(), client_request_id=uuid4(), page_indices=[1])


def test_request_normalizes_page_set_and_rejects_external_parameters():
    """页集合排序稳定指纹，客户端不能注入外部模型或对象地址。"""
    data = dict(version=2, draft_id=uuid4(), client_request_id=uuid4(), page_indices=[19, 1])
    assert ReportReprocessInput(**data).page_indices == [1, 19]
    for key in ("model", "object_key", "image_url", "processor"):
        with pytest.raises(ValidationError):
            ReportReprocessInput(**data, **{key: "untrusted"})
    assert VisionConfigurationInput().report_model == ""


def test_merge_only_replaces_selected_evidence_and_preserves_manual_edits():
    """第二页用全局索引 1，人工字段及第一页修改保持完整。"""
    upload_id = str(uuid4())
    page = dict(width=1200, height=1600, rotation=0, transform="identity", upload_id=upload_id)
    fields = []
    for index in (0, 1):
        fields.append(
            dict(
                field_id=str(uuid4()),
                name="葡萄糖",
                value_raw=str(7 + index),
                source="ocr",
                evidence=dict(page_index=index, block_id=f"p{index}-b0", raw_text=f"葡萄糖 {7 + index}"),
            )
        )
    manual = dict(field_id=str(uuid4()), name="人工补充", value_raw="9")
    original = ReportPayload.model_validate(
        dict(
            fields=[*fields, manual],
            excluded_pages=[1],
            pages=[
                {**page, "page_index": 0, "upload_page_index": 0},
                {**page, "page_index": 1, "upload_page_index": 1, "status": "failed", "error_code": "provider_failed"},
            ],
        )
    )
    replacement = ReportPayload.model_validate(
        dict(
            fields=[
                {
                    **fields[1],
                    "field_id": str(uuid4()),
                    "value_raw": "6.8",
                    "evidence": {"page_index": 1, "block_id": "p1-b0", "raw_text": "葡萄糖 6.8"},
                }
            ],
            pages=[{**page, "page_index": 1, "upload_page_index": 1}],
        )
    )
    result = merge_report_pages(original, replacement)
    assert result.fields[0].model_dump() == original.fields[0].model_dump()
    assert result.fields[1].model_dump() == original.fields[2].model_dump()
    assert result.fields[2].value_raw == "6.8" and result.fields[2].evidence.page_index == 1
    assert result.excluded_pages == [1]
    assert [p.status for p in result.pages] == ["ready", "ready"]
    assert original.pages[1].status == "failed" and original.fields[1].value_raw == "8"
