"""对话购买只接受服务器回执，不接收客户端商品、价格或成员身份。"""

from pydantic import Field
from yuxi.services.health_vision_types import HealthDTO


class ConversationPurchaseInput(HealthDTO):
    """原回执同请求重放，商城创建仍使用确定性幂等键。"""

    offer_token: str = Field(min_length=100, max_length=4096, pattern=r"^[A-Za-z0-9_-]+$")
