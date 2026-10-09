"""真实配餐入口拒绝默认、回放及私网，诊断不泄露凭据。"""

import json

import pytest

from test.support.health_safe_planner_live_inputs import LiveModelNotConfigured, load_live_inputs

pytestmark = pytest.mark.unit


def valid_inputs():
    """只提供无网络访问的公开格式测试参数。"""
    return {
        "RUN_HEALTH_SAFE_PLANNER_REAL_MODEL": "1",
        "HEALTH_SAFE_PLANNER_LIVE_PROVIDER_TYPE": "openai",
        "HEALTH_SAFE_PLANNER_LIVE_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "HEALTH_SAFE_PLANNER_LIVE_MODEL_ID": "qwen-plus-2025-07-28",
        "HEALTH_SAFE_PLANNER_LIVE_API_KEY": "unit-secret-never-used",
    }


def test_explicit_fixed_cloud_model_preserves_owner_metadata_without_leaking_secrets():
    """主Owner的所选模型与参数完整保留，repr不能包含任何秘密。"""
    values = valid_inputs()
    model = {
        "id": "qwen-plus-2025-07-28",
        "type": "chat",
        "source": "manual",
        "request_body_overrides": {"enable_thinking": False},
    }
    values.update(
        HEALTH_SAFE_PLANNER_LIVE_HEADERS_JSON=json.dumps({"x-private": "header-secret"}),
        HEALTH_SAFE_PLANNER_LIVE_EXTRA_JSON=json.dumps({"private": "extra-secret"}),
        HEALTH_SAFE_PLANNER_LIVE_MODEL_JSON=json.dumps(model),
        HEALTH_SAFE_PLANNER_LIVE_INCLUDE_USER_UID="false",
    )
    configured = load_live_inputs(values)
    assert configured.model_json == model and configured.model_id == model["id"]
    assert configured.headers_json == {"x-private": "header-secret"}
    assert configured.extra_json == {"private": "extra-secret"}
    assert not configured.include_user_uid
    assert all(secret not in repr(configured) for secret in ("unit-secret", "header-secret", "extra-secret"))


@pytest.mark.parametrize("switch", [None, "", "true", "0"])
def test_live_probe_needs_exact_opt_in(switch):
    """保留真实参数也不能隐式触发外呼。"""
    values = valid_inputs()
    if switch is None:
        values.pop("RUN_HEALTH_SAFE_PLANNER_REAL_MODEL")
    else:
        values["RUN_HEALTH_SAFE_PLANNER_REAL_MODEL"] = switch
    with pytest.raises(LiveModelNotConfigured, match="未显式开启"):
        load_live_inputs(values)


@pytest.mark.parametrize("missing", ["PROVIDER_TYPE", "BASE_URL", "MODEL_ID", "API_KEY"])
def test_missing_external_input_has_explicit_skip_reason(missing):
    """任何必填缺失都没有默认模型或供应商。"""
    values = valid_inputs()
    values.pop("HEALTH_SAFE_PLANNER_LIVE_" + missing)
    with pytest.raises(LiveModelNotConfigured, match="缺少显式"):
        load_live_inputs(values)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://api:8766/v1",
        "https://localhost/v1",
        "https://127.0.0.1/v1",
        "https://10.0.0.2/v1",
        "https://host.docker.internal/v1",
        "https://replay.aliyuncs.com/v1",
        "https://user:password@dashscope.aliyuncs.com/v1",
        "https://dashscope.aliyuncs.com/v1?key=secret",
    ],
)
def test_replay_private_or_secret_bearing_endpoints_are_rejected(endpoint):
    """错误地址不能借live标记成为通过的真实模型证据。"""
    values = valid_inputs()
    values["HEALTH_SAFE_PLANNER_LIVE_BASE_URL"] = endpoint
    with pytest.raises(ValueError, match="端点"):
        load_live_inputs(values)


def test_public_provider_with_local_model_override_cannot_masquerade_as_live():
    """实际模型端点覆盖仍必须是外部服务，公开provider地址不能遮蔽回放。"""
    values = valid_inputs()
    values["HEALTH_SAFE_PLANNER_LIVE_MODEL_JSON"] = json.dumps(
        {
            "id": "qwen-plus-2025-07-28",
            "type": "chat",
            "base_url_override": "http://api:8766/v1",
        }
    )
    with pytest.raises(ValueError, match="端点"):
        load_live_inputs(values)


@pytest.mark.parametrize(
    "model", ["qwen-latest", "qwen-preview", "deterministic-safe-meal-plan-20261009", "replay-model", "provider:model"]
)
def test_floating_or_replay_model_is_not_accepted(model):
    """明确版本不允许替换成别名或回放。"""
    values = valid_inputs()
    values["HEALTH_SAFE_PLANNER_LIVE_MODEL_ID"] = model
    with pytest.raises(ValueError, match="固定模型"):
        load_live_inputs(values)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("PROVIDER_TYPE", "anthropic", "兼容"),
        ("API_KEY", "synthetic-safe-planner-key", "合成回放"),
        ("API_KEY", "private-key\ninvalid", "控制字符"),
        ("MODEL_JSON", '{"id":"another-model","type":"chat"}', "所选模型"),
        ("MODEL_JSON", '{"id":"qwen-plus-2025-07-28","type":"embedding"}', "所选模型"),
        ("HEADERS_JSON", '["private-secret"]', "JSON对象"),
        ("EXTRA_JSON", "private-secret", "合法JSON对象"),
        ("INCLUDE_USER_UID", "1", "布尔值"),
    ],
)
def test_invalid_provider_metadata_has_safe_error(field, value, reason):
    """异常只报告边界，绝不回显字段值或JSON解析正文。"""
    values = valid_inputs()
    values["HEALTH_SAFE_PLANNER_LIVE_" + field] = value
    with pytest.raises(ValueError, match=reason) as raised:
        load_live_inputs(values)
    assert value not in str(raised.value)
