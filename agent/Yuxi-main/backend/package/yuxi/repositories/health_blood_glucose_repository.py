"""本人独立血糖的必要投影及专用回执。"""

from yuxi.repositories.health_measurement_repository import HealthMeasurementRepository
from yuxi.storage.postgres.models_health import HealthBloodGlucoseUse


class HealthBloodGlucoseRepository(HealthMeasurementRepository):
    """返回原始血糖与明确测量条件，不生成临床判断。"""

    kind = "blood_glucose"
    label = "血糖"
    use_model = HealthBloodGlucoseUse
    value_fields = {"glucose": "glucose"}
