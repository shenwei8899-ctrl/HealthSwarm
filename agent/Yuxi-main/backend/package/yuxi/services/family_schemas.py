"""家庭档案 HTTP 输入与字段白名单。"""

import math
from datetime import date, datetime, timedelta, UTC
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator


PROFILE_FIELDS = {
    "sex",
    "birth_date",
    "height_cm",
    "activity_level",
    "goal",
    "medical_history",
    "medications",
    "doctor_instructions",
    "allergens",
    "avoidances",
    "preferences",
    "health_goals",
    "condition_records",
    "medication_records",
    "instruction_records",
    "allergy_records",
    "meal_habits",
    "lifestyle",
}
REQUIRED_PROFILE_FIELDS = ("sex", "birth_date", "height_cm", "activity_level", "goal")
STRUCTURED_PROFILE_FIELDS = {
    "health_goals",
    "condition_records",
    "medication_records",
    "instruction_records",
    "allergy_records",
    "meal_habits",
    "lifestyle",
}
METRIC_FIELDS = {
    "weight": ("weight",),
    "blood_pressure": ("systolic", "diastolic"),
    "blood_glucose": ("glucose",),
    "blood_lipids": ("tc", "tg", "hdl", "ldl"),
    "height": ("height",),
}
METRIC_UNITS = {
    "weight": "kg",
    "blood_pressure": "mmHg",
    "blood_glucose": "mmol/L",
    "blood_lipids": "mmol/L",
    "height": "cm",
}


class FactRecord(BaseModel):
    """用户录入的事实及来源，不自动产生诊断或专业规则。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    description: str = Field(min_length=1, max_length=500)
    source: str | None = Field(default=None, max_length=200)
    recorded_on: date | None = None
    reviewed_on: date | None = None


class HealthGoal(FactRecord):
    """可复盘的用户行为目标，与专业批准的营养目标分开。"""

    start_date: date | None = None
    review_date: date | None = None
    status: Literal["active", "completed", "paused"] = "active"

    @model_validator(mode="after")
    def check_dates(self):
        """复盘不能早于目标开始。"""
        if self.start_date and self.review_date and self.review_date < self.start_date:
            raise ValueError("复盘日期不能早于开始日期")
        return self


class ConditionRecord(FactRecord):
    """区分自述症状和已有确诊资料。"""

    status: Literal["symptom", "diagnosed", "resolved", "unknown"] = "unknown"


class MedicationRecord(FactRecord):
    """保留药物名称、剂量和频次的未知项。"""

    dose: str | None = Field(default=None, max_length=100)
    frequency: str | None = Field(default=None, max_length=100)
    start_date: date | None = None
    status: Literal["current", "stopped", "unknown"] = "unknown"


class InstructionRecord(FactRecord):
    """来源和有效日期明确的医嘱资料。"""

    valid_until: date | None = None


class AllergyRecord(FactRecord):
    """过敏原、反应和确认来源，与普通忌口分开。"""

    reaction: str | None = Field(default=None, max_length=300)
    status: Literal["reported", "confirmed", "unknown"] = "reported"


class MealHabits(BaseModel):
    """学校、工作和居家用餐安排。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    weekday: str | None = Field(default=None, max_length=500)
    weekend: str | None = Field(default=None, max_length=500)
    chewing_swallowing: str | None = Field(default=None, max_length=300)


class Lifestyle(BaseModel):
    """与用餐有关的活动及特殊阶段自述。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    activity_schedule: str | None = Field(default=None, max_length=500)
    sleep_schedule: str | None = Field(default=None, max_length=300)
    special_stage: str | None = Field(default=None, max_length=300)


class HouseholdSettings(BaseModel):
    """共同生活偏好，不承载成员的私有健康信息。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cook: str | None = Field(default=None, max_length=100)
    shopper: str | None = Field(default=None, max_length=100)
    weekday_meals: str | None = Field(default=None, max_length=500)
    weekend_meals: str | None = Field(default=None, max_length=500)
    cooking_minutes: int | None = Field(default=None, ge=1, le=1440)
    daily_budget: float | None = Field(default=None, gt=0, le=100000, allow_inf_nan=False)
    shared_preferences: str | None = Field(default=None, max_length=500)


class FamilyUpdate(BaseModel):
    """改名和共同生活设置使用同一个明确版本。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=80)
    settings: HouseholdSettings


class GuardianRequest(BaseModel):
    """申请人明确声明监护关系，审核前不开放资料。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    relationship: Literal["父亲", "母亲", "法定监护人"]
    birth_date: date
    attested: Literal[True]
    expires_at: datetime

    @model_validator(mode="after")
    def check_expiry(self):
        """监护授权期限最长一年且必须带时区。"""
        now = datetime.now(UTC)
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        age = (
            today.year
            - self.birth_date.year
            - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        )
        if self.birth_date > today or age >= 18:
            raise ValueError("监护申请仅支持未成年成员")
        if self.expires_at.tzinfo is None or not now < self.expires_at <= now + timedelta(days=366):
            raise ValueError("监护期限须为带时区的未来时间，最长一年")
        return self


class GuardianReview(BaseModel):
    """独立管理员核对资料后审核申请。"""

    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    approved: bool
    verified: Literal[True]


