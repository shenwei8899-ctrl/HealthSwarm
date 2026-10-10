"""识图不确定性和确定性营养计算的独立负向 oracle。"""

import io
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image, PngImagePlugin
from pydantic import ValidationError

from yuxi.services.health_media_service import prepare_upload
from yuxi.services.health_nutrition_service import calculate_nutrition
from yuxi.services.health_vision_provider import normalize_report_blocks, redact_report_blocks, verify_report_fields
from yuxi.services.health_vision_service import require_editable
from yuxi.services import health_vision_service as service_module
from yuxi.services.health_vision_types import (
    Evidence,
    FoodInput,
    HealthVisionError,
    MealPayload,
    ReportField,
    ReportPayload,
    ReportPage,
    VisionTaskInput,
    VisionConfigurationInput,
)
from yuxi.utils.datetime_utils import utc_now_naive
from datetime import timedelta


@pytest.mark.asyncio
async def test_health_approval_boundaries_refresh_before_reading_model_view(monkeypatch):
    """配置探测和写审批都先刷新，避免独立 worker 的旧供应商视图。"""
    events = []
    cache = Mock()
    cache.refresh.side_effect = lambda: events.append("refresh")
    cache.get_all_specs.side_effect = lambda _kind: events.append("list") or []
    cache.get_model_info.side_effect = lambda _spec: events.append("model") or None
    monkeypatch.setattr(service_module, "model_cache", cache)
    monkeypatch.setattr(service_module, "health_vision_opts", SimpleNamespace(get=AsyncMock(return_value={})))
    monkeypatch.setattr(service_module, "resolve_ocr_task_params", AsyncMock(side_effect=ValueError("synthetic")))
    monkeypatch.setattr(service_module.provider_repository, "get_model_provider", AsyncMock(return_value=None))

    @asynccontextmanager
    async def session_context():
        """只替代本单元测试的食品数量读取，不执行健康业务。"""
        yield type("SyntheticSession", (), {"scalar": AsyncMock(return_value=0)})()

    monkeypatch.setattr(service_module.pg_manager, "get_async_session_context", session_context)
    configuration = await service_module.HealthVisionService().configuration()
    assert events == ["refresh", "list"] and not configuration["consultation"]["available"]
    events.clear()
    data = VisionConfigurationInput(
        consultation_model="synthetic:fixed", policy_version="synthetic", cloud_processing_reviewed=True
    )
    with pytest.raises(HealthVisionError, match="model_not_configured"):
        await service_module.HealthVisionService().configure("synthetic-actor", data)
    assert events == ["refresh"]


def meal(food_id=None, **kwargs):
    """固定就餐时区和独立的手算参数。"""
    item = {
        "item_id": uuid4(),
        "name": "测试食品",
        "food_id": food_id,
        "grams": "150",
        "share_ratio": "0.4",
        "portion_source": "weighed",
        **kwargs,
    }
    return MealPayload(meal_type="lunch", eaten_at="2026-10-04T12:00:00+08:00", items=[item])


def food_record(**kwargs):
    """测试数值仅为 oracle，不作为产品食品数据。"""
    return SimpleNamespace(
        id=str(uuid4()),
        name="合成测试食品",
        source="合成独立手算",
        license="测试用途",
        edition="test",
        dataset_version="test-1",
        cooking_state="熟",
        recipe_estimated=False,
        nutrients={
            "energy_kcal": "200",
            "protein_g": "10",
            "fat_g": "5",
            "carbohydrate_g": "25",
            "sodium_mg": "100",
            **kwargs,
        },
    )


def test_independent_nutrition_oracle_grams_and_share():
    food = food_record()
    result = calculate_nutrition(meal(food.id), {food.id: food})
    # 150g * 40% = 60g；每百克 200kcal、10g 蛋白质。
    assert result["totals"] == {
        "energy_kcal": "120.00",
        "protein_g": "6.00",
        "fat_g": "3.00",
        "carbohydrate_g": "15.00",
        "sodium_mg": "60.00",
    }
    assert result["complete"] and not result["estimated"]
    assert result["sources"][0]["dataset_version"] == "test-1"


def test_missing_nutrient_not_zero_and_estimate_visible():
    food = food_record(protein_g=None)
    result = calculate_nutrition(meal(food.id, portion_source="estimated"), {food.id: food})
    assert result["totals"]["protein_g"] is None
    assert result["totals"]["energy_kcal"] == "120.00"
    assert not result["complete"] and result["estimated"]


