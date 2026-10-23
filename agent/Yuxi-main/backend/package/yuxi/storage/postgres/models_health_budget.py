"""项目健康 AI 价格批准、月额度与逐次外呼账本。"""

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Numeric, String

from yuxi.storage.postgres.models_business import Base, JSON_VALUE
from yuxi.utils.datetime_utils import utc_now_naive


class HealthAiOpening(Base):
    """启用时登记本月既有费用，避免中途部署把已花金额清零。"""

    __tablename__ = "health_ai_opening"
    id = Column(Integer, primary_key=True)
    month = Column(Date, nullable=False)
    occupied_cny = Column(Numeric(18, 6), nullable=False)
    evidence = Column(String(2000), nullable=False)
    approved_by = Column(String, nullable=False)
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_health_ai_opening_singleton"),
        CheckConstraint("occupied_cny >= 0 AND occupied_cny <= 40", name="ck_health_ai_opening_amount"),
    )


class HealthAiPrice(Base):
    """价格版本保留审批依据，实际处理配置改变后须重新批准。"""

    __tablename__ = "health_ai_price"
    id = Column(String(36), primary_key=True)
    target = Column(String(64), nullable=False, index=True)
    kind = Column(String(10), nullable=False)
    specification = Column(JSON_VALUE, nullable=False)
    approved_by = Column(String, nullable=False)
    approved_at = Column(DateTime, default=utc_now_naive, nullable=False)
    valid_until = Column(DateTime, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)


class HealthAiMonth(Base):
    """月占用包含已结算支出和全部未决预留。"""

    __tablename__ = "health_ai_month"
    month = Column(Date, primary_key=True)
    occupied_cny = Column(Numeric(18, 6), nullable=False, default=0)
    blocked = Column(Boolean, nullable=False, default=False)
    __table_args__ = (CheckConstraint("occupied_cny >= 0 AND occupied_cny <= 40", name="ck_health_ai_month_limit"),)


class HealthAiCall(Base):
    """外呼前提交预留，缺失回执和进程丢失不释放额度。"""

    __tablename__ = "health_ai_call"
    id = Column(String(36), primary_key=True)
    month = Column(Date, ForeignKey("health_ai_month.month"), nullable=False, index=True)
    price_id = Column(String(36), ForeignKey("health_ai_price.id"), nullable=False)
    purpose = Column(String(24), nullable=False)
    owner_id = Column(String(64), nullable=False, index=True)
    reserved_cny = Column(Numeric(18, 6), nullable=False)
    charged_cny = Column(Numeric(18, 6))
    status = Column(String(16), nullable=False, default="reserved")
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    finished_at = Column(DateTime)
    __table_args__ = (
        CheckConstraint("reserved_cny > 0 AND reserved_cny <= 40", name="ck_health_ai_call_reservation"),
        CheckConstraint(
            "charged_cny IS NULL OR (charged_cny >= 0 AND charged_cny <= reserved_cny)", name="ck_health_ai_call_charge"
        ),
        CheckConstraint("status IN ('reserved', 'settled', 'unknown')", name="ck_health_ai_call_status"),
    )


HEALTH_BUDGET_TABLES = [model.__table__ for model in (HealthAiOpening, HealthAiPrice, HealthAiMonth, HealthAiCall)]
