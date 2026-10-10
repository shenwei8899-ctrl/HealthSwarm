"""健康识图边界 DTO 与可解释的业务错误。"""

import math
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HEALTH_SCOPES = {
    "report_upload",
    "report_view",
    "profile_edit",
    "profile_view",
    "diet_edit",
    "ai_use",
    "professional_review",
}
NUTRIENTS = {"energy_kcal": "kcal", "protein_g": "g", "fat_g": "g", "carbohydrate_g": "g", "sodium_mg": "mg"}
HEALTH_TASK_TYPES = {"report_extract_v1", "meal_recognize_v1"}
MEAL_PROMPT_VERSION = "health-meal-v2"
ReportPageErrorCode = Literal[
    "provider_unavailable",
    "provider_timeout",
    "provider_failed",
    "provider_job_unavailable",
    "model_schema_invalid",
    "parser_contract_invalid",
    "evidence_invalid",
]


class HealthVisionError(Exception):
    """仅携带可公开的错误代码，不包含模型或患者正文。"""

    def __init__(self, code: str, message: str, status: int = 422):
        self.code, self.message, self.status = code, message, status
        super().__init__(f"{code}: {message}")


class HealthDTO(BaseModel):
    """拒绝额外字段和非有限数的业务输入。"""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class MemberInput(HealthDTO):
    display_name: str = Field(min_length=1, max_length=80)
    relationship_label: str = Field(default="本人", min_length=1, max_length=40)
    authorized: Literal[True]


class GrantInput(HealthDTO):
    actor_uid: str = Field(min_length=1, max_length=100)
    scopes: list[
        Literal[
            "report_upload", "report_view", "profile_edit", "profile_view", "diet_edit", "ai_use", "professional_review"
        ]
    ]


class ConsentInput(HealthDTO):
    purpose: Literal["report", "meal", "consultation", "meal_plan", "diet_analysis", "quality_review", "purchase"]
    accepted: bool
    processor: str = Field(min_length=1, max_length=160)
    policy_version: str = Field(min_length=1, max_length=80)


class ConsultationInput(HealthDTO):
    """绑定创建只接受幂等键，不接受模型、线程或成员覆盖。"""

    client_request_id: UUID


class VisionTaskInput(HealthDTO):
    member_id: UUID
    upload_ids: list[UUID] = Field(min_length=1, max_length=20)
    client_request_id: UUID
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] | None = None
    eaten_at: datetime | None = None

    @field_validator("upload_ids")
    @classmethod
    def unique_uploads(cls, value):
        """重复照片不能重复计餐。"""
        if len(value) != len(set(value)):
            raise ValueError("文件不能重复")
        return value


class Evidence(HealthDTO):
    page_index: int = Field(ge=0, le=19)
    block_id: str = Field(min_length=1, max_length=80)
    raw_text: str = Field(min_length=1, max_length=10000)
    bbox: list[float] | None = None

    @field_validator("bbox")
    @classmethod
    def valid_box(cls, value):
        """只接受处理页归一化坐标。"""
        if value is not None and (
            len(value) != 4 or not all(0 <= x <= 1 for x in value) or value[0] >= value[2] or value[1] >= value[3]
        ):
            raise ValueError("证据坐标无效")
        return value


class ReportField(HealthDTO):
    field_id: UUID
    name: str = Field(min_length=1, max_length=120)
    observation_code: Literal[
        "unknown", "glucose", "hba1c", "triglycerides", "cholesterol", "hdl", "ldl", "uric_acid"
    ] = "unknown"
    value_raw: str = Field(default="", max_length=500)
    value_numeric: Decimal | None = None
    unit_raw: str = Field(default="", max_length=100)
    reference_raw: str = Field(default="", max_length=500)
    observed_at: str | None = Field(default=None, max_length=40)
    fasting: Literal["unknown", "yes", "no"] = "unknown"
    source: Literal["ocr", "manual"] = "manual"
    evidence: Evidence | None = None
    review_flags: list[str] = Field(default_factory=list, max_length=15)
    excluded: bool = False

    @model_validator(mode="after")
    def source_evidence(self):
        """人工录入不能伪造 OCR 证据。"""
        if self.source == "ocr" and self.evidence is None:
            raise ValueError("OCR 字段必须有原文证据")
        if self.source == "manual" and self.evidence is not None:
            raise ValueError("人工字段不能附加 OCR 证据")
        if self.value_numeric is not None and (
            re.fullmatch(r"[+-]?\d+(?:\.\d+)?", self.value_raw) is None or Decimal(self.value_raw) != self.value_numeric
        ):
            raise ValueError("数值必须与明确的原始数字一致")
        if self.observed_at:
            date.fromisoformat(self.observed_at)
        else:
            self.observed_at = None
        return self


