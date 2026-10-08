"""仅重放显式选餐反馈协议，独立检查字段与写入版本。"""

import json
import re
from http.server import ThreadingHTTPServer

from health_diet_analysis_replay_server import AnalystReplayHandler

MODEL = "deterministic-meal-feedback-20261007"


def feedback_delta(authorization, body):
    """固定两工具，原文及版本由实际工具结果证明。"""
    if authorization != "Bearer synthetic-feedback-key" or body.get("model") != MODEL or body.get("stream") is not True:
        raise ValueError("synthetic_model_required")
    names = {tool.get("function", {}).get("name") for tool in body.get("tools", [])}
    if names != {"get_selected_meal_feedback", "record_selected_meal_feedback"}:
        raise ValueError("fixed_feedback_tools_required")
    messages = body["messages"]
    if not any(m.get("role") == "system" and "slug: family-diet-analyst" in str(m.get("content")) for m in messages):
        raise ValueError("fixed_skill_required")
    quote = next(m["content"] for m in reversed(messages) if m.get("role") == "user")
    match = re.search(
        r"合成反馈回放:([0-9a-f]{32}):(valid|repeat|forged|stale|fake_saved|questions|saved_questions)", quote
    )
    if not match:
        raise ValueError("synthetic_input_required")
    token, mode = match.groups()
    if mode == "fake_saved":
        return {"role": "assistant", "content": '{"feedback_saved":true}'}, True
    if mode == "questions":
        return {"role": "assistant", "content": '{"questions":["请明确是否记录这餐反馈？"]}'}, True
    selected, saved, repeated = f"selected-{token}", f"saved-{token}", f"repeat-{token}"
    outputs = {
        m.get("tool_call_id"): json.loads(m["content"])
        for m in messages
        if m.get("role") == "tool" and m.get("tool_call_id") in {selected, saved, repeated}
    }
    if saved in outputs:
        result = outputs[saved]
        if result["feedback"]["version"] != outputs[selected]["feedback_version"] + 1 or result["feedback"]["details"][
            "tags"
        ] != ["too_salty"]:
            raise ValueError("independent_feedback_oracle_failed")
        if result["feedback"]["details"]["consumption"] != "half" or result["nutrition_recalculated"] is not False:
            raise ValueError("feedback_meaning_failed")
        if mode == "saved_questions":
            return {"role": "assistant", "content": '{"questions":["还有其他反馈吗？"]}'}, True
        if mode != "repeat" or repeated in outputs:
            return {"role": "assistant", "content": '{"feedback_saved":true}'}, True
        name, call_id = "record_selected_meal_feedback", repeated
        args = {"quote": quote, "version": outputs[selected]["feedback_version"]}
    elif selected in outputs:
        name, call_id = "record_selected_meal_feedback", saved
        args = {"quote": quote + ("伪造" if mode == "forged" else ""), "version": outputs[selected]["feedback_version"]}
        if mode == "stale":
            args["version"] += 1
    else:
        name, call_id, args = "get_selected_meal_feedback", selected, {}
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "index": 0,
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ],
    }, False


class FeedbackReplayHandler(AnalystReplayHandler):
    """沿用本地SSE帧写入，不代理外网或存储原文。"""

    def do_POST(self):
        """父handler的全局函数与模型由独立合成协议替换。"""
        import health_diet_analysis_replay_server as server

        server.replay_delta, server.MODEL = feedback_delta, MODEL
        super().do_POST()


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8770), FeedbackReplayHandler).serve_forever()
