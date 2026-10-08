"""独立合成质量协议：固定资源、手算营养及服务器检查收据。"""

import json
import re
from http.server import ThreadingHTTPServer
from uuid import uuid4

from health_diet_analysis_replay_server import AnalystReplayHandler

MODEL = "deterministic-quality-20261007"


def quality_delta(authorization, body):
    """只接受隔离合成输入，合法结果也不提交专业批准。"""
    if authorization != "Bearer synthetic-quality-key" or body.get("model") != MODEL or body.get("stream") is not True:
        raise ValueError("synthetic_model_required")
    names = {tool.get("function", {}).get("name") for tool in body.get("tools", [])}
    if names != {"get_quality_review_context", "check_selected_plan_quality"}:
        raise ValueError("fixed_quality_tools_required")
    messages = body["messages"]
    if not any(m.get("role") == "system" and "slug: family-quality-review" in str(m.get("content")) for m in messages):
        raise ValueError("fixed_quality_skill_required")
    query = next(m["content"] for m in reversed(messages) if m.get("role") == "user")
    match = re.fullmatch(
        r"QUALITY_E2E:([0-9a-f]{32}):(valid|questions|no_receipt|fake_approval|cross_run)(:personal)?", query
    )
    if not match:
        raise ValueError("synthetic_input_required")
    token, mode, personal = match.groups()
    if mode == "questions":
        return {"role": "assistant", "content": json.dumps({"questions": ["请补充已确认的过敏资料。"]})}, True
    if mode == "no_receipt":
        return {"role": "assistant", "content": json.dumps({"check_id": str(uuid4())})}, True
    if mode == "fake_approval":
        return {"role": "assistant", "content": '{"approved":true}'}, True
    if mode == "cross_run":
        old = next(
            json.loads(m["content"])
            for m in messages
            if m.get("role") == "tool" and json.loads(m["content"]).get("result_type") == "quality_check"
        )
        return {"role": "assistant", "content": json.dumps({"check_id": old["check_id"]})}, True
    context_id, check_id = f"context-{token}", f"check-{token}"
    outputs = {
        m.get("tool_call_id"): json.loads(m["content"])
        for m in messages
        if m.get("role") == "tool" and m.get("tool_call_id") in {context_id, check_id}
    }
    if check_id in outputs:
        result = outputs[check_id]
        if result["nutrition"]["totals"] != {
            "energy_kcal": "300.00",
            "protein_g": "30.00",
            "fat_g": "6.00",
            "carbohydrate_g": "60.00",
            "sodium_mg": "150.00",
        } or result["safety_check"]["status"] != ("conflict" if personal else "passed"):
            raise ValueError("independent_quality_oracle_failed")
        if personal:
            check = result["safety_check"]
            target = check.get("personal_targets", {})
            if (
                check.get("checks_version") != "quality-rules-v2-personal"
                or target.get("status") != "ready"
                or target.get("energy_kcal") != "330"
                or target.get("bounds", {}).get("energy_kcal") != {"minimum": "330", "maximum": "330"}
                or check.get("missing") != []
                or check.get("conflicts")
                != [
                    {
                        "path": "nutrition.energy_kcal",
                        "code": "approved_nutrient_range",
                        "reason": "计划量超出当前批准范围",
                    }
                ]
            ):
                raise ValueError("independent_personal_target_oracle_failed")
        if result["professional_review"] != "not_a_professional_decision":
            raise ValueError("model_professional_decision_forbidden")
        return {"role": "assistant", "content": json.dumps({"check_id": result["check_id"]})}, True
    if context_id in outputs:
        name, call_id = "check_selected_plan_quality", check_id
    else:
        name, call_id = "get_quality_review_context", context_id
    return {
        "role": "assistant",
        "tool_calls": [{"index": 0, "id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}],
    }, False


class QualityReplayHandler(AnalystReplayHandler):
    """复用本地流式协议帧，不代理外网，不记录正文。"""

    def do_POST(self):
        """此独立进程只提供质量回放。"""
        import health_diet_analysis_replay_server as server

        server.replay_delta, server.MODEL = quality_delta, MODEL
        super().do_POST()


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8771), QualityReplayHandler).serve_forever()