class ReportPreparationInput(HealthDTO):
    """人工方向和去倾斜仅改变报告处理副本。"""

    rotation: Annotated[int, Field(strict=True)] = 0
    deskew_angle: float = Field(default=0, ge=-10, le=10, allow_inf_nan=False, strict=True)

    @field_validator("rotation")
    @classmethod
    def quarter_turn(cls, value):
        """仅接受顺时针四分之一圈，不静默舍入客户端角度。"""
        if value not in {0, 90, 180, 270}:
            raise ValueError("报告旋转仅支持 0、90、180、270 度")
        return value


class ReportPage(HealthDTO):
    """复核使用服务端生成的处理页定位。"""

    page_index: int = Field(ge=0, le=19)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    rotation: int = 0
    transform: str
    source_space: Literal["encoded_image", "pdf_rendered_page"] | None = None
    source_width: int | None = Field(default=None, gt=0)
    source_height: int | None = Field(default=None, gt=0)
    exif_orientation: int | None = Field(default=None, ge=1, le=8)
    deskew_angle: float = Field(default=0, ge=-10, le=10, allow_inf_nan=False)
    source_to_processed: list[float] | None = Field(default=None, min_length=6, max_length=6)
    upload_id: UUID
    upload_page_index: int = Field(ge=0, le=19)
    status: Literal["ready", "failed"] = "ready"
    error_code: ReportPageErrorCode | None = None
    quality_flags: list[Literal["low_resolution"]] = Field(default_factory=list, max_length=1)

    @model_validator(mode="after")
    def consistent_status(self):
        """失败页须有受控原因，成功页不能携带失败原因。"""
        if (self.status == "failed") != (self.error_code is not None):
            raise ValueError("页面状态与错误代码不一致")
        if self.transform == "affine-v1" and (
            self.source_space is None
            or self.source_width is None
            or self.source_height is None
            or self.exif_orientation is None
            or self.source_to_processed is None
            or any(not math.isfinite(value) for value in self.source_to_processed)
        ):
            raise ValueError("仿射变换须包含源坐标空间、尺寸和有限系数")
        return self


class ReportPayload(HealthDTO):
    fields: list[ReportField] = Field(default_factory=list, max_length=300)
    excluded_pages: list[int] = Field(default_factory=list, max_length=20)
    pages: list[ReportPage] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_fields(self):
        """重复标识和不存在的排除页不能产生重复正式指标。"""
        if len({item.field_id for item in self.fields}) != len(self.fields):
            raise ValueError("报告项不能重复")
        indices = {page.page_index for page in self.pages}
        if len(indices) != len(self.pages) or set(self.excluded_pages) - indices:
            raise ValueError("排除页或页面标识无效")
        return self


class SeasoningAdjustment(HealthDTO):
    """明确成品之外的追加量或已知配方油糖的替换量。"""

    role: Literal["oil", "sugar"]
    mode: Literal["append", "replace"]
    food_id: UUID
    grams: Decimal = Field(gt=0, le=10000)


