"""原小程序建档字段的云端输入，不接受身份或授权字段。"""

from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DietaryDetails(BaseModel):
    """保留自述、未知和明确无，不生成专业诊断。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    statedWeightKg: float | None = Field(default=None, gt=0, le=1000, allow_inf_nan=False)
    healthStatus: Literal["unknown", "none", "set"] = "unknown"
    conditions: list[str] = Field(default_factory=list, max_length=50)
    otherCondition: str = Field(default="", max_length=500)
    allergyStatus: Literal["unknown", "none", "set"] = "unknown"
    allergies: list[str] = Field(default_factory=list, max_length=50)
    intoleranceStatus: Literal["unknown", "none", "set"] = "unknown"
    intolerances: list[str] = Field(default_factory=list, max_length=50)
    avoidanceStatus: Literal["unknown", "none", "set"] = "unknown"
    avoidances: list[str] = Field(default_factory=list, max_length=50)
    doctorStatus: Literal["unknown", "none", "set"] = "unknown"
    clinicianGuidance: str = Field(default="", max_length=2000)
    goals: list[str] = Field(default_factory=list, max_length=30)
    cuisines: list[str] = Field(default_factory=list, max_length=30)
    tastePreferences: list[str] = Field(default_factory=list, max_length=30)
    flavors: list[str] = Field(default_factory=list, max_length=30)
    recentNote: str = Field(default="", max_length=1000)
    hypoglycemiaRisk: str = Field(default="未填写", max_length=100)
    kidneyCondition: str = Field(default="未填写", max_length=100)

    @model_validator(mode="after")
    def limited_text(self):
        """数组中的来源文本保持有界。"""
        for name in (
            "conditions",
            "allergies",
            "intolerances",
            "avoidances",
            "goals",
            "cuisines",
            "tastePreferences",
            "flavors",
        ):
            if any(not text or len(text) > 200 for text in getattr(self, name)):
                raise ValueError("建档条目须为非空短文本")
        return self


class MiniappMemberInput(BaseModel):
    """客户端引用仅用于同次建档映射，不能关联别人的身份。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    client_ref: str = Field(min_length=1, max_length=80)
    member_id: UUID | None = None
    version: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=80)
    relation: str = Field(min_length=1, max_length=30)
    birth_date: date
    sex: Literal["female", "male", "unspecified"] = "unspecified"
    height_cm: float | None = Field(default=None, gt=0, le=300, allow_inf_nan=False)
    weight_kg: float | None = Field(default=None, gt=0, le=1000, allow_inf_nan=False)
    dietary: DietaryDetails

    @model_validator(mode="after")
    def complete_onboarding(self):
        """完整建档须明确作答必填信息，其他用途的共享字段模型保持兼容。"""
        if self.birth_date > datetime.now(timezone(timedelta(hours=8))).date():
            raise ValueError("出生日期不能在未来")
        dietary = self.dietary
        for state, field, label in (
            ("healthStatus", "conditions", "已知基础病"),
            ("allergyStatus", "allergies", "食物过敏"),
            ("intoleranceStatus", "intolerances", "食物不耐受"),
            ("avoidanceStatus", "avoidances", "饮食忌口"),
            ("doctorStatus", "clinicianGuidance", "医生饮食要求"),
        ):
            status, value = getattr(dietary, state), getattr(dietary, field)
            if status == "unknown":
                raise ValueError(f"请选择{label}状态")
            if status == "set" and not value:
                raise ValueError(f"请补充具体{label}内容")
        if dietary.healthStatus == "set" and "其他" in dietary.conditions and not dietary.otherCondition:
            raise ValueError("请补充具体基础病")
        for field, label in (("goals", "饮食目标"), ("tastePreferences", "口味偏好")):
            values = getattr(dietary, field)
            if not values or any(value in {"其他", "自定义"} for value in values):
                raise ValueError(f"请选择或补充{label}")
        # 原小程序将菜系列为可后补；空数组表示未填写，不自动推断为“无特别要求”。
        if any(value in {"其他", "自定义"} for value in dietary.cuisines):
            raise ValueError("请补充具体菜系偏好")
        for state, field in (
            ("allergyStatus", "allergies"),
            ("intoleranceStatus", "intolerances"),
            ("avoidanceStatus", "avoidances"),
        ):
            if getattr(dietary, state) == "set" and any(
                value in {"其他", "自定义"} for value in getattr(dietary, field)
            ):
                raise ValueError("请补充具体食物或成分")
        return self


class MiniappProfileInput(BaseModel):
    """完成建档时整体保存，三步表单不增加前置确认。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    client_request_id: UUID
    scope: Literal["household", "self"] = "household"
    family_version: int = Field(ge=1)
    usage_mode: Literal["个人使用", "家庭使用"]
    default_diners: list[str] = Field(min_length=1, max_length=20)
    members: list[MiniappMemberInput] = Field(min_length=1, max_length=20)
    analysis_consent: dict[str, str] | None = None

    @model_validator(mode="after")
    def selection(self):
        """默认就餐者只引用本次明确成员。"""
        refs = [member.client_ref for member in self.members]
        if (
            len(refs) != len(set(refs))
            or len(set(self.default_diners)) != len(self.default_diners)
            or not set(self.default_diners) <= set(refs)
        ):
            raise ValueError("默认就餐成员与建档成员不一致")
        return self


def miniapp_onboarding_ready(member, family):
    """按当前本人完整档案与确认版本判定，不继承其他家人的完成标记。"""
    if member is None or not member.is_active:
        return False
    from pydantic import ValidationError

    profile = member.profile or {}
    try:
        MiniappMemberInput.model_validate(
            {
                "client_ref": member.id,
                "member_id": member.id,
                "version": member.version,
                "name": member.name,
                "relation": "本人",
                "birth_date": profile.get("birth_date"),
                "sex": profile.get("sex", "unspecified"),
                "height_cm": profile.get("height_cm"),
                "dietary": profile.get("dietary_details", {}),
            }
        )
    except ValidationError:
        return False
    return member.confirmed_version == member.version
