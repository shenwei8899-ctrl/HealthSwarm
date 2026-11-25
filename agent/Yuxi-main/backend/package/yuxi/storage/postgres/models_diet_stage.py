"""成员阶段、独立周行动及私有生成结果。"""

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text

from yuxi.storage.postgres.models_business import Base, JSON_VALUE
from yuxi.utils.datetime_utils import utc_now_naive


class DietStage(Base):
    """用户确认的当前目标，行动计次不改变此版本。"""

    __tablename__ = "health_diet_stage"
    __table_args__ = (
        Index("uq_diet_stage_open", "member_id", unique=True, postgresql_where=text("status = 'active'")),
    )
    id = Column(String(36), primary_key=True)
    family_id = Column(String(36), ForeignKey("family_archives.id"), nullable=False, index=True)
    member_id = Column(String(36), ForeignKey("family_members.id"), nullable=False, index=True)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    starts_on = Column(Date, nullable=False)
    review_on = Column(Date, nullable=False, index=True)
    status = Column(String(16), nullable=False, default="active")
    version = Column(Integer, nullable=False, default=1)
    goals = Column(JSON_VALUE, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)
    checked_at = Column(DateTime, index=True)


class DietStageWrite(Base):
    """保存不可变操作收据及目标修订，原键重试不重复计次。"""

    __tablename__ = "health_diet_stage_write"
    __table_args__ = (UniqueConstraint("actor_uid", "request_id", name="uq_diet_stage_write"),)
    id = Column(String(36), primary_key=True)
    stage_id = Column(String(36), ForeignKey("health_diet_stage.id"), nullable=False, index=True)
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    request_id = Column(String(36), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    snapshot = Column(JSON_VALUE, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)


class DietActionWeek(Base):
    """少量行动作为一个原子版本，保留每项稳定身份。"""

    __tablename__ = "health_diet_action_week"
    __table_args__ = (UniqueConstraint("stage_id", "starts_on", name="uq_diet_stage_week"),)
    id = Column(String(36), primary_key=True)
    stage_id = Column(String(36), ForeignKey("health_diet_stage.id"), nullable=False, index=True)
    starts_on = Column(Date, nullable=False)
    ends_on = Column(Date, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    goal_version = Column(Integer, nullable=False, default=1)
    actions = Column(JSON_VALUE, nullable=False)


class DietStageReview(Base):
    """建议及复盘按操作者隔离，来源变化后不能展示旧正文。"""

    __tablename__ = "health_diet_stage_review"
    __table_args__ = (UniqueConstraint("actor_uid", "request_id", name="uq_diet_stage_review_request"),)
    id = Column(String(36), primary_key=True)
    family_id = Column(String(36), ForeignKey("family_archives.id"), nullable=False)
    member_id = Column(String(36), ForeignKey("family_members.id"), nullable=False, index=True)
    stage_id = Column(String(36), ForeignKey("health_diet_stage.id"))
    actor_uid = Column(String, ForeignKey("users.uid"), nullable=False)
    request_id = Column(String(36), nullable=False)
    kind = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    task_id = Column(String(64))
    input_hash = Column(String(64), nullable=False)
    sources = Column(JSON_VALUE, nullable=False)
    result = Column(JSON_VALUE)
    error = Column(String(200))
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)


DIET_STAGE_TABLES = [model.__table__ for model in (DietStage, DietStageWrite, DietActionWeek, DietStageReview)]
