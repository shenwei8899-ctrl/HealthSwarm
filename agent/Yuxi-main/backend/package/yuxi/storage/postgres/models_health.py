"""成员私有识图数据及不可变确认快照。"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)

from yuxi.storage.postgres.models_business import Base, JSON_VALUE
from yuxi.utils.datetime_utils import utc_now_naive


class FamilyMember(Base):
    """健康对象，不以家庭管理员身份隐式授权。"""

    __tablename__ = "family_member"
    id = Column(String(36), primary_key=True)
    owner_uid = Column(String, ForeignKey("users.uid"), nullable=False, index=True)
    display_name = Column(String(80), nullable=False)
    relationship_label = Column(String(40), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthGrant(Base):
    """账号对成员的显式可撤回授权。"""

    __tablename__ = "health_grant"
    member_id = Column(String(36), ForeignKey("family_member.id"), primary_key=True)
    actor_uid = Column(String, ForeignKey("users.uid"), primary_key=True)
    scopes = Column(JSON_VALUE, nullable=False)
    revoked_at = Column(DateTime)


class HealthFamilyProfileLink(Base):
    """本人显式关联两套成员身份，保留既有健康对象。"""

    __tablename__ = "health_family_profile_link"
    member_id = Column(String(36), ForeignKey("family_member.id"), primary_key=True)
    source_member_id = Column(String(36), ForeignKey("family_members.id"), nullable=False, unique=True)
    family_id = Column(String(36), ForeignKey("family_archives.id"), nullable=False)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthFamilyProfileUse(Base):
    """Run 的正式档案来源依赖，只保存摘要和版本。"""

    __tablename__ = "health_family_profile_use"
    run_id = Column(String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True)
    payload_hash = Column(String(64), primary_key=True)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False)
    source_member_id = Column(String(36), ForeignKey("family_members.id"), nullable=False)
    version = Column(Integer, nullable=False)


class HealthWeightUse(Base):
    """Run 的独立实测体重依赖，仅保存冻结范围、摘要和版本引用。"""

    __tablename__ = "health_weight_use"
    run_id = Column(String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True)
    payload_hash = Column(String(64), primary_key=True)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False)
    source_member_id = Column(String(36), ForeignKey("family_members.id"), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    record_refs = Column(JSON_VALUE, nullable=False)


class HealthBloodPressureUse(Base):
    """Run 的独立血压依赖，仅保存冻结范围、摘要和版本引用。"""

    __tablename__ = "health_blood_pressure_use"
    run_id = Column(String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True)
    payload_hash = Column(String(64), primary_key=True)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False)
    source_member_id = Column(String(36), ForeignKey("family_members.id"), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    record_refs = Column(JSON_VALUE, nullable=False)


class HealthBloodGlucoseUse(Base):
    """Run 的独立血糖依赖，仅保存冻结范围、摘要和版本引用。"""

    __tablename__ = "health_blood_glucose_use"
    run_id = Column(String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True)
    payload_hash = Column(String(64), primary_key=True)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False)
    source_member_id = Column(String(36), ForeignKey("family_members.id"), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    record_refs = Column(JSON_VALUE, nullable=False)


class HealthBloodLipidsUse(Base):
    """Run的同条血脂四项依赖，仅保存冻结范围、摘要与版本引用。"""

    __tablename__ = "health_blood_lipids_use"
    run_id = Column(String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True)
    payload_hash = Column(String(64), primary_key=True)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False)
    source_member_id = Column(String(36), ForeignKey("family_members.id"), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    record_refs = Column(JSON_VALUE, nullable=False)


class HealthProcessingConsent(Base):
    """访问权限之外的用途和处理方同意。"""

    __tablename__ = "health_processing_consent"
    member_id = Column(String(36), ForeignKey("family_member.id"), primary_key=True)
    actor_uid = Column(String, ForeignKey("users.uid"), primary_key=True)
    purpose = Column(String(16), primary_key=True)
    processor = Column(String(160), nullable=False)
    policy_version = Column(String(80), nullable=False)
    granted_at = Column(DateTime, default=utc_now_naive, nullable=False)
    revoked_at = Column(DateTime)


class PrivateUpload(Base):
    """随机对象键及清除元数据的处理页。"""

    __tablename__ = "private_upload"
    id = Column(String(36), primary_key=True)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False, index=True)
    purpose = Column(String(16), nullable=False)
    original_key = Column(String(255), nullable=False, unique=True)
    sha256 = Column(String(64), nullable=False)
    mime = Column(String(40), nullable=False)
    byte_size = Column(Integer, nullable=False)
    pages = Column(JSON_VALUE, nullable=False)
    status = Column(String(16), default="active", nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthConsultation(Base):
    """咨询的不可变成员绑定，不从客户端会话 metadata 取身份。"""

    __tablename__ = "health_consultation"
    __table_args__ = (UniqueConstraint("actor_uid", "request_id", name="uq_health_consultation_request"),)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False, index=True)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    request_id = Column(String(36), nullable=False)
    family_planner_selection = Column(JSON_VALUE)
    initial_planner_selection = Column(JSON_VALUE)
    safe_planner_selection = Column(JSON_VALUE)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthSafePlannerPreview(Base):
    """单成员已保存餐单的不可变当前Run安全预览收据。"""

    __tablename__ = "health_safe_planner_preview"
    __table_args__ = (CheckConstraint("operation IN ('swap','regeneration')", name="ck_health_safe_planner_operation"),)
    id = Column(String(36), primary_key=True)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    conversation_id = Column(
        Integer, ForeignKey("health_consultation.conversation_id", ondelete="CASCADE"), nullable=False
    )
    run_id = Column(String(64), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    operation = Column(String(24), nullable=False)
    parameters = Column(JSON_VALUE, nullable=False)
    snapshot = Column(JSON_VALUE, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthFamilyPlannerPreview(Base):
    """家庭模型只读预览的不可变当前Run收据。"""

    __tablename__ = "health_family_planner_preview"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('swap','regeneration','participation')", name="ck_health_family_planner_operation"
        ),
    )
    id = Column(String(36), primary_key=True)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    conversation_id = Column(
        Integer, ForeignKey("health_consultation.conversation_id", ondelete="CASCADE"), nullable=False
    )
    run_id = Column(String(64), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    operation = Column(String(24), nullable=False)
    parameters = Column(JSON_VALUE, nullable=False)
    snapshot = Column(JSON_VALUE, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class VisionJob(Base):
    """业务身份；执行状态唯一属于既有 Task。"""

    __tablename__ = "vision_job"
    __table_args__ = (UniqueConstraint("actor_uid", "member_id", "kind", "request_id", name="uq_vision_job_request"),)
    id = Column(String(36), primary_key=True)
    task_id = Column(String(32), ForeignKey("tasks.id"), nullable=False, unique=True)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    request_id = Column(String(36), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    upload_ids = Column(JSON_VALUE, nullable=False)
    input_snapshot = Column(JSON_VALUE, nullable=False)
    phase = Column(String(32), default="validating", nullable=False)
    result_id = Column(String(36))
    error_code = Column(String(64))
    parent_task_id = Column(String(32))
    created_at = Column(DateTime, default=utc_now_naive, nullable=False, index=True)


class VisionDraft(Base):
    """报告或一餐候选，原始抽取和用户修订分别保留。"""

    __tablename__ = "vision_draft"
    __table_args__ = (CheckConstraint("version > 0", name="ck_vision_draft_version"),)
    id = Column(String(36), primary_key=True)
    job_id = Column(String(36), ForeignKey("vision_job.id"), unique=True)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    review_status = Column(String(32), nullable=False, default="pending_confirmation")
    original_payload = Column(JSON_VALUE, nullable=False)
    payload = Column(JSON_VALUE, nullable=False)
    parser_version = Column(String(80))
    model_version = Column(String(160))
    raw_result_key = Column(String(255))
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class VisionRevision(Base):
    """每次人工纠错或显式重识别的版本与操作人。"""

    __tablename__ = "vision_revision"
    __table_args__ = (UniqueConstraint("draft_id", "version", name="uq_vision_revision_version"),)
    id = Column(String(36), primary_key=True)
    draft_id = Column(String(36), ForeignKey("vision_draft.id"), nullable=False)
    version = Column(Integer, nullable=False)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    payload = Column(JSON_VALUE, nullable=False)
    reason = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class FoodRecord(Base):
    """审核发布的每百克可食部分营养数据版本。"""

    __tablename__ = "health_food_record"
    __table_args__ = (UniqueConstraint("record_code", "dataset_version", name="uq_health_food_version"),)
    id = Column(String(36), primary_key=True)
    record_code = Column(String(100), nullable=False)
    name = Column(String(120), nullable=False, index=True)
    cooking_state = Column(String(40), nullable=False)
    source = Column(String(300), nullable=False)
    license = Column(String(300), nullable=False)
    edition = Column(String(100), nullable=False)
    dataset_version = Column(String(80), nullable=False)
    nutrients = Column(JSON_VALUE, nullable=False)
    recipe_estimated = Column(Boolean, nullable=False, default=False)
    published_by = Column(String, ForeignKey("users.uid"), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class RecipeVersion(Base):
    """不可变配方、可食原料快照与净成品重。"""

    __tablename__ = "health_recipe_version"
    __table_args__ = (
        UniqueConstraint("record_code", "dataset_version", name="uq_health_recipe_version"),
        CheckConstraint("yield_grams > 0", name="ck_health_recipe_yield"),
    )
    id = Column(String(36), primary_key=True)
    record_code = Column(String(100), nullable=False)
    name = Column(String(120), nullable=False, index=True)
    cooking_state = Column(String(40), nullable=False)
    source = Column(String(300), nullable=False)
    license = Column(String(300), nullable=False)
    edition = Column(String(100), nullable=False)
    dataset_version = Column(String(80), nullable=False)
    ingredients = Column(JSON_VALUE, nullable=False)
    yield_grams = Column(Numeric(16, 6), nullable=False)
    nutrients = Column(JSON_VALUE, nullable=False)
    published_by = Column(String, ForeignKey("users.uid"), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class PortionReference(Base):
    """与食品或食谱版本绑定的审核份量规格。"""

    __tablename__ = "health_portion_reference"
    __table_args__ = (
        CheckConstraint("(food_id IS NOT NULL) <> (recipe_version_id IS NOT NULL)", name="ck_health_portion_target"),
        CheckConstraint("grams_per_unit > 0", name="ck_health_portion_grams"),
        UniqueConstraint("food_id", "unit_label", "dataset_version", name="uq_health_food_portion_version"),
        UniqueConstraint("recipe_version_id", "unit_label", "dataset_version", name="uq_health_recipe_portion_version"),
    )
    id = Column(String(36), primary_key=True)
    food_id = Column(String(36), ForeignKey("health_food_record.id"), index=True)
    recipe_version_id = Column(String(36), ForeignKey("health_recipe_version.id"), index=True)
    unit_label = Column(String(80), nullable=False)
    grams_per_unit = Column(Numeric(16, 6), nullable=False)
    source = Column(String(300), nullable=False)
    license = Column(String(300), nullable=False)
    edition = Column(String(100), nullable=False)
    dataset_version = Column(String(80), nullable=False)
    applicable_scope = Column(String(300), nullable=False)
    published_by = Column(String, ForeignKey("users.uid"), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class NutritionCalculation(Base):
    """草稿版本对应的不可变营养计算。"""

    __tablename__ = "nutrition_calculation"
    id = Column(String(36), primary_key=True)
    draft_id = Column(String(36), ForeignKey("vision_draft.id"), nullable=False, index=True)
    draft_version = Column(Integer, nullable=False)
    input_hash = Column(String(64), nullable=False)
    input_snapshot = Column(JSON_VALUE, nullable=False)
    result = Column(JSON_VALUE, nullable=False)
    calculation_version = Column(String(40), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class VisionConfirmation(Base):
    """与正式记录在一个事务提交的一次确认。"""

    __tablename__ = "vision_confirmation"
    __table_args__ = (
        UniqueConstraint("actor_uid", "member_id", "kind", "request_id", name="uq_vision_confirmation_request"),
    )
    id = Column(String(36), primary_key=True)
    draft_id = Column(String(36), ForeignKey("vision_draft.id"), nullable=False, unique=True)
    draft_version = Column(Integer, nullable=False)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False)
    kind = Column(String(16), nullable=False)
    request_id = Column(String(36), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    target_ids = Column(JSON_VALUE, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthObservation(Base):
    """用户已接受的指标时间点，不覆盖历史。"""

    __tablename__ = "health_observation"
    id = Column(String(36), primary_key=True)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False, index=True)
    confirmation_id = Column(String(36), ForeignKey("vision_confirmation.id"), nullable=False)
    field_id = Column(String(36), nullable=False)
    snapshot = Column(JSON_VALUE, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class DietLog(Base):
    """一餐已确认的输入、份量来源与营养快照。"""

    __tablename__ = "diet_log"
    id = Column(String(36), primary_key=True)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False, index=True)
    confirmation_id = Column(String(36), ForeignKey("vision_confirmation.id"), nullable=False)
    calculation_id = Column(String(36), ForeignKey("nutrition_calculation.id"), nullable=False)
    snapshot = Column(JSON_VALUE, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class MealFeedback(Base):
    """账号私有的单餐自述及当前版本。"""

    __tablename__ = "meal_feedback"
    __table_args__ = (UniqueConstraint("actor_uid", "diet_log_id", name="uq_meal_feedback_slot"),)
    id = Column(String(36), primary_key=True)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False, index=True)
    diet_log_id = Column(String(36), ForeignKey("diet_log.id", ondelete="CASCADE"), nullable=False)
    details = Column(JSON_VALUE, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(16), nullable=False, default="active")
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)


class MealFeedbackRevision(Base):
    """不可变修订和幂等收据，撤回后旧请求不能复活。"""

    __tablename__ = "meal_feedback_revision"
    __table_args__ = (
        UniqueConstraint("feedback_id", "version", name="uq_meal_feedback_revision"),
        UniqueConstraint("actor_uid", "request_id", name="uq_meal_feedback_request"),
    )
    id = Column(String(36), primary_key=True)
    feedback_id = Column(String(36), ForeignKey("meal_feedback.id", ondelete="CASCADE"), nullable=False)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    request_id = Column(String(36), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False)
    details = Column(JSON_VALUE, nullable=False)
    status = Column(String(16), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class MealFeedbackUse(Base):
    """模型调用前提交的单餐反馈版本依赖。"""

    __tablename__ = "meal_feedback_use"
    run_id = Column(String(64), ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True)
    feedback_id = Column(String(36), ForeignKey("meal_feedback.id", ondelete="CASCADE"), primary_key=True)
    version = Column(Integer, primary_key=True)


class HealthFeedbackConversation(Base):
    """由用户业务选餐建立的不可变会话来源，不取客户端metadata。"""

    __tablename__ = "health_feedback_conversation"
    conversation_id = Column(
        Integer, ForeignKey("health_consultation.conversation_id", ondelete="CASCADE"), primary_key=True
    )
    diet_log_id = Column(String(36), ForeignKey("diet_log.id"), nullable=False)
    source_version = Column(Integer, nullable=False)


class HealthFeedbackWrite(Base):
    """反馈修订与当前服务器原消息、Run共同绑定的不可变来源。"""

    __tablename__ = "health_feedback_write"
    revision_id = Column(String(36), ForeignKey("meal_feedback_revision.id", ondelete="CASCADE"), primary_key=True)
    source_message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(String(64), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, unique=True)
    conversation_id = Column(
        Integer,
        ForeignKey("health_feedback_conversation.conversation_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )


class NutritionEvidence(Base):
    """已专业审核的通用科普片段；修订发布新版本，旧版本仅可撤回。"""

    __tablename__ = "nutrition_evidence"
    id = Column(String(36), primary_key=True)
    source_ref = Column(String(500), nullable=False)
    source_version = Column(String(80), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    review_ref = Column(String(500), nullable=False)
    reviewed_by = Column(String(100), nullable=False)
    reviewed_at = Column(DateTime, nullable=False)
    valid_until = Column(DateTime, nullable=False)
    published_by = Column(String, ForeignKey("users.uid"), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    revoked_at = Column(DateTime)


class NutritionEvidenceCitation(Base):
    """运行内检索回执，引用来源绑定到同一成员、账号和咨询线程。"""

    __tablename__ = "nutrition_evidence_citation"
    id = Column(String(36), primary_key=True)
    evidence_id = Column(String(36), ForeignKey("nutrition_evidence.id"), nullable=False, index=True)
    run_id = Column(String(64), ForeignKey("agent_runs.id"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    content_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthMemoryFact(Base):
    """账号成员范围的用户自述；当前版本不属于正式健康档案。"""

    __tablename__ = "health_memory_fact"
    __table_args__ = (UniqueConstraint("actor_uid", "member_id", "fact_key", name="uq_health_memory_slot"),)
    id = Column(String(36), primary_key=True)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False, index=True)
    fact_key = Column(String(64), nullable=False)
    kind = Column(String(24), nullable=False)
    content = Column(String(500), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(16), nullable=False, default="active")
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthMemoryRevision(Base):
    """不可变记忆修订与请求收据，防止工具重放重复写入。"""

    __tablename__ = "health_memory_revision"
    __table_args__ = (
        UniqueConstraint("fact_id", "version", name="uq_health_memory_revision"),
        UniqueConstraint("actor_uid", "request_id", "source_hash", name="uq_health_memory_source"),
    )
    id = Column(String(36), primary_key=True)
    fact_id = Column(String(36), ForeignKey("health_memory_fact.id", ondelete="CASCADE"), nullable=False)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    version = Column(Integer, nullable=False)
    request_id = Column(String(64), nullable=False)
    source_hash = Column(String(64), nullable=False)
    source_message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"))
    source_run_id = Column(String(64), ForeignKey("agent_runs.id", ondelete="SET NULL"))
    content = Column(String(500), nullable=False)
    kind = Column(String(24), nullable=False)
    status = Column(String(16), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthMemoryUse(Base):
    """模型调用前提交的版本依赖，撤回不依赖 checkpoint 工具收据。"""

    __tablename__ = "health_memory_use"
    run_id = Column(String(64), ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True)
    fact_id = Column(String(36), ForeignKey("health_memory_fact.id", ondelete="CASCADE"), primary_key=True)
    version = Column(Integer, primary_key=True)


class HealthDailyConversation(Base):
    """北京时间每日会话及原子发布的消息摘录摘要。"""

    __tablename__ = "health_daily_conversation"
    __table_args__ = (UniqueConstraint("actor_uid", "member_id", "business_date", name="uq_health_daily_scope"),)
    conversation_id = Column(
        Integer, ForeignKey("health_consultation.conversation_id", ondelete="CASCADE"), primary_key=True
    )
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False)
    business_date = Column(Date, nullable=False, index=True)
    summary = Column(JSON_VALUE)
    summary_fingerprint = Column(String(64))
    summary_version = Column(Integer, nullable=False, default=0)
    summary_generated_at = Column(DateTime)
    summary_checked_at = Column(DateTime)


class HealthMealPlanPreview(Base):
    """服务器计算的三餐预览；模型运行回执不能跨Run引用。"""

    __tablename__ = "health_meal_plan_preview"
    id = Column(String(36), primary_key=True)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False, index=True)
    run_id = Column(String(64), ForeignKey("agent_runs.id", ondelete="SET NULL"), index=True)
    spec = Column(JSON_VALUE, nullable=False)
    snapshot = Column(JSON_VALUE, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthInitialPlanPreview(Base):
    """批准初始配餐的独立回执，确认时重新核对全部当前来源。"""

    __tablename__ = "health_initial_plan_preview"
    id = Column(String(36), primary_key=True)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("health_consultation.conversation_id", ondelete="SET NULL"))
    run_id = Column(String(64), ForeignKey("agent_runs.id", ondelete="SET NULL"), index=True)
    selection = Column(JSON_VALUE, nullable=False)
    snapshot = Column(JSON_VALUE, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthMealPlan(Base):
    """用户保存的账号私有餐单草稿，不是已审核个性化方案。"""

    __tablename__ = "health_meal_plan"
    __table_args__ = (CheckConstraint("version > 0", name="ck_health_meal_plan_version"),)
    id = Column(String(36), primary_key=True)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    spec = Column(JSON_VALUE, nullable=False)
    snapshot = Column(JSON_VALUE, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthMealPlanRevision(Base):
    """保存及换菜的不可变快照、操作理由与幂等收据。"""

    __tablename__ = "health_meal_plan_revision"
    __table_args__ = (
        UniqueConstraint("plan_id", "version", name="uq_health_meal_plan_revision"),
        UniqueConstraint("actor_uid", "request_id", name="uq_health_meal_plan_request"),
    )
    id = Column(String(36), primary_key=True)
    plan_id = Column(String(36), ForeignKey("health_meal_plan.id", ondelete="CASCADE"), nullable=False)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    request_id = Column(String(36), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False)
    reason = Column(String(500), nullable=False)
    spec = Column(JSON_VALUE, nullable=False)
    snapshot = Column(JSON_VALUE, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthProfileSnapshot(Base):
    """外部正式档案的不可变AI读取投影，不拥有建档与确认流程。"""

    __tablename__ = "health_profile_snapshot"
    __table_args__ = (UniqueConstraint("member_id", "version", name="uq_health_profile_snapshot"),)
    id = Column(String(36), primary_key=True)
    member_id = Column(String(36), ForeignKey("family_member.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    payload = Column(JSON_VALUE, nullable=False)
    content_hash = Column(String(64), nullable=False)
    attestation = Column(JSON_VALUE, nullable=False)
    attested_at = Column(DateTime, nullable=False)
    valid_until = Column(DateTime, nullable=False)
    imported_by = Column(String, ForeignKey("users.uid"), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    revoked_at = Column(DateTime)


class HealthRuleSnapshot(Base):
    """外部批准规则版本，临床口径由专业内容方拥有。"""

    __tablename__ = "health_rule_snapshot"
    __table_args__ = (UniqueConstraint("rule_code", "version", name="uq_health_rule_snapshot"),)
    id = Column(String(36), primary_key=True)
    rule_code = Column(String(80), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    payload = Column(JSON_VALUE, nullable=False)
    content_hash = Column(String(64), nullable=False)
    attestation = Column(JSON_VALUE, nullable=False)
    attested_at = Column(DateTime, nullable=False)
    valid_until = Column(DateTime, nullable=False)
    imported_by = Column(String, ForeignKey("users.uid"), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    revoked_at = Column(DateTime)


class HealthProfessionalReviewer(Base):
    """独立专业资格的外部登记版本，管理员角色不等于审核资格。"""

    __tablename__ = "health_professional_reviewer"
    reviewer_uid = Column(String, ForeignKey("users.uid"), primary_key=True)
    version = Column(Integer, primary_key=True)
    attestation = Column(JSON_VALUE, nullable=False)
    content_hash = Column(String(64), nullable=False)
    attested_at = Column(DateTime, nullable=False)
    valid_until = Column(DateTime, nullable=False)
    registered_by = Column(String, ForeignKey("users.uid"), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    revoked_at = Column(DateTime)


class HealthQualityCheck(Base):
    """独立服务器检查回执，绑定保存对象、外部版本及可选执行Owner。"""

    __tablename__ = "health_quality_check"
    __table_args__ = (UniqueConstraint("actor_uid", "request_id", name="uq_health_quality_request"),)
    id = Column(String(36), primary_key=True)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False, index=True)
    plan_id = Column(String(36), ForeignKey("health_meal_plan.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_version = Column(Integer, nullable=False)
    rule_code = Column(String(80), nullable=False)
    rule_id = Column(String(36), ForeignKey("health_rule_snapshot.id"))
    request_id = Column(String(36), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    run_id = Column(String(64), ForeignKey("agent_runs.id", ondelete="SET NULL"), unique=True)
    snapshot = Column(JSON_VALUE, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthProfessionalReview(Base):
    """当前审核流程状态，检查与专业批准为独立事实。"""

    __tablename__ = "health_professional_review"
    id = Column(String(36), primary_key=True)
    check_id = Column(
        String(36), ForeignKey("health_quality_check.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    member_id = Column(String(36), ForeignKey("family_member.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False)
    reviewer_uid = Column(String, ForeignKey("users.uid"))
    reviewer_version = Column(Integer)
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)
    invalidation_reason = Column(String(80))


class HealthReviewAction(Base):
    """专业和提交动作的不可变理由、证据与幂等收据。"""

    __tablename__ = "health_review_action"
    __table_args__ = (
        UniqueConstraint("review_id", "version", name="uq_health_review_action_version"),
        UniqueConstraint("actor_uid", "request_id", name="uq_health_review_action_request"),
    )
    id = Column(String(36), primary_key=True)
    review_id = Column(String(36), ForeignKey("health_professional_review.id", ondelete="CASCADE"), nullable=False)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    request_id = Column(String(36), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False)
    reason = Column(String(500), nullable=False)
    evidence_refs = Column(JSON_VALUE, nullable=False)
    reviewer_attestation = Column(JSON_VALUE)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthQualityConversation(Base):
    """用户选定餐单/版本/规则的不可变质量检查会话。"""

    __tablename__ = "health_quality_conversation"
    conversation_id = Column(
        Integer, ForeignKey("health_consultation.conversation_id", ondelete="CASCADE"), primary_key=True
    )
    plan_id = Column(String(36), ForeignKey("health_meal_plan.id", ondelete="CASCADE"), nullable=False)
    plan_version = Column(Integer, nullable=False)
    rule_code = Column(String(80), nullable=False)


class HealthNextDayProposal(Base):
    """账号私有次日提议，预览来源与提议快照保持不可变。"""

    __tablename__ = "health_next_day_proposal"
    __table_args__ = (UniqueConstraint("actor_uid", "request_id", name="uq_health_next_day_request"),)
    id = Column(String(36), primary_key=True)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    member_id = Column(String(36), ForeignKey("family_member.id", ondelete="CASCADE"), nullable=False)
    preview_id = Column(String(36), ForeignKey("health_meal_plan_preview.id", ondelete="CASCADE"), nullable=False)
    source_date = Column(Date, nullable=False)
    plan_date = Column(Date, nullable=False)
    request_id = Column(String(36), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    source_hash = Column(String(64), nullable=False)
    snapshot = Column(JSON_VALUE, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthMealPlanAdoption(Base):
    """正式采用的不可变方案/来源快照与可失效的使用状态。"""

    __tablename__ = "health_meal_plan_adoption"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_health_adoption_version"),
        CheckConstraint(
            "status IN ('active','withdrawn','superseded','invalidated')", name="ck_health_adoption_status"
        ),
        Index(
            "uq_health_active_adoption",
            "actor_uid",
            "member_id",
            "plan_date",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )
    id = Column(String(36), primary_key=True)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    member_id = Column(String(36), ForeignKey("family_member.id", ondelete="CASCADE"), nullable=False)
    plan_id = Column(String(36), ForeignKey("health_meal_plan.id", ondelete="CASCADE"), nullable=False)
    plan_version = Column(Integer, nullable=False)
    plan_date = Column(Date, nullable=False)
    review_id = Column(String(36), ForeignKey("health_professional_review.id", ondelete="CASCADE"), nullable=False)
    sources = Column(JSON_VALUE, nullable=False)
    snapshot = Column(JSON_VALUE, nullable=False)
    status = Column(String(24), nullable=False)
    version = Column(Integer, nullable=False)
    reason = Column(String(500))
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, nullable=False)


class HealthMealPlanAdoptionMember(Base):
    """账号内逐成员当日采用指针，有效状态仅由关联采用拥有。"""

    __tablename__ = "health_meal_plan_adoption_member"
    actor_uid = Column(String, ForeignKey("users.uid"), primary_key=True)
    member_id = Column(String(36), ForeignKey("family_member.id", ondelete="CASCADE"), primary_key=True)
    plan_date = Column(Date, primary_key=True)
    adoption_id = Column(String(36), ForeignKey("health_meal_plan_adoption.id", ondelete="CASCADE"), nullable=False)


class HealthMealPlanAdoptionAction(Base):
    """采用与取消的不可变动作及共享幂等收据。"""

    __tablename__ = "health_meal_plan_adoption_action"
    __table_args__ = (UniqueConstraint("actor_uid", "request_id", name="uq_health_adoption_request"),)
    id = Column(String(36), primary_key=True)
    adoption_id = Column(String(36), ForeignKey("health_meal_plan_adoption.id", ondelete="CASCADE"), nullable=False)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    request_id = Column(String(36), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    operation = Column(String(24), nullable=False)
    version = Column(Integer, nullable=False)
    reason = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)


HEALTH_TABLES = [
    model.__table__
    for model in (
        FamilyMember,
        HealthGrant,
        HealthFamilyProfileLink,
        HealthFamilyProfileUse,
        HealthWeightUse,
        HealthBloodPressureUse,
        HealthBloodGlucoseUse,
        HealthBloodLipidsUse,
        HealthProcessingConsent,
        HealthConsultation,
        HealthSafePlannerPreview,
        HealthFamilyPlannerPreview,
        PrivateUpload,
        VisionJob,
        VisionDraft,
        VisionRevision,
        FoodRecord,
        RecipeVersion,
        PortionReference,
        NutritionCalculation,
        VisionConfirmation,
        HealthObservation,
        DietLog,
        MealFeedback,
        MealFeedbackRevision,
        MealFeedbackUse,
        HealthFeedbackConversation,
        HealthFeedbackWrite,
        NutritionEvidence,
        NutritionEvidenceCitation,
        HealthMemoryFact,
        HealthMemoryRevision,
        HealthMemoryUse,
        HealthDailyConversation,
        HealthMealPlanPreview,
        HealthInitialPlanPreview,
        HealthMealPlan,
        HealthMealPlanRevision,
        HealthProfileSnapshot,
        HealthRuleSnapshot,
        HealthProfessionalReviewer,
        HealthQualityCheck,
        HealthProfessionalReview,
        HealthReviewAction,
        HealthQualityConversation,
        HealthNextDayProposal,
        HealthMealPlanAdoption,
        HealthMealPlanAdoptionMember,
        HealthMealPlanAdoptionAction,
    )
]
