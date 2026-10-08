"""本人独立体重测量的既有投影及回执协议。"""

from yuxi.repositories.health_measurement_repository import HealthMeasurementRepository
from yuxi.storage.postgres.models_health import HealthWeightUse


class HealthWeightRepository(HealthMeasurementRepository):
    """保留体重公开接口、原值投影和既有依赖表。"""

    kind = "weight"
    label = "体重"
    use_model = HealthWeightUse
    value_fields = {"value": "weight"}