@pytest.mark.parametrize(
    "missing",
    [{"share_ratio": None}, {"grams": None}, {"portion_source": "unknown"}, {"food_id": None}, {"excluded": True}],
)
def test_unknown_portion_food_or_no_items_has_no_false_totals(missing):
    food = food_record()
    result = calculate_nutrition(
        meal(food.id, **{key: value for key, value in missing.items() if key != "food_id"})
        if "food_id" not in missing
        else meal(None),
        {food.id: food},
    )
    assert not result["complete"]
    assert all(value is None for value in result["totals"].values())


@pytest.mark.parametrize("invalid", [{"grams": "NaN"}, {"share_ratio": -0.1}, {"share_ratio": 1.1}, {"grams": -1}])
def test_nonfinite_and_invalid_portions_rejected(invalid):
    with pytest.raises(ValidationError):
        meal(**invalid)


def test_duplicate_and_naive_time_rejected():
    payload = meal()
    with pytest.raises(ValidationError):
        MealPayload(meal_type="lunch", eaten_at="2026-10-04T12:00:00", items=[])
    with pytest.raises(ValidationError):
        MealPayload(meal_type="lunch", eaten_at=payload.eaten_at, items=payload.items * 2)
    with pytest.raises(ValidationError):
        VisionTaskInput(member_id=uuid4(), upload_ids=[(upload := uuid4()), upload], client_request_id=uuid4())


def test_manual_cannot_forge_evidence_numeric_or_date():
    field = {"field_id": uuid4(), "name": "血糖", "value_raw": "6.8"}
    for extra in (
        {"value_numeric": "68"},
        {"value_numeric": "NaN"},
        {"observed_at": "昨天"},
        {"source": "ocr"},
        {"evidence": {"page_index": 0, "block_id": "b", "raw_text": "6.8"}},
        {"observation_code": "arbitrary"},
    ):
        with pytest.raises(ValidationError):
            ReportField(**field, **extra)
    report_field = ReportField(**field)
    with pytest.raises(ValidationError):
        ReportPayload(fields=[report_field, report_field])
    with pytest.raises(ValidationError):
        ReportPayload(excluded_pages=[1])


@pytest.mark.parametrize(
    "status,error",
    [
        ("ready", "provider_failed"),
        ("failed", None),
        ("failed", "consent_required"),
        ("failed", "patient-sensitive-text"),
    ],
)
def test_report_page_status_rejects_inconsistent_or_private_failure(status, error):
    """页级失败只公开受控代码，不能把授权失败误记为单页失败。"""
    with pytest.raises(ValidationError):
        ReportPage(
            page_index=0,
            width=120,
            height=120,
            transform="identity",
            upload_id=uuid4(),
            upload_page_index=0,
            status=status,
            error_code=error,
        )


def test_legacy_report_page_defaults_ready_without_claiming_quality():
    """旧页可读取且不会伪造新质量检测记录。"""
    page = ReportPage(page_index=0, width=120, height=120, transform="identity", upload_id=uuid4(), upload_page_index=0)
    assert page.status == "ready" and page.error_code is None and page.quality_flags == []


def test_report_evidence_independent_row_match():
    blocks = [
        {
            "block_id": "p0_b0",
            "page_index": 0,
            "raw_text": "葡萄糖 6.8 mmol/L 3.9-6.1\n蛋白质 68 g/L 60-80",
            "bbox": None,
        }
    ]
    result = verify_report_fields(
        [
            {
                "name": "葡萄糖",
                "value_raw": "6.8",
                "value_numeric": "6.8",
                "unit_raw": "mmol/L",
                "reference_raw": "3.9-6.1",
                "block_id": "p0_b0",
            }
        ],
        blocks,
    )[0]
    assert result["value_numeric"] == "6.8" and result["observed_at"] is None
    assert result["evidence"]["raw_text"] == blocks[0]["raw_text"]
    result = verify_report_fields(
        [{"name": "葡萄糖", "value_raw": "68", "value_numeric": "68", "unit_raw": "g/L", "block_id": "p0_b0"}], blocks
    )[0]
    assert result["value_numeric"] is None and "row_evidence_mismatch" in result["review_flags"]
    for item in ({"name": "葡萄糖", "block_id": "fake"}, {"name": None, "block_id": "p0_b0"}):
        with pytest.raises(HealthVisionError):
            verify_report_fields([item], blocks)


def test_report_comparison_not_coerced_and_pixel_boxes_not_fabricated():
    blocks = normalize_report_blocks(
        [
            {
                "result": {
                    "layoutParsingResults": [
                        {
                            "prunedResult": {
                                "parsing_res_list": [
                                    {"block_content": "血糖 <0.1 mmol/L", "block_bbox": [100, 200, 300, 400]}
                                ]
                            }
                        }
                    ]
                }
            }
        ],
        {"page_index": 1},
    )
    assert blocks[0]["bbox"] is None
    field = verify_report_fields(
        [{"name": "血糖", "value_raw": "<0.1", "value_numeric": "0.1", "unit_raw": "mmol/L", "block_id": "p1_b0"}],
        blocks,
    )[0]
    assert field["value_numeric"] is None
    with pytest.raises(ValidationError):
        Evidence(page_index=0, block_id="b", raw_text="test", bbox=[0.8, 0.8, 0.1, 0.1])