class MealLocation(HealthDTO):
    """模型观察位置绑定外发照片序号与归一化处理图。"""

    image_index: int = Field(ge=0, le=2, strict=True)
    bbox: list[Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def positive_area(self):
        """没有面积的框不构成可定位的观察。"""
        if self.bbox[0] >= self.bbox[2] or self.bbox[1] >= self.bbox[3]:
            raise ValueError("位置框必须有正面积")
        return self


class MealPhoto(HealthDTO):
    """来源由 worker 按实际外发顺序绑定，不由模型生成。"""

    image_index: int = Field(ge=0, le=2, strict=True)
    upload_id: UUID
    upload_page_index: Literal[0] = 0


class MealItem(HealthDTO):
    item_id: UUID
    name: str = Field(min_length=1, max_length=120)
    candidates: list[str] = Field(default_factory=list, max_length=3)
    cooking_method: str = Field(default="未知", max_length=100)
    visible_ingredients: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=20
    )
    locations: list[MealLocation] = Field(default_factory=list, max_length=3)
    uncertainties: list[str] = Field(default_factory=list, max_length=20)
    food_id: UUID | None = None
    recipe_version_id: UUID | None = None
    grams: Decimal | None = Field(default=None, gt=0, le=10000)
    portion_reference_id: UUID | None = None
    portion_count: Decimal | None = Field(default=None, gt=0, le=1000)
    share_ratio: Decimal | None = Field(default=None, ge=0, le=1)
    portion_source: Literal["unknown", "estimated", "weighed", "manual"] = "unknown"
    adjustments: list[SeasoningAdjustment] = Field(default_factory=list, max_length=2)
    excluded: bool = False

    @model_validator(mode="after")
    def consistent_mapping_and_portion(self):
        """两种数据映射与数量来源互斥，参考份量不能伪装称重。"""
        if self.food_id and self.recipe_version_id:
            raise ValueError("食品与食谱映射只能选择一种")
        if self.portion_reference_id:
            if self.grams is not None or self.portion_count is None or self.portion_source != "estimated":
                raise ValueError("碗勺参考须填写数量、留空克数并标记估算")
        elif self.portion_count is not None:
            raise ValueError("份量数量须关联已发布参考版本")
        if len({entry.role for entry in self.adjustments}) != len(self.adjustments):
            raise ValueError("同类油糖只能进行一次明确调整")
        if any(entry.mode == "replace" for entry in self.adjustments) and self.recipe_version_id is None:
            raise ValueError("替换油糖必须有可辨识原配方")
        if len({entry.image_index for entry in self.locations}) != len(self.locations):
            raise ValueError("同一菜品在每张照片只能有一个位置标记")
        return self


class MealPayload(HealthDTO):
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"]
    eaten_at: datetime
    items: list[MealItem] = Field(default_factory=list, max_length=30)
    photos: list[MealPhoto] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def unique_items(self):
        """同一个食物标识不能重复计餐。"""
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("食物项不能重复")
        if [photo.image_index for photo in self.photos] != list(range(len(self.photos))):
            raise ValueError("照片顺序须与外发视角一致")
        if len({photo.upload_id for photo in self.photos}) != len(self.photos):
            raise ValueError("同一上传不能重复绑定")
        if any(location.image_index >= len(self.photos) for item in self.items for location in item.locations):
            raise ValueError("食物位置必须绑定已有照片")
        return self

    @field_validator("eaten_at")
    @classmethod
    def require_timezone(cls, value):
        """就餐时间保留客户端明确时区。"""
        if value.tzinfo is None:
            raise ValueError("就餐时间必须包含时区")
        return value


class DraftInput(HealthDTO):
    member_id: UUID
    kind: Literal["report", "meal"]
    report: ReportPayload | None = None
    meal: MealPayload | None = None

    @model_validator(mode="after")
    def matching_kind(self):
        """只接受与用途一致的一种载荷。"""
        if (self.kind == "report" and (self.report is None or self.meal is not None)) or (
            self.kind == "meal" and (self.meal is None or self.report is not None)
        ):
            raise ValueError("草稿用途与内容不一致")
        return self


class DraftPatch(HealthDTO):
    version: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)
    report: ReportPayload | None = None
    meal: MealPayload | None = None


class VersionInput(HealthDTO):
    version: int = Field(gt=0)


