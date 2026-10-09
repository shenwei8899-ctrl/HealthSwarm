"""真实配餐探针仅接受显式外部模型，不选择默认或本地回放。"""

import ipaddress
import json
from dataclasses import dataclass, field
from urllib.parse import urlsplit


class LiveModelNotConfigured(ValueError):
    """未开启或缺少真实模型输入时由测试明确跳过。"""


@dataclass(frozen=True)
class LivePlannerModel:
    """本轮临时供应商参数，凭据及附加配置不进入诊断表示。"""

    provider_type: str
    base_url: str
    model_id: str
    api_key: str = field(repr=False)
    headers_json: dict = field(repr=False)
    extra_json: dict = field(repr=False)
    model_json: dict = field(repr=False)
    include_user_uid: bool


def load_live_inputs(environ):
    """先检查显式开关，再验证不含秘密的固定输入边界。"""
    if environ.get("RUN_HEALTH_SAFE_PLANNER_REAL_MODEL") != "1":
        raise LiveModelNotConfigured("真实模型探针未显式开启")
    prefix = "HEALTH_SAFE_PLANNER_LIVE_"
    fields = ("PROVIDER_TYPE", "BASE_URL", "API_KEY", "MODEL_ID")
    if any(not environ.get(prefix + name, "").strip() for name in fields):
        raise LiveModelNotConfigured("真实模型探针缺少显式供应商参数")
    provider_type, base_url, api_key, model_id = (environ[prefix + name].strip() for name in fields)
    if provider_type not in {"openai", "openrouter"}:
        raise ValueError("配餐用途需要兼容的聊天供应商类型")
    if any(ord(char) < 32 for value in (base_url, api_key, model_id) for char in value):
        raise ValueError("真实模型输入不能包含控制字符")
    if ":" in model_id or any(word in model_id.lower() for word in ("latest", "preview", "deterministic", "replay")):
        raise ValueError("真实配餐探针需要固定模型，拒绝浮动或回放模型")
    if api_key.lower().startswith("synthetic-"):
        raise ValueError("真实配餐探针不能使用合成回放凭据")
    _require_external_url(base_url)
    headers = _json_object(environ.get(prefix + "HEADERS_JSON", "{}"))
    extra = _json_object(environ.get(prefix + "EXTRA_JSON", "{}"))
    model = _json_object(environ.get(prefix + "MODEL_JSON", "{}"))
    if model and (model.get("id") != model_id or model.get("type") != "chat"):
        raise ValueError("所选模型记录必须与明确聊天模型一致")
    if model.get("base_url_override"):
        _require_external_url(model["base_url_override"])
    include_uid = environ.get(prefix + "INCLUDE_USER_UID", "false")
    if include_uid not in {"true", "false"}:
        raise ValueError("用户标识发送选项必须为明确布尔值")
    return LivePlannerModel(provider_type, base_url, model_id, api_key, headers, extra, model, include_uid == "true")


def _require_external_url(base_url):
    """不解析DNS，仅拒绝当前探针明确的本地、私网与回放地址。"""
    if not isinstance(base_url, str):
        raise ValueError("真实模型端点格式无效")
    try:
        parsed = urlsplit(base_url)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        raise ValueError("真实模型端点格式无效") from None
    if (
        parsed.scheme != "https"
        or not host
        or "." not in host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
        or host in {"localhost", "host.docker.internal"}
        or host.endswith((".localhost", ".local", ".internal", ".invalid", ".test", ".example"))
        or "replay" in host
    ):
        raise ValueError("真实模型端点必须是明确外部HTTPS服务")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError("真实模型端点不能是本地或私网地址")


def _json_object(value):
    """附加供应商参数保留原Owner形态，不把解析错误中的内容输出。"""
    try:
        result = json.loads(value)
    except (ValueError, TypeError):
        raise ValueError("附加供应商配置必须是合法JSON对象") from None
    if not isinstance(result, dict):
        raise ValueError("附加供应商配置必须是JSON对象")
    return result
