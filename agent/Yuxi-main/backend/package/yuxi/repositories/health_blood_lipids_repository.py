"""本人同条血脂四项的必要投影及专用回执。"""

from yuxi.repositories.health_measurement_repository import HealthMeasurementRepository
from yuxi.storage.postgres.models_health import HealthBloodLipidsUse


class HealthBloodLipidsRepository(HealthMeasurementRepository):
    """整条读取四项原值与独立版本，不计算比值或生成临床判断。"""

    kind = "blood_lipids"
    label = "血脂四项"
    use_model = HealthBloodLipidsUse
    value_fields = {"tc": "tc", "tg": "tg", "hdl": "hdl", "ldl": "ldl"}
