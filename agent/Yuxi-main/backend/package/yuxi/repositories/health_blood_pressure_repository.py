"""本人独立血压测量的必要投影及专用回执。"""

from yuxi.repositories.health_measurement_repository import HealthMeasurementRepository
from yuxi.storage.postgres.models_health import HealthBloodPressureUse


class HealthBloodPressureRepository(HealthMeasurementRepository):
    """仅返回原始收缩压、舒张压及独立测量来源版本。"""

    kind = "blood_pressure"
    label = "血压"
    use_model = HealthBloodPressureUse
    value_fields = {"systolic": "systolic", "diastolic": "diastolic"}