class ReportReprocessInput(VersionInput):
    """显式选择未确认报告的失败页，不接收模型参数或对象地址。"""

    version: int = Field(gt=0, strict=True)
    draft_id: UUID
    client_request_id: UUID
    page_indices: list[Annotated[int, Field(ge=0, le=19, strict=True)]] = Field(min_length=1, max_length=20)

    @field_validator("page_indices")
    @classmethod
    def unique_pages(cls, value):
        """集合规范化使同一页集合的请求指纹稳定。"""
        if len(set(value)) != len(value):
            raise ValueError("重识别页不能重复且须为有效页索引")
        return sorted(value)


class ConfirmInput(VersionInput):
    client_request_id: UUID
    calculation_id: UUID | None = None
    accept_incomplete: bool = False


class PublishedNutritionSource(HealthDTO):
    """食品与食谱审核发布均保留来源、许可与版本。"""

    record_code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    cooking_state: str = Field(min_length=1, max_length=40)
    source: str = Field(min_length=1, max_length=300)
    license: str = Field(min_length=1, max_length=300)
    edition: str = Field(min_length=1, max_length=100)
    dataset_version: str = Field(min_length=1, max_length=80)


class FoodInput(PublishedNutritionSource):
    nutrients: dict[str, Decimal | None]
    recipe_estimated: bool = False

    @field_validator("nutrients")
    @classmethod
    def approved_nutrients(cls, value):
        """营养单位由受控代码确定，未知值保持空。"""
        if set(value) - NUTRIENTS.keys() or any(
            x is not None and (not x.is_finite() or x < 0 or x > 100000) for x in value.values()
        ):
            raise ValueError("营养代码或数值无效")
        return {key: value.get(key) for key in NUTRIENTS}


class RecipeIngredient(HealthDTO):
    """原料重量为可食克数，油糖角色用于可验证的配方替换。"""

    food_id: UUID
    grams: Decimal = Field(gt=0, le=100000, decimal_places=6)
    role: Literal["food", "oil", "sugar"] = "food"


class RecipeInput(PublishedNutritionSource):
    """客户端仅提交配方和净成品重，不能提交营养值。"""

    ingredients: list[RecipeIngredient] = Field(min_length=1, max_length=50)
    yield_grams: Decimal = Field(gt=0, le=100000, decimal_places=6)


class PortionInput(HealthDTO):
    """有实测来源的碗勺份量，只用于对应食品或食谱版本。"""

    food_id: UUID | None = None
    recipe_version_id: UUID | None = None
    unit_label: str = Field(min_length=1, max_length=80)
    grams_per_unit: Decimal = Field(gt=0, le=10000, decimal_places=6)
    source: str = Field(min_length=1, max_length=300)
    license: str = Field(min_length=1, max_length=300)
    edition: str = Field(min_length=1, max_length=100)
    dataset_version: str = Field(min_length=1, max_length=80)
    applicable_scope: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def one_mapping(self):
        """未关联或双重关联的规格不能发布。"""
        if bool(self.food_id) == bool(self.recipe_version_id):
            raise ValueError("份量参考须关联一种食品或食谱版本")
        return self


class VisionConfigurationInput(HealthDTO):
    report_model: str = Field(default="", max_length=160)
    meal_model: str = Field(default="", max_length=160)
    consultation_model: str = Field(default="", max_length=160)
    meal_plan_model: str = Field(default="", max_length=160)
    diet_analysis_model: str = Field(default="", max_length=160)
    quality_review_model: str = Field(default="", max_length=160)
    purchase_model: str = Field(default="", max_length=160)
    policy_version: str = Field(default="", max_length=80)
    cloud_processing_reviewed: bool = False

    @model_validator(mode="after")
    def require_policy(self):
        """配置模型必须先审批处理政策，不自动启用云调用。"""
        configured = (
            self.report_model
            or self.meal_model
            or self.consultation_model
            or self.meal_plan_model
            or self.diet_analysis_model
            or self.quality_review_model
            or self.purchase_model
        )
        if configured and (not self.policy_version or not self.cloud_processing_reviewed):
            raise ValueError("启用前须确认处理政策与费用限额已经审批")
        return self
