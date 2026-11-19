"""原小程序建档字段的云端输入，不接受身份或授权字段。"""

from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ActivityLevel = Literal["sedentary", "light", "moderate", "high"]


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
    sex: Literal["female", "male"]
    height_cm: float = Field(gt=0, le=300, allow_inf_nan=False, strict=True)
    weight_kg: float = Field(gt=0, le=1000, allow_inf_nan=False, strict=True)
    activity_level: ActivityLevel | None = None
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
    onboarding_version: Literal[2] | None = None
    scope: Literal["household", "self"] = "household"
    family_version: int = Field(ge=1)
    usage_mode: Literal["个人使用", "家庭使用"]
    default_diners: list[str] = Field(min_length=1, max_length=20)
    members: list[MiniappMemberInput] = Field(min_length=1, max_length=20)
    analysis_consent: dict[str, str] | None = None
    plan_consent: dict[str, str] | None = None

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
        if self.onboarding_version == 2 and any(member.activity_level is None for member in self.members):
            raise ValueError("请选择每位建档成员的日常活动量")
        return self

    def submission_dump(self, *, exclude_processing_consents=False):
        """保留新增字段缺省前的请求指纹，仍纳入显式提交的活动量。"""
        exclude = {}
        if exclude_processing_consents:
            exclude["processing_consents"] = True
        if "onboarding_version" not in self.model_fields_set:
            exclude["onboarding_version"] = True
        if "plan_consent" not in self.model_fields_set:
            exclude["plan_consent"] = True
        exclude["members"] = {
            index: {"activity_level"}
            for index, member in enumerate(self.members)
            if "activity_level" not in member.model_fields_set
        }
        return self.model_dump(mode="json", exclude=exclude)


class MiniappAnalysisInput(BaseModel):
    """用户核对已保存的成员资料后明确接受单一用途，不提交档案副本。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["start_analysis"]
    client_request_id: UUID
    member_id: UUID
    expected_version: int = Field(ge=1)
    accepted: Literal[True]
    purpose: Literal["consultation", "meal_plan"]
    processor: str = Field(min_length=1, max_length=200)
    policy_version: str = Field(min_length=1, max_length=200)


class MiniappConsultationOpenInput(BaseModel):
    """应用在本人建档后自动衔接咨询，只引用服务端已保存的成员和版本。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["open_consultation"]
    client_request_id: UUID
    member_id: UUID
    expected_version: int = Field(ge=1)


def miniapp_onboarding_ready(member, family):
    """保留建档完成标记，咨询自动衔接只使用完整的服务端档案。"""
    return miniapp_profile_complete(member)


def miniapp_profile_complete(member):
    """按当前正式字段判断完整性，历史缺失资料不继承完成标记。"""
    if member is None or not member.is_active:
        return False
    try:
        saved_miniapp_member(member)
    except ValidationError:
        return False
    return True


def require_miniapp_profile(member):
    """按成员名称和缺失字段解释资料错误，不要求档案主体本人确认。"""
    from yuxi.services.health_vision_types import HealthVisionError

    labels = {
        "birth_date": "出生日期", "sex": "性别", "height_cm": "身高",
        "weight_kg": "体重", "activity_level": "日常活动量", "name": "姓名或称呼",
        "dietary": "饮食与健康资料",
    }
    try:
        saved_miniapp_member(member)
    except ValidationError as exc:
        fields = list(dict.fromkeys(labels.get(str(error["loc"][0]), "饮食与健康资料") for error in exc.errors()))
        raise HealthVisionError("profile_incomplete", f"请补充{member.name}的资料：" + "、".join(fields), 422) from None


def saved_miniapp_member(member, profile=None):
    """将已保存字段还原为提交契约，体重只读取自述体重的正式位置。"""
    profile = (member.profile or {}) if profile is None else profile
    dietary = profile.get("dietary_details") or {}
    return MiniappMemberInput.model_validate(
        {
            "client_ref": str(member.id),
            "member_id": member.id,
            "version": member.version,
            "name": member.name,
            "relation": getattr(member, "relationship", "本人"),
            "birth_date": profile.get("birth_date"),
            "sex": profile.get("sex"),
            "height_cm": profile.get("height_cm"),
            "activity_level": profile.get("activity_level"),
            "weight_kg": dietary.get("statedWeightKg") if isinstance(dietary, dict) else None,
            "dietary": dietary,
        }
    )