def test_identity_redacted_before_field_model():
    blocks = [
        {"block_id": "a", "raw_text": "姓名 张三"},
        {"block_id": "b", "raw_text": "患者电话 13812345678"},
        {"block_id": "c", "raw_text": "葡萄糖 6.8 张三"},
    ]
    safe = redact_report_blocks(blocks, "张三")
    assert len(safe) == 1 and "张三" not in safe[0]["raw_text"]


def test_real_content_sniff_and_metadata_removed():
    image = Image.new("RGB", (140, 120), "white")
    buffer = io.BytesIO()
    info = PngImagePlugin.PngInfo()
    info.add_text("patient", "synthetic private name")
    image.save(buffer, format="PNG", pnginfo=info)
    mime, pages = prepare_upload(buffer.getvalue(), "meal")
    assert mime == "image/png" and pages[0]["width"] == 140
    with Image.open(io.BytesIO(pages[0]["data"])) as clean:
        assert "patient" not in clean.info
    for data in (b"fake image.jpg", b"<svg></svg>", b"%PDF-broken"):
        with pytest.raises(HealthVisionError):
            prepare_upload(data, "meal")
    with pytest.raises(HealthVisionError, match="file_too_large"):
        prepare_upload(b"x" * (10 * 1024 * 1024 + 1), "report")


def test_invalid_and_encrypted_pdf_rejected():
    from pypdf import PdfWriter

    for pages, encrypted in ((0, False), (21, False), (1, True)):
        pdf = PdfWriter()
        for _ in range(pages):
            pdf.add_blank_page(width=100, height=100)
        if encrypted:
            pdf.encrypt("synthetic-password")
        buffer = io.BytesIO()
        pdf.write(buffer)
        with pytest.raises(HealthVisionError, match="invalid_pdf"):
            prepare_upload(buffer.getvalue(), "report")


def test_publish_requires_approved_nutrient_codes_and_cloud_approval():
    base = dict(
        record_code="test",
        name="synthetic",
        cooking_state="熟",
        source="test",
        license="test only",
        edition="1",
        dataset_version="1",
    )
    for nutrients in ({"calories": 10}, {"energy_kcal": -1}, {"protein_g": "NaN"}):
        with pytest.raises(ValidationError):
            FoodInput(**base, nutrients=nutrients)
    assert FoodInput(**base, nutrients={}).nutrients["energy_kcal"] is None
    with pytest.raises(ValidationError):
        VisionConfigurationInput(meal_model="provider/model")


@pytest.mark.parametrize(
    ("policy_version", "cloud_processing_reviewed"),
    [("", False), ("synthetic-policy-v1", False), ("", True)],
)
def test_purchase_only_model_requires_policy_and_explicit_cloud_approval(policy_version, cloud_processing_reviewed):
    """仅配置采购模型也不能绕过敏感数据云处理审批。"""
    with pytest.raises(ValidationError, match="启用前须确认处理政策与费用限额已经审批"):
        VisionConfigurationInput(
            purchase_model="synthetic:purchase-fixed",
            policy_version=policy_version,
            cloud_processing_reviewed=cloud_processing_reviewed,
        )


def test_approved_purchase_model_and_explicit_disable_remain_valid():
    """明确批准允许配置采购，清空全部模型无需新增云审批。"""
    data = VisionConfigurationInput(
        purchase_model="synthetic:purchase-fixed",
        policy_version="synthetic-policy-v1",
        cloud_processing_reviewed=True,
    )
    assert data.purchase_model == "synthetic:purchase-fixed"
    assert VisionConfigurationInput(purchase_model="").purchase_model == ""


def test_confirmed_stale_and_expired_drafts_not_editable():
    record = SimpleNamespace(review_status="pending_confirmation", version=2, created_at=utc_now_naive())
    with pytest.raises(HealthVisionError, match="version_conflict"):
        require_editable(record, 1)
    record.review_status = "confirmed"
    with pytest.raises(HealthVisionError, match="version_conflict"):
        require_editable(record, 2)
    record.review_status = "pending_confirmation"
    record.created_at -= timedelta(days=8)
    with pytest.raises(HealthVisionError, match="draft_expired"):
        require_editable(record, 2)
