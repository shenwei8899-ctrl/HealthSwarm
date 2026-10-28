"""运行原样E2E oracle负控；不启动HTTP/PG，不替代真实槽位验收。"""

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).resolve().parents[2] / "e2e/test_health_validated_publication_e2e.py"
FUNCTIONS = {"assert_rewind_events", "assert_consent_read_denied", "assert_no_candidate"}
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
SCOPE = {"json": json}
exec(
    compile(
        ast.Module(
            body=[node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS],
            type_ignores=[],
        ),
        str(SOURCE),
        "exec",
    ),
    SCOPE,
)


def denied_events():
    """正式SSE建连授权失败的受控帧。"""
    return [("error", {"run_id": "run", "message": "运行任务不存在"}, None)]


def init(event_id):
    """区分真实init与注入legacy init的事件ID。"""
    return ("custom", {"payload": {"name": "yuxi.init"}}, event_id)


@pytest.mark.parametrize("mode", ["consent", "scope", "source"])
def test_fresh_denial_requires_one_error_without_replayed_init(mode):
    SCOPE["assert_rewind_events"](denied_events(), "run", mode, ["legacy"])


@pytest.mark.parametrize(
    "events",
    [
        [],
        [init("init"), *denied_events()],
        [("error", {"run_id": "other", "message": "运行任务不存在"}, None)],
        [("error", {"run_id": "run", "message": "运行任务不存在"}, "stale-id")],
        [("error", {"run_id": "run", "message": "provider or database error"}, None)],
        [
            ("custom", {"payload": {"name": "yuxi.health_answer_delta", "content": "PRIVATE_BODY"}}, "delta"),
            *denied_events(),
        ],
    ],
)
def test_consent_oracle_rejects_empty_wrong_error_or_any_custom(events):
    with pytest.raises(AssertionError):
        SCOPE["assert_rewind_events"](events, "run", "consent", ["legacy"])


def test_nonrevoked_replay_keeps_exact_one_real_init_and_distinct_ids():
    SCOPE["assert_rewind_events"]([init("actual"), init("legacy")], "run", "success", ["legacy"])


@pytest.mark.parametrize(
    "events", [[], [init("legacy")], [init("actual"), init("second")], [init("actual"), init("actual")]]
)
def test_nonrevoked_replay_cannot_skip_or_duplicate_real_init(events):
    with pytest.raises(AssertionError):
        SCOPE["assert_rewind_events"](events, "run", "success", ["legacy"])


def denied_response():
    """对应真实HealthRoute错误投影。"""
    return SimpleNamespace(
        status_code=403,
        headers={"cache-control": "no-store"},
        json=lambda: {
            "code": "consent_required",
            "detail": "请先同意当前咨询用途",
            "message": "请先同意当前咨询用途",
            "trace_id": "trace",
            "retryable": False,
        },
    )


def test_read_only_denial_requires_specific_consent_code_and_no_store():
    SCOPE["assert_consent_read_denied"](denied_response(), "token")


@pytest.mark.parametrize("mutation", ["success", "wrong_code", "cache", "private", "retryable"])
def test_read_only_denial_does_not_accept_empty_success_or_other_error(mutation):
    response = denied_response()
    payload = response.json()
    response.json = lambda: payload
    if mutation == "success":
        response.status_code = 200
    elif mutation == "wrong_code":
        payload["code"] = "not_found"
    elif mutation == "cache":
        response.headers = {"cache-control": "public"}
    elif mutation == "private":
        payload["private"] = "PRIVATE_CANDIDATE"
    else:
        payload["retryable"] = True
    with pytest.raises(AssertionError):
        SCOPE["assert_consent_read_denied"](response, "token")
