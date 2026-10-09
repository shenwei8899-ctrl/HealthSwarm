"""内存转交入口不能从输入包获得外呼权限或覆盖任意环境。"""

import io
import json
import sys

import pytest

from test.support import health_safe_planner_live_runner as runner

pytestmark = pytest.mark.unit


def model_packet():
    """仅提供无效但非回放的unit凭据，永不实际发起模型请求。"""
    return {
        "HEALTH_SAFE_PLANNER_LIVE_PROVIDER_ID": "alibaba-cn",
        "HEALTH_SAFE_PLANNER_LIVE_PROVIDER_TYPE": "openai",
        "HEALTH_SAFE_PLANNER_LIVE_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "HEALTH_SAFE_PLANNER_LIVE_API_KEY": "unit-secret-never-used",
        "HEALTH_SAFE_PLANNER_LIVE_MODEL_ID": "qwen-plus-2025-07-28",
        "HEALTH_SAFE_PLANNER_LIVE_HEADERS_JSON": "{}",
        "HEALTH_SAFE_PLANNER_LIVE_EXTRA_JSON": "{}",
        "HEALTH_SAFE_PLANNER_LIVE_MODEL_JSON": "{}",
        "HEALTH_SAFE_PLANNER_LIVE_INCLUDE_USER_UID": "false",
    }


def test_wire_needs_caller_opt_in_even_with_complete_provider(monkeypatch):
    """stdin不能代替调用者明确许可外呼。"""
    monkeypatch.delenv("RUN_HEALTH_SAFE_PLANNER_REAL_MODEL", raising=False)
    with pytest.raises(ValueError, match="未显式"):
        runner.read_environment_packet(json.dumps(model_packet()))


@pytest.mark.parametrize(
    "invalid",
    [
        "broken-json",
        "[]",
        "{}",
        '{"RUN_HEALTH_SAFE_PLANNER_REAL_MODEL":"1"}',
        '{"HEALTH_SAFE_PLANNER_LIVE_API_KEY":123}',
    ],
)
def test_wire_rejects_unknown_missing_or_non_string_fields(monkeypatch, invalid):
    """只有完整的九字段模型包可以进入进程环境。"""
    monkeypatch.setenv("RUN_HEALTH_SAFE_PLANNER_REAL_MODEL", "1")
    with pytest.raises(ValueError):
        runner.read_environment_packet(invalid)


def test_run_is_fixed_to_probe_and_preserves_pytest_failure(monkeypatch, capsys):
    """验收失败原样返回，凭据只在进程环境中，不输出到控制台。"""
    monkeypatch.setenv("RUN_HEALTH_SAFE_PLANNER_REAL_MODEL", "1")
    monkeypatch.setenv("HEALTH_CONSULTATION_E2E_ISOLATED", "true")
    monkeypatch.setattr(sys, "argv", ["live-runner", "run"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(model_packet())))
    seen = []
    monkeypatch.setattr(pytest, "main", lambda args: seen.append(args) or 7)
    for name, value in model_packet().items():
        monkeypatch.setenv(name, value)
    assert runner.main() == 7
    assert seen and seen[0][0] == "test/e2e/test_health_safe_planner_live_e2e.py"
    assert "--show-capture=no" in seen[0] and "--tb=short" in seen[0] and "--showlocals" not in seen[0]
    captured = capsys.readouterr()
    assert "unit-secret" not in captured.out + captured.err


@pytest.mark.parametrize("invalid", ["no_isolation", "missing_key", "local_url", "floating_model"])
def test_run_rejects_before_pytest_for_unapproved_environment(monkeypatch, capsys, invalid):
    """错误环境不能以四个skip的成功退出冒充已完成真实模型验收。"""
    monkeypatch.setenv("RUN_HEALTH_SAFE_PLANNER_REAL_MODEL", "1")
    monkeypatch.setenv("HEALTH_CONSULTATION_E2E_ISOLATED", "true" if invalid != "no_isolation" else "false")
    packet = model_packet()
    if invalid == "missing_key":
        packet["HEALTH_SAFE_PLANNER_LIVE_API_KEY"] = ""
    elif invalid == "local_url":
        packet["HEALTH_SAFE_PLANNER_LIVE_BASE_URL"] = "http://api:8766/v1"
    elif invalid == "floating_model":
        packet["HEALTH_SAFE_PLANNER_LIVE_MODEL_ID"] = "qwen-latest"
    for name, value in packet.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(sys, "argv", ["live-runner", "run"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(packet)))
    called = []
    monkeypatch.setattr(pytest, "main", lambda args: called.append(args) or 0)
    assert runner.main() == 2 and not called
    assert "unit-secret" not in capsys.readouterr().err
