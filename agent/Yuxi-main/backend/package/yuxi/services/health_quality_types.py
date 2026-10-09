"""外部确认投影、批准规则及专业审核的业务边界。"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from yuxi.services.health_vision_types import HealthDTO, NUTRIENTS

Code = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.:-]+$")]
Version = Annotated[int, Field(gt=0, strict=True)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class StatedCodes(HealthDTO):
    """未填写、明确无及明确条目分别保留，不从文本推断。"""

    state: Literal["unknown", "none", "specified"]
    codes: list[Code] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def explicit_state(self):
        """明确条目才允许非空编码，拒绝重复。"""
        if (self.state == "specified") != bool(self.codes) or len(set(self.codes)) != len(self.codes):
            raise ValueError("状态与明确条目不符，或编码重复")
        self.codes.sort()
        return self


class ProfileProjection(HealthDTO):
    """健康档案服务拥有的已确认字段投影，不是AI建档输入。"""

    population_code: Code | None = None
    age_years: int | None = Field(default=None, ge=0, le=130, strict=True)
    sex_code: Code | None = None
    weight_kg: Decimal | None = Field(default=None, gt=0, le=1000, decimal_places=6)
    height_cm: Decimal | None = Field(default=None, gt=0, le=500, decimal_places=6)
    activity_code: Code | None = None
    conditions: StatedCodes
    allergies: StatedCodes
    intolerances: StatedCodes
    avoidances: StatedCodes
    doctor_requirements: StatedCodes
    preferences: StatedCodes


class ExternalVersion(HealthDTO):
    """受信管理导入仍须带外部依据和有限有效期。"""

    version: Version
    source_ref: str = Field(min_length=1, max_length=500)
    source_version: str = Field(min_length=1, max_length=80)
    authority_ref: str = Field(min_length=1, max_length=500)
    attested_by: str = Field(min_length=1, max_length=100)
    attested_at: datetime
    valid_until: datetime

    @field_validator("attested_at", "valid_until")
    @classmethod
    def aware_time(cls, value):
        """导入跨系统时间必须有时区，不猜本地时间。"""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("时间须含时区")
        return value

    @model_validator(mode="after")
    def ordered_time(self):
        """有效期不能早于或等于外部确认时间。"""
        if self.valid_until <= self.attested_at:
            raise ValueError("有效期须晚于确认时间")
        return self


class FamilyProfileSource(HealthDTO):
    """由本人正式关联确定的专业确认来源，摘要由服务端计算。"""

    family_id: UUID
    source_member_id: UUID
    confirmed_version: Version


class WeightMeasurementSource(HealthDTO):
    """明确选择本人实测的独立版本，不由客户端提供数值或摘要。"""

    record_id: UUID
    version: Version


class ProfileImport(ExternalVersion):
    """只接受外部已确认版本，未知字段可以显式保留。"""

    status: Literal["confirmed"]
    payload: ProfileProjection
    family_profile_source: FamilyProfileSource | None = None
    weight_measurement_source: WeightMeasurementSource | None = None

    @model_validator(mode="after")
    def weight_requires_family_source(self):
        """体重记录必须通过本人正式档案关联确定归属。"""
        if self.weight_measurement_source is not None and self.family_profile_source is None:
            raise ValueError("选定实测体重须同时明确本人正式档案来源")
        return self


class NutrientBounds(HealthDTO):
    """批准规则提供每日范围，代码不默认任何医学阈值。"""

    minimum: Decimal = Field(ge=0, le=1000000, decimal_places=6)
    maximum: Decimal = Field(ge=0, le=1000000, decimal_places=6)

    @model_validator(mode="after")
    def valid_range(self):
        """拒绝倒置范围。"""
        if self.maximum < self.minimum:
            raise ValueError("最大值小于最小值")
        return self


class IngredientClassification(HealthDTO):
    """分类绑定实际食品内容摘要，完整性由批准资料明确提供。"""

    food_id: UUID
    food_hash: Digest
    complete: bool = Field(strict=True)
    allergen_codes: list[Code] = Field(default_factory=list, max_length=50)
    intolerance_codes: list[Code] = Field(default_factory=list, max_length=50)
    food_categories: list[Code] = Field(default_factory=list, max_length=50)


class DoctorRequirementRule(HealthDTO):
    """医嘱编码仅消费批准规则，不把自由文字变成限制。"""

    code: Code
    excluded_food_categories: list[Code] = Field(default_factory=list, max_length=50)
    excluded_food_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    daily_bounds: dict[str, NutrientBounds] = Field(default_factory=dict)


class SwapRecipeClassification(HealthDTO):
    """专业分类绑定实际菜谱版本及配方摘要，不从菜名猜类型。"""

    recipe_version_id: UUID
    recipe_hash: Digest
    dish_type_code: Code
    allowed_meal_types: list[Literal["breakfast", "lunch", "dinner"]] = Field(min_length=1, max_length=3)

    @field_validator("allowed_meal_types")
    @classmethod
    def distinct_meals(cls, values):
        """批准餐次不能重复。"""
        if len(values) != len(set(values)):
            raise ValueError("批准餐次重复")
        return values


class MealSwapRules(HealthDTO):
    """营养差异上限使用现有营养单位，由外部批准资料明确给出。"""

    recipe_classifications: list[SwapRecipeClassification] = Field(min_length=1, max_length=1000)
    maximum_nutrient_differences: dict[str, Annotated[Decimal, Field(ge=0, le=1000000, decimal_places=6)]]

    @model_validator(mode="after")
    def complete_limits(self):
        """缺一项差异上限或重复版本均拒绝，零上限表示必须相同。"""
        if set(self.maximum_nutrient_differences) != NUTRIENTS.keys():
            raise ValueError("换菜须明确全部五项营养差异上限")
        ids = [c.recipe_version_id for c in self.recipe_classifications]
        if len(ids) != len(set(ids)):
            raise ValueError("换菜菜谱分类版本重复")
        return self


class TargetRangeFactors(HealthDTO):
    """批准能量乘数和常数产生营养范围，不默认换算或临床系数。"""

    minimum_per_energy: Decimal = Field(ge=0, le=1000000, decimal_places=6)
    maximum_per_energy: Decimal = Field(ge=0, le=1000000, decimal_places=6)
    minimum_constant: Decimal = Field(ge=0, le=1000000, decimal_places=6)
    maximum_constant: Decimal = Field(ge=0, le=1000000, decimal_places=6)

    @model_validator(mode="after")
    def ordered_factors(self):
        """正能量的范围不得由倒置系数或常数构成。"""
        if self.minimum_per_energy > self.maximum_per_energy or self.minimum_constant > self.maximum_constant:
            raise ValueError("目标系数或常数范围倒置")
        return self


class PersonalTargetFormula(HealthDTO):
    """公式只匹配批准的人群、性别编码和完整疾病组合。"""

    population_code: Code
    sex_code: Code
    condition_codes: list[Code] = Field(max_length=50)
    intercept_kcal: Decimal = Field(ge=-1000000, le=1000000, decimal_places=6)
    weight_kg_coefficient: Decimal = Field(ge=-1000000, le=1000000, decimal_places=6)
    height_cm_coefficient: Decimal = Field(ge=-1000000, le=1000000, decimal_places=6)
    age_years_coefficient: Decimal = Field(ge=-1000000, le=1000000, decimal_places=6)
    activity_factors: dict[Code, Annotated[Decimal, Field(gt=0, le=1000000, decimal_places=6)]] = Field(
        min_length=1, max_length=50
    )
    nutrient_ranges: dict[str, TargetRangeFactors]

    @model_validator(mode="after")
    def complete_formula(self):
        """五项营养全部明确，组合无重复；不推断未提供字段。"""
        if set(self.nutrient_ranges) != NUTRIENTS.keys() or len(self.condition_codes) != len(set(self.condition_codes)):
            raise ValueError("目标公式须明确五项营养且疾病编码不重复")
        self.condition_codes.sort()
        return self


class GenerationDishRule(HealthDTO):
    """专业资料明确菜品类型与有限份量，不由代码估量。"""

    dish_type_code: Code
    grams_options: list[Annotated[Decimal, Field(gt=0, le=10000, decimal_places=6)]] = Field(
        min_length=1, max_length=10
    )

    @field_validator("grams_options")
    @classmethod
    def distinct_amounts(cls, values):
        """相同份量只参与一次搜索，顺序归一化。"""
        if len(values) != len(set(values)):
            raise ValueError("批准份量重复")
        return sorted(values)


class GenerationMealRule(HealthDTO):
    """每种菜品类型最多一道，家庭按类型合并实际食用者。"""

    meal_type: Literal["breakfast", "lunch", "dinner"]
    dishes: list[GenerationDishRule] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def distinct_types(self):
        """禁止重复类型造成不明确的共同菜位。"""
        if len({d.dish_type_code for d in self.dishes}) != len(self.dishes):
            raise ValueError("批准餐次菜品类型重复")
        self.dishes.sort(key=lambda d: d.dish_type_code)
        return self


class GenerationProfileMenu(HealthDTO):
    """只匹配批准人群和完整疾病组合的三餐菜单。"""

    population_code: Code
    condition_codes: list[Code] = Field(max_length=50)
    meals: list[GenerationMealRule] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def complete_menu(self):
        """三餐各一次，疾病组合不含重复。"""
        if {m.meal_type for m in self.meals} != {"breakfast", "lunch", "dinner"}:
            raise ValueError("批准菜单须各包含一次三餐")
        if len(self.condition_codes) != len(set(self.condition_codes)):
            raise ValueError("批准菜单疾病编码重复")
        self.condition_codes.sort()
        self.meals.sort(key=lambda m: ("breakfast", "lunch", "dinner").index(m.meal_type))
        return self


class MealGenerationRules(HealthDTO):
    """初始配餐目录独立于换菜差异，明确实际配方和可用份量。"""

    recipe_classifications: list[SwapRecipeClassification] = Field(min_length=1, max_length=1000)
    profile_menus: list[GenerationProfileMenu] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def distinct_catalogs(self):
        """每个配方及人群组合唯一，菜单类型须有批准餐次候选。"""
        ids = [c.recipe_version_id for c in self.recipe_classifications]
        keys = [(m.population_code, tuple(m.condition_codes)) for m in self.profile_menus]
        if len(ids) != len(set(ids)) or len(keys) != len(set(keys)):
            raise ValueError("初始配餐目录或菜单重复")
        available = {(c.dish_type_code, meal) for c in self.recipe_classifications for meal in c.allowed_meal_types}
        if any(
            (d.dish_type_code, m.meal_type) not in available
            for menu in self.profile_menus
            for m in menu.meals
            for d in m.dishes
        ):
            raise ValueError("批准菜单类型缺少对应餐次目录")
        return self


class QualityRules(HealthDTO):
    """外部批准的人群、疾病组合、配料分类及营养范围。"""

    allowed_population_codes: list[Code] = Field(min_length=1, max_length=50)
    minimum_age_years: int = Field(ge=0, le=130, strict=True)
    maximum_age_years: int = Field(ge=0, le=130, strict=True)
    supported_condition_sets: list[list[Code]] = Field(min_length=1, max_length=50)
    allergen_codes: list[Code] = Field(default_factory=list, max_length=50)
    intolerance_codes: list[Code] = Field(default_factory=list, max_length=50)
    food_categories: list[Code] = Field(default_factory=list, max_length=100)
    ingredient_classifications: list[IngredientClassification] = Field(min_length=1, max_length=1000)
    doctor_requirement_rules: list[DoctorRequirementRule] = Field(default_factory=list, max_length=50)
    daily_bounds: dict[str, NutrientBounds]
    meal_swap: MealSwapRules | None = None
    meal_generation: MealGenerationRules | None = None
    personal_targets: list[PersonalTargetFormula] | None = Field(default=None, min_length=1, max_length=50)
    meal_target_shares: (
        dict[
            Literal["breakfast", "lunch", "dinner"], dict[str, Annotated[Decimal, Field(ge=0, le=1, decimal_places=6)]]
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def consistent_catalogs(self):
        """拒绝模糊或重复分类，缺营养范围由检查器显式报告未知。"""
        if self.minimum_age_years > self.maximum_age_years:
            raise ValueError("批准年龄范围倒置")
        if not set(self.daily_bounds) <= NUTRIENTS.keys():
            raise ValueError("营养编码无效")
        for codes in (self.allowed_population_codes, self.allergen_codes, self.intolerance_codes, self.food_categories):
            if len(codes) != len(set(codes)):
                raise ValueError("规则目录编码重复")
        combinations = [tuple(sorted(codes)) for codes in self.supported_condition_sets]
        if len(combinations) != len(set(combinations)) or any(len(c) != len(set(c)) for c in combinations):
            raise ValueError("疾病组合重复")
        if len({c.food_id for c in self.ingredient_classifications}) != len(self.ingredient_classifications):
            raise ValueError("食品分类版本重复")
        if len({c.code for c in self.doctor_requirement_rules}) != len(self.doctor_requirement_rules):
            raise ValueError("医嘱规则编码重复")
        target_keys = set()
        if self.meal_target_shares is not None:
            shares = self.meal_target_shares
            if set(shares) != {"breakfast", "lunch", "dinner"} or any(
                set(v) != NUTRIENTS.keys() for v in shares.values()
            ):
                raise ValueError("餐次分配须明确三餐全部五项营养比例")
            if any(sum(shares[m][code] for m in shares) != 1 for code in NUTRIENTS):
                raise ValueError("每项营养的三餐分配比例须合计为一")
        for formula in self.personal_targets or []:
            key = (formula.population_code, formula.sex_code, tuple(formula.condition_codes))
            if (
                key in target_keys
                or formula.population_code not in self.allowed_population_codes
                or tuple(formula.condition_codes) not in combinations
            ):
                raise ValueError("个人目标公式重复或不在批准人群/疾病组合中")
            target_keys.add(key)
        for classification in self.ingredient_classifications:
            for name, catalog in (
                ("allergen_codes", self.allergen_codes),
                ("intolerance_codes", self.intolerance_codes),
                ("food_categories", self.food_categories),
            ):
                values = getattr(classification, name)
                if len(values) != len(set(values)) or not set(values) <= set(catalog):
                    raise ValueError("配料分类不在批准目录中或重复")
        for menu in self.meal_generation.profile_menus if self.meal_generation else []:
            if (
                menu.population_code not in self.allowed_population_codes
                or tuple(menu.condition_codes) not in combinations
            ):
                raise ValueError("初始菜单不在批准人群或疾病组合中")
        for requirement in self.doctor_requirement_rules:
            if not set(requirement.excluded_food_categories) <= set(self.food_categories):
                raise ValueError("医嘱分类不在批准目录中")
            if not set(requirement.daily_bounds) <= NUTRIENTS.keys():
                raise ValueError("医嘱营养编码无效")
            if (
                not requirement.excluded_food_ids
                and not requirement.excluded_food_categories
                and not requirement.daily_bounds
            ):
                raise ValueError("医嘱规则未明确限制")
        return self


class RulesImport(ExternalVersion):
    """管理员登记专业内容方的已批准版本。"""

    rule_code: Code
    status: Literal["approved"]
    payload: QualityRules


class ReviewerImport(ExternalVersion):
    """受信管理员登记外部资格，不以User角色替代资格。"""

    reviewer_uid: str = Field(min_length=1, max_length=100)
    status: Literal["qualified"]


class QualityCheckInput(HealthDTO):
    """用户明确选择对象版本及规则，不提交检查结论。"""

    client_request_id: UUID
    version: Version
    rule_code: Code


class PersonalTargetSelection(HealthDTO):
    """读取当前成员确认投影和批准公式，不由客户端提供身体参数。"""

    rule_code: Code
    rule_version: Version
    profile_version: Version


class ReviewActionInput(HealthDTO):
    """专业及提交动作使用同一版本和幂等约束。"""

    client_request_id: UUID
    version: Version
    reason: str = Field(min_length=1, max_length=500)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)

    @field_validator("evidence_refs")
    @classmethod
    def evidence_present(cls, values):
        """每项证据有明确内容，拒绝重复占位。"""
        if any(not v.strip() or len(v) > 500 for v in values) or len(values) != len(set(values)):
            raise ValueError("证据为空、过长或重复")
        return [v.strip() for v in values]


class QualityAnswer(HealthDTO):
    """模型只选择检查收据或问题，不提交安全及专业状态。"""

    check_id: UUID | None = None
    questions: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def one_answer(self):
        """拒绝假完成、空问题及自由字段。"""
        if bool(self.check_id) == bool(self.questions) or any(not q.strip() or len(q) > 200 for q in self.questions):
            raise ValueError("选择本Run检查回执或一到三个具体问题")
        return self
