"""审核范围回放的两阶段协议不得削弱原有独立来源oracle。"""

import json
from copy import deepcopy

import pytest

from test.support.health_reviewed_scope_replay_server import AUTHORIZATION, MODEL, STATES, TOOLS, replay_response

TOKEN = "b" * 32
IDENTITY = "11111111-1111-4111-8111-111111111111"


def request(role):
    """只登记合成gold，工具schema仍由测试独立手写。"""
    expected = {
        "forbidden": ["FORBIDDEN_SCOPE"],
        "evidence_ids": [IDENTITY],
        "contents": {IDENTITY: "synthetic-reviewed-source"},
        "scopes": {IDENTITY: None},
    }
    STATES[TOKEN] = {"roles": {role: expected}, "foreign_citation": None}
    names = (
        TOOLS
        if role == "consultation"
        else {f"get_member_{role}_records", "query_reviewed_nutrition_knowledge", "query_family_nutrition_knowledge"}
    )
    return {
        "model": MODEL,
        "stream": True,
        "tool_choice": "required",
        "tools": [
            {
                "function": {
                    "name": name,
                    "parameters": {"properties": {"query": {"type": "string"}}, "required": ["query"]},
                }
            }
            for name in names | {"finalize_health_answer"}
        ],
        "messages": [{"role": "user", "content": f"REVIEWED_SCOPE_E2E:{TOKEN}:{role}:success"}],
    }


def attach_knowledge(body, role):
    """来源内容和采用ID必须与独立gold逐字匹配。"""
    body["messages"].append(
        {
            "role": "tool",
            "tool_call_id": f"scope-knowledge-{TOKEN}-{role}-success",
            "content": json.dumps(
                {
                    "citations": [
                        {
                            "evidence_id": IDENTITY,
                            "citation_id": IDENTITY,
                            "content": "synthetic-reviewed-source",
                            "scope": "general_education",
                        }
                    ]
                }
            ),
        }
    )


@pytest.mark.parametrize("role", ["consultation", "blood_glucose", "blood_lipids", "blood_pressure"])
def test_scope_replay_keeps_source_oracle_through_finalize_and_tool_free_answer(role):
    body = request(role)
    try:
        assert replay_response(AUTHORIZATION, body)[3] == "knowledge"
        attach_knowledge(body, role)
        *_, phase, delta = replay_response(AUTHORIZATION, body)
        assert phase == "finalize"
        body["messages"].append({"role": "tool", "tool_call_id": delta["tool_calls"][0]["id"], "content": "准备完成"})
        with pytest.raises(ValueError, match="explicit_finalization_required"):
            replay_response(AUTHORIZATION, body)
        body.pop("tools")
        body.pop("tool_choice")
        *_, phase, answer = replay_response(AUTHORIZATION, body)
        assert phase == "answer" and f"[证据:{IDENTITY}]" in answer["content"]
        forged = deepcopy(body)
        forged["messages"][1]["content"] = forged["messages"][1]["content"].replace(
            "synthetic-reviewed-source", "FORBIDDEN_SCOPE"
        )
        with pytest.raises(ValueError, match="forbidden_scope_reached_model"):
            replay_response(AUTHORIZATION, forged)
    finally:
        STATES.pop(TOKEN, None)


def test_scope_replay_still_refuses_a_broader_knowledge_tool_schema():
    body = request("consultation")
    try:
        function = next(
            row["function"] for row in body["tools"] if row["function"]["name"] == "query_reviewed_nutrition_knowledge"
        )
        function["parameters"]["properties"]["member_id"] = {"type": "string"}
        with pytest.raises(ValueError, match="query_only_tool_required"):
            replay_response(AUTHORIZATION, body)
    finally:
        STATES.pop(TOKEN, None)