class FamilyInput(BaseModel):
    """家庭名称。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)


class MemberInput(FamilyInput):
    """仅创建成员关系，不创建其他人的健康信息。"""

    relationship: str = Field(min_length=1, max_length=30)


class ProfileInput(BaseModel):
    """可更正的档案字段；未提供与明确空值分别表达。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    sex: Literal["female", "male", "unspecified"] | None = None
    birth_date: date | None = None
    height_cm: float | None = Field(default=None, gt=0, le=300, allow_inf_nan=False)
    activity_level: Literal["sedentary", "light", "moderate", "high"] | None = None
    goal: str | None = Field(default=None, max_length=200)
    medical_history: str | None = Field(default=None, max_length=2000)
    medications: str | None = Field(default=None, max_length=2000)
    doctor_instructions: str | None = Field(default=None, max_length=2000)
    allergens: list[str] | None = Field(default=None, max_length=50)
    avoidances: list[str] | None = Field(default=None, max_length=50)
    preferences: str | None = Field(default=None, max_length=500)
    health_goals: list[HealthGoal] | None = Field(default=None, max_length=30)
    condition_records: list[ConditionRecord] | None = Field(default=None, max_length=50)
    medication_records: list[MedicationRecord] | None = Field(default=None, max_length=50)
    instruction_records: list[InstructionRecord] | None = Field(default=None, max_length=50)
    allergy_records: list[AllergyRecord] | None = Field(default=None, max_length=50)
    meal_habits: MealHabits | None = None
    lifestyle: Lifestyle | None = None

    @model_validator(mode="after")
    def check_birth_date(self):
        """不接受未来出生日期。"""
        if self.birth_date and self.birth_date > datetime.now(UTC).date():
            raise ValueError("出生日期不能在未来")
        for values in (self.allergens, self.avoidances):
            if values and any(not value.strip() or len(value) > 100 for value in values):
                raise ValueError("过敏原和忌口须为非空短文本")
        return self


class ProfileUpdate(BaseModel):
    """基于明确版本修改档案。"""

    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    profile: ProfileInput


class VersionInput(BaseModel):
    """确认当前版本。"""

    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class MemberUpdate(MemberInput):
    """维护成员关系元信息，不改变健康档案。"""

    expected_version: int = Field(ge=1)


class MemberStatusInput(BaseModel):
    """停用或恢复家庭关系。"""

    model_config = ConfigDict(extra="forbid")
    is_active: bool
    expected_version: int = Field(ge=1)


class AuthorizationInput(BaseModel):
    """由本人授权字段、用途和期限。"""

    model_config = ConfigDict(extra="forbid")
    fields: list[str] = Field(max_length=30)
    edit_fields: list[str] = Field(default_factory=list, max_length=30)
    purpose: Literal["family_nutrition"] = "family_nutrition"
    expires_at: datetime

    @model_validator(mode="after")
    def check_authorization(self):
        """授权字段与有效期只能使用支持的当前语义。"""
        if set(self.fields) - (PROFILE_FIELDS | METRIC_FIELDS.keys()):
            raise ValueError("授权字段不支持")
        if not set(self.edit_fields) <= set(self.fields):
            raise ValueError("代维护范围必须包含在查看范围内")
        if self.expires_at.tzinfo is None or self.expires_at <= datetime.now(UTC):
            raise ValueError("授权有效期必须为带时区的未来时间")
        if self.expires_at > datetime.now(UTC) + timedelta(days=366):
            raise ValueError("授权有效期最长一年")
        return self


class JoinInput(BaseModel):
    """认领一次性邀请。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: str = Field(min_length=20, max_length=100)


class MeasurementInput(BaseModel):
    """独立且可幂等保存的实测记录。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: UUID
    kind: Literal["weight", "blood_pressure", "blood_glucose", "blood_lipids", "height"]
    values: dict[str, float]
    measured_at: datetime
    source: str = Field(default="manual", min_length=1, max_length=100)
    condition: str = Field(default="", max_length=100)
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def check_measurement(self):
        """只保存完整、有限且带明确测量时间的指标。"""
        validate_metric_values(self.kind, self.values)
        if self.measured_at.tzinfo is None or self.measured_at > datetime.now(UTC):
            raise ValueError("测量时间必须带时区且不能在未来")
        if self.kind == "blood_glucose" and self.condition not in {"fasting", "after_meal_2h", "random"}:
            raise ValueError("血糖必须注明测量条件")
        return self


class MeasurementUpdate(VersionInput):
    """更正数值或测量信息，指标类型和成员归属保持稳定。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    values: dict[str, float]
    note: str = Field(min_length=1, max_length=1000)
    measured_at: datetime | None = None
    source: str | None = Field(default=None, min_length=1, max_length=100)
    condition: str | None = Field(default=None, max_length=100)


class MeasurementVoid(VersionInput):
    """作废保留原始值、原因与审计。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=1, max_length=1000)


class MeasurementQuery(BaseModel):
    """指标查询的自然日范围、分页和条件。"""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["weight", "blood_pressure", "blood_glucose", "blood_lipids", "height"] | None = None
    days: int = Field(default=30, ge=1, le=366)
    condition: Literal["fasting", "after_meal_2h", "random"] | None = None
    from_date: date | None = None
    to_date: date | None = None
    include_voided: bool = False
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


def validate_metric_values(kind: str, values: dict[str, float]) -> None:
    """验证指标结构，不进行诊断或临床风险分级。"""
    if set(values) != set(METRIC_FIELDS[kind]) or any(not math.isfinite(v) or v <= 0 for v in values.values()):
        raise ValueError("指标数值须完整且为有限正数")
    if kind == "blood_pressure" and values["systolic"] <= values["diastolic"]:
        raise ValueError("收缩压须大于舒张压")
