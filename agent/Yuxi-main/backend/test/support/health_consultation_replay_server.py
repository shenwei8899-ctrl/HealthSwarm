"""只接受合成健康咨询的本地协议重放，不代理任何供应商。"""

import json
import re
import time
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Lock
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

MODEL = "deterministic-health-20261004"
SAFE_PLANNER_MODEL = "deterministic-safe-meal-plan-20261009"
SAFE_PLANNER_TOOLS = {
    "get_safe_plan_context",
    "preview_safe_plan_swap",
    "preview_safe_plan_regeneration",
}
TOOLS = {
    "get_confirmed_profile",
    "get_confirmed_diet",
    "get_complete_health_profile",
    "get_member_weight_records",
    "get_member_blood_pressure_records",
    "get_member_blood_glucose_records",
    "get_member_blood_lipids_records",
    "query_reviewed_nutrition_knowledge",
    "get_member_memories",
    "remember_member_fact",
    "get_meal_feedback",
}
STATES = {}
LOCK = Lock()


def safe_planner_replay_delta(authorization, body):
    """单成员协议独立核对固定工具、300/310/305手算结果及本轮收据。"""
    if (
        authorization != "Bearer synthetic-safe-planner-key"
        or body.get("model") != SAFE_PLANNER_MODEL
        or body.get("stream") is not True
    ):
        raise ValueError("synthetic_safe_model_required")
    names = [t.get("function", {}).get("name") for t in body.get("tools", [])]
    if len(names) != 3 or set(names) != SAFE_PLANNER_TOOLS:
        raise ValueError("fixed_safe_tools_required")
    messages = body.get("messages", [])
    if not any(m.get("role") == "system" and "slug: family-meal-planner" in str(m.get("content")) for m in messages):
        raise ValueError("fixed_safe_skill_required")
    user = next((m for m in reversed(messages) if m.get("role") == "user"), {})
    match = re.fullmatch(
        r"SAFE_PLANNER_E2E:([0-9a-f]{32}):(swap|swap_second|regeneration|questions|invalid|forged|foreign|safe_gate)(?::([0-9a-f-]{36}))?",
        str(user.get("content", "")),
    )
    if match is None or (match[2] == "foreign") != bool(match[3]):
        raise ValueError("synthetic_safe_input_required")
    token, mode, foreign = match.groups()
    context_id, preview_id = f"safe-context-{token}", f"safe-preview-{token}"
    if mode == "swap_second" and not any(
        message.get("role") == "tool"
        and str(message.get("tool_call_id", "")).startswith("safe-preview-")
        and message.get("tool_call_id") != preview_id
        for message in messages
    ):
        raise ValueError("prior_safe_checkpoint_required")
    outputs = {
        m.get("tool_call_id"): json.loads(m["content"])
        for m in messages
        if m.get("role") == "tool" and m.get("tool_call_id") in {context_id, preview_id}
    }
    if preview_id in outputs:
        receipt = outputs[preview_id]
        if (
            set(receipt) != {"preview_id", "scope", "member_id", "operation", "result"}
            or receipt["scope"] != "single_member_saved_plan"
            or not re.fullmatch(r"[0-9a-f-]{36}", str(receipt["preview_id"]))
            or receipt["operation"] != ("regeneration" if mode == "regeneration" else "swap")
        ):
            raise ValueError("single_member_receipt_required")
        result = receipt["result"]
        if result.get("status") != "ready":
            raise ValueError("safe_preview_ready_required")
        if mode == "regeneration":
            if result["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] != "305.00":
                raise ValueError("independent_305kcal_required")
        else:
            candidates = result["candidates"]
            if len(candidates) != 1 or candidates[0]["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] != "310.00":
                raise ValueError("independent_310kcal_required")
        answer = {"preview_id": foreign if mode == "foreign" else receipt["preview_id"]}
        if mode == "invalid":
            answer["professional_review"] = "approved"
        elif mode == "forged":
            answer["preview_id"] = "00000000-0000-0000-0000-000000000000"
        return token, mode, {"role": "assistant", "content": json.dumps(answer)}, True
    if context_id in outputs:
        current = outputs[context_id]
        if (
            current.get("scope") != "single_member_saved_plan"
            or current["plan_snapshot"]["nutrition"]["totals"]["energy_kcal"] != "300.00"
            or not re.fullmatch(r"[0-9a-f-]{36}", str(current["member_id"]))
            or current["professional_review"] != "not_a_professional_decision"
        ):
            raise ValueError("independent_original_300kcal_required")
        if mode == "questions":
            return (
                token,
                mode,
                {"role": "assistant", "content": json.dumps({"questions": ["合成：要调整哪一餐？"]})},
                True,
            )
        name, args, call_id = (
            ("preview_safe_plan_regeneration", {}, preview_id)
            if mode == "regeneration"
            else ("preview_safe_plan_swap", {"meal_type": "lunch", "dish_index": 0}, preview_id)
        )
    else:
        name, args, call_id = "get_safe_plan_context", {}, context_id
    return (
        token,
        mode,
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "index": 0,
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
            ],
        },
        False,
    )


def validate_request(authorization, body):
    """重放的 oracle 独立核对固定工具、合成输入及必要业务投影。"""
    if authorization != "Bearer synthetic-health-replay-key" or body.get("model") != MODEL:
        raise ValueError("invalid_authorization_or_model")
    if body.get("stream") is not True:
        raise ValueError("stream_required")
    names = {tool.get("function", {}).get("name") for tool in body.get("tools", [])}
    if names != TOOLS:
        raise ValueError("unexpected_tool_set")
    messages = body.get("messages", [])
    system = "\n".join(
        item["content"] for item in messages if item.get("role") == "system" and isinstance(item.get("content"), str)
    )
    if not all(marker in system for marker in ("slug: family-nutritionist", "## 咨询流程", "## 日常反馈与记忆边界")):
        raise ValueError("fixed_nutritionist_skill_required")
    users = [item for item in messages if item.get("role") == "user"]
    marker = (
        re.fullmatch(
            r"HEALTH_CONSULTATION_E2E:([0-9a-f]{32}):(one|two|evidence|invalid_evidence|lexical|lexical_rebuilt|memory|read_memory|derived_memory|update_memory|empty_memory|feedback|derived_feedback|edited_feedback|empty_feedback|feedback_gate|mixed_feedback|neutral|profile|profile_updated|derived_profile|profile_gate|derived_profile_gate|weight_read|weight_updated|weight_missing|weight_gate|weight_derived_gate|bp_read|bp_updated|bp_missing|bp_not_linked|bp_gate|bp_derived_gate|glucose_read|glucose_updated|glucose_missing|glucose_not_linked|glucose_gate|glucose_derived_gate|lipids_read|lipids_updated|lipids_missing|lipids_not_linked|lipids_gate|lipids_derived_gate)(?:\n我以后(?:不吃|会吃)香菜)?",
            str(users[-1]["content"]),
        )
        if users
        else None
    )
    if marker is None:
        raise ValueError("synthetic_input_required")
    token, step = marker.groups()
    call_id = f"health-read-{token}-{step}"
    results = [item for item in messages if item.get("role") == "tool" and item.get("tool_call_id") == call_id]
    record_ids = []
    if step in {
        "lipids_read",
        "lipids_updated",
        "lipids_missing",
        "lipids_not_linked",
        "lipids_gate",
        "lipids_derived_gate",
    }:
        if step == "lipids_derived_gate":
            if not any(
                item.get("role") == "assistant"
                and "合成本人血脂四项tc4.8、tg1.2、hdl1.3、ldl2.6 mmol/L" in str(item.get("content"))
                for item in messages
            ):
                raise ValueError("prior_blood_lipids_answer_required")
            return token, step, call_id, True, []
        if not results:
            return token, step, call_id, False, []
        payload = json.loads(results[-1]["content"])
        if set(payload) != {
            "status",
            "code",
            "owner",
            "member_id",
            "source_member_id",
            "period",
            "limit",
            "records",
            "truncated",
            "full_health_profile_available",
            "nutrition_safety_ready",
            "source_hash",
        }:
            raise ValueError("minimal_blood_lipids_projection_required")
        period = payload["period"]
        if set(period) != {"start_date", "end_date", "timezone"} or period["timezone"] != "Asia/Shanghai":
            raise ValueError("blood_lipids_period_required")
        start, end = date.fromisoformat(period["start_date"]), date.fromisoformat(period["end_date"])
        if end - start != timedelta(days=29) or type(payload["limit"]) is not int or payload["limit"] != 20:
            raise ValueError("blood_lipids_period_required")
        if (
            payload["owner"] != "健康档案服务"
            or payload["truncated"] is not False
            or payload["full_health_profile_available"] is not False
            or payload["nutrition_safety_ready"] is not False
            or not re.fullmatch(r"[0-9a-f-]{36}", str(payload["member_id"]))
            or not re.fullmatch(r"[0-9a-f]{64}", str(payload["source_hash"]))
        ):
            raise ValueError("independent_blood_lipids_source_required")
        if step == "lipids_not_linked":
            if (
                payload["status"] != "not_ready"
                or payload["code"] != "blood_lipids_not_linked"
                or payload["source_member_id"] is not None
                or payload["records"] != []
            ):
                raise ValueError("unlinked_blood_lipids_required")
            return token, step, call_id, True, []
        if not re.fullmatch(r"[0-9a-f-]{36}", str(payload["source_member_id"])):
            raise ValueError("independent_blood_lipids_source_required")
        if step == "lipids_missing":
            if (
                payload["status"] != "not_ready"
                or payload["code"] != "blood_lipids_missing"
                or payload["records"] != []
            ):
                raise ValueError("missing_blood_lipids_required")
            return token, step, call_id, True, []
        if (
            payload["status"] != "ready"
            or payload["code"] != "self_blood_lipids_records"
            or len(payload["records"]) != 1
        ):
            raise ValueError("synthetic_blood_lipids_record_required")
        record = payload["records"][0]
        if set(record) != {"record_id", "tc", "tg", "hdl", "ldl", "unit", "measured_at", "source", "version"}:
            raise ValueError("minimal_blood_lipids_record_required")
        ldl, version = (2.7, 2) if step == "lipids_updated" else (2.6, 1)
        if (
            any(type(record[field]) not in {int, float} for field in ("tc", "tg", "hdl", "ldl"))
            or record["tc"] != 4.8
            or record["tg"] != 1.2
            or record["hdl"] != 1.3
            or record["ldl"] != ldl
            or type(record["version"]) is not int
            or record["version"] != version
            or record["unit"] != "mmol/L"
            or type(record["source"]) is not str
            or not record["source"]
            or not re.fullmatch(r"[0-9a-f-]{36}", str(record["record_id"]))
        ):
            raise ValueError("synthetic_blood_lipids_pair_required")
        measured = str(record["measured_at"])
        when = datetime.fromisoformat(measured)
        if (
            not measured.endswith("Z")
            or when.utcoffset() != timedelta(0)
            or not start <= when.astimezone(ZoneInfo("Asia/Shanghai")).date() <= end
        ):
            raise ValueError("blood_lipids_utc_measurement_required")
        return token, step, call_id, True, [record["record_id"]]
    if step in {
        "glucose_read",
        "glucose_updated",
        "glucose_missing",
        "glucose_not_linked",
        "glucose_gate",
        "glucose_derived_gate",
    }:
        if step == "glucose_derived_gate":
            if not any(
                item.get("role") == "assistant"
                and "合成本人血糖5.5 mmol/L，测量条件fasting" in str(item.get("content"))
                for item in messages
            ):
                raise ValueError("prior_blood_glucose_answer_required")
            return token, step, call_id, True, []
        if not results:
            return token, step, call_id, False, []
        payload = json.loads(results[-1]["content"])
        if set(payload) != {
            "status",
            "code",
            "owner",
            "member_id",
            "source_member_id",
            "period",
            "limit",
            "records",
            "truncated",
            "full_health_profile_available",
            "nutrition_safety_ready",
            "source_hash",
        }:
            raise ValueError("minimal_blood_glucose_projection_required")
        period = payload["period"]
        if set(period) != {"start_date", "end_date", "timezone"} or period["timezone"] != "Asia/Shanghai":
            raise ValueError("blood_glucose_period_required")
        start, end = date.fromisoformat(period["start_date"]), date.fromisoformat(period["end_date"])
        if end - start != timedelta(days=29) or type(payload["limit"]) is not int or payload["limit"] != 20:
            raise ValueError("blood_glucose_period_required")
        if (
            payload["owner"] != "健康档案服务"
            or payload["truncated"] is not False
            or payload["full_health_profile_available"] is not False
            or payload["nutrition_safety_ready"] is not False
            or not re.fullmatch(r"[0-9a-f-]{36}", str(payload["member_id"]))
            or not re.fullmatch(r"[0-9a-f]{64}", str(payload["source_hash"]))
        ):
            raise ValueError("independent_blood_glucose_source_required")
        if step == "glucose_not_linked":
            if (
                payload["status"] != "not_ready"
                or payload["code"] != "blood_glucose_not_linked"
                or payload["source_member_id"] is not None
                or payload["records"] != []
            ):
                raise ValueError("unlinked_blood_glucose_required")
            return token, step, call_id, True, []
        if not re.fullmatch(r"[0-9a-f-]{36}", str(payload["source_member_id"])):
            raise ValueError("independent_blood_glucose_source_required")
        if step == "glucose_missing":
            if (
                payload["status"] != "not_ready"
                or payload["code"] != "blood_glucose_missing"
                or payload["records"] != []
            ):
                raise ValueError("missing_blood_glucose_required")
            return token, step, call_id, True, []
        if (
            payload["status"] != "ready"
            or payload["code"] != "self_blood_glucose_records"
            or len(payload["records"]) != 1
        ):
            raise ValueError("synthetic_blood_glucose_record_required")
        record = payload["records"][0]
        if set(record) != {"record_id", "glucose", "condition", "unit", "measured_at", "source", "version"}:
            raise ValueError("minimal_blood_glucose_record_required")
        condition, version = ("after_meal_2h", 2) if step == "glucose_updated" else ("fasting", 1)
        if (
            type(record["glucose"]) not in {int, float}
            or record["glucose"] != 5.5
            or record["condition"] != condition
            or type(record["version"]) is not int
            or record["version"] != version
            or record["unit"] != "mmol/L"
            or type(record["source"]) is not str
            or not record["source"]
            or not re.fullmatch(r"[0-9a-f-]{36}", str(record["record_id"]))
        ):
            raise ValueError("synthetic_blood_glucose_pair_required")
        measured = str(record["measured_at"])
        when = datetime.fromisoformat(measured)
        if (
            not measured.endswith("Z")
            or when.utcoffset() != timedelta(0)
            or not start <= when.astimezone(ZoneInfo("Asia/Shanghai")).date() <= end
        ):
            raise ValueError("blood_glucose_utc_measurement_required")
        return token, step, call_id, True, [record["record_id"]]
    if step in {"bp_read", "bp_updated", "bp_missing", "bp_not_linked", "bp_gate", "bp_derived_gate"}:
        if step == "bp_derived_gate":
            if not any(
                item.get("role") == "assistant" and "合成本人血压120/80 mmHg" in str(item.get("content"))
                for item in messages
            ):
                raise ValueError("prior_blood_pressure_answer_required")
            return token, step, call_id, True, []
        if not results:
            return token, step, call_id, False, []
        payload = json.loads(results[-1]["content"])
        if set(payload) != {
            "status",
            "code",
            "owner",
            "member_id",
            "source_member_id",
            "period",
            "limit",
            "records",
            "truncated",
            "full_health_profile_available",
            "nutrition_safety_ready",
            "source_hash",
        }:
            raise ValueError("minimal_blood_pressure_projection_required")
        period = payload["period"]
        if set(period) != {"start_date", "end_date", "timezone"} or period["timezone"] != "Asia/Shanghai":
            raise ValueError("blood_pressure_period_required")
        start, end = date.fromisoformat(period["start_date"]), date.fromisoformat(period["end_date"])
        if end - start != timedelta(days=29) or type(payload["limit"]) is not int or payload["limit"] != 20:
            raise ValueError("blood_pressure_period_required")
        if (
            payload["owner"] != "健康档案服务"
            or payload["truncated"] is not False
            or payload["full_health_profile_available"] is not False
            or payload["nutrition_safety_ready"] is not False
            or not re.fullmatch(r"[0-9a-f-]{36}", str(payload["member_id"]))
            or not re.fullmatch(r"[0-9a-f]{64}", str(payload["source_hash"]))
        ):
            raise ValueError("independent_blood_pressure_source_required")
        if step == "bp_not_linked":
            if (
                payload["status"] != "not_ready"
                or payload["code"] != "blood_pressure_not_linked"
                or payload["source_member_id"] is not None
                or payload["records"] != []
            ):
                raise ValueError("unlinked_blood_pressure_required")
            return token, step, call_id, True, []
        if not re.fullmatch(r"[0-9a-f-]{36}", str(payload["source_member_id"])):
            raise ValueError("independent_blood_pressure_source_required")
        if step == "bp_missing":
            if (
                payload["status"] != "not_ready"
                or payload["code"] != "blood_pressure_missing"
                or payload["records"] != []
            ):
                raise ValueError("missing_blood_pressure_required")
            return token, step, call_id, True, []
        if (
            payload["status"] != "ready"
            or payload["code"] != "self_blood_pressure_records"
            or len(payload["records"]) != 1
        ):
            raise ValueError("synthetic_blood_pressure_record_required")
        record = payload["records"][0]
        if set(record) != {"record_id", "systolic", "diastolic", "unit", "measured_at", "source", "version"}:
            raise ValueError("minimal_blood_pressure_record_required")
        systolic, diastolic, version = (122, 82, 2) if step == "bp_updated" else (120, 80, 1)
        if (
            type(record["systolic"]) not in {int, float}
            or record["systolic"] != systolic
            or type(record["diastolic"]) not in {int, float}
            or record["diastolic"] != diastolic
            or type(record["version"]) is not int
            or record["version"] != version
            or record["unit"] != "mmHg"
            or type(record["source"]) is not str
            or not record["source"]
            or not re.fullmatch(r"[0-9a-f-]{36}", str(record["record_id"]))
        ):
            raise ValueError("synthetic_blood_pressure_pair_required")
        measured = str(record["measured_at"])
        when = datetime.fromisoformat(measured)
        if (
            not measured.endswith("Z")
            or when.utcoffset() != timedelta(0)
            or not start <= when.astimezone(ZoneInfo("Asia/Shanghai")).date() <= end
        ):
            raise ValueError("blood_pressure_utc_measurement_required")
        return token, step, call_id, True, [record["record_id"]]
    if step in {"weight_read", "weight_updated", "weight_missing", "weight_gate", "weight_derived_gate"}:
        if step == "weight_derived_gate":
            if not any(
                item.get("role") == "assistant" and "合成本人体重60 kg" in str(item.get("content")) for item in messages
            ):
                raise ValueError("prior_weight_answer_required")
            return token, step, call_id, True, []
        if not results:
            return token, step, call_id, False, []
        payload = json.loads(results[-1]["content"])
        required = {
            "status",
            "code",
            "owner",
            "member_id",
            "source_member_id",
            "period",
            "limit",
            "records",
            "truncated",
            "full_health_profile_available",
            "nutrition_safety_ready",
            "source_hash",
        }
        if set(payload) != required:
            raise ValueError("minimal_weight_projection_required")
        period = payload["period"]
        if set(period) != {"start_date", "end_date", "timezone"} or period["timezone"] != "Asia/Shanghai":
            raise ValueError("weight_period_required")
        start, end = date.fromisoformat(period["start_date"]), date.fromisoformat(period["end_date"])
        if end - start != timedelta(days=29) or payload["limit"] != 20 or payload["truncated"] is not False:
            raise ValueError("weight_period_required")
        if (
            payload["owner"] != "健康档案服务"
            or payload["full_health_profile_available"] is not False
            or payload["nutrition_safety_ready"] is not False
            or not re.fullmatch(r"[0-9a-f-]{36}", str(payload["member_id"]))
            or not re.fullmatch(r"[0-9a-f-]{36}", str(payload["source_member_id"]))
            or not re.fullmatch(r"[0-9a-f]{64}", str(payload["source_hash"]))
        ):
            raise ValueError("independent_weight_source_required")
        records = payload["records"]
        if step == "weight_missing":
            if payload["status"] != "not_ready" or payload["code"] != "weight_missing" or records != []:
                raise ValueError("missing_weight_required")
            return token, step, call_id, True, []
        if payload["status"] != "ready" or payload["code"] != "self_weight_records" or len(records) != 1:
            raise ValueError("synthetic_weight_record_required")
        record = records[0]
        if set(record) != {"record_id", "value", "unit", "measured_at", "source", "version"}:
            raise ValueError("minimal_weight_record_required")
        value, version = (61, 2) if step == "weight_updated" else (60, 1)
        if (
            type(record["value"]) not in {int, float}
            or record["value"] != value
            or type(record["version"]) is not int
            or record["version"] != version
            or record["unit"] != "kg"
            or record["source"] not in {"synthetic-weight-scale", "device"}
            or not re.fullmatch(r"[0-9a-f-]{36}", str(record["record_id"]))
        ):
            raise ValueError("synthetic_weight_value_required")
        measured = str(record["measured_at"])
        when = datetime.fromisoformat(measured)
        if (
            not measured.endswith("Z")
            or when.utcoffset() != timedelta(0)
            or not start <= when.astimezone(ZoneInfo("Asia/Shanghai")).date() <= end
        ):
            raise ValueError("weight_utc_measurement_required")
        return token, step, call_id, True, [record["record_id"]]
    if step in {"profile", "profile_updated", "derived_profile", "profile_gate", "derived_profile_gate"}:
        if step in {"derived_profile", "derived_profile_gate"}:
            if not any(
                item.get("role") == "assistant" and "合成本人身高171" in str(item.get("content")) for item in messages
            ):
                raise ValueError("prior_profile_answer_required")
            return token, step, call_id, True, []
        if results:
            profile = json.loads(results[-1]["content"])
            expected_height, expected_version = (172, 3) if step == "profile_updated" else (171, 2)
            if (
                profile.get("status") != "ready"
                or profile.get("confirmed_version") != expected_version
                or profile.get("profile", {}).get("height_cm") != expected_height
                or profile.get("nutrition_safety_ready") is not False
                or profile.get("full_health_profile_available") is not False
                or not re.fullmatch(r"[0-9a-f]{64}", str(profile.get("source_hash", "")))
            ):
                raise ValueError("confirmed_self_profile_required")
            return token, step, call_id, True, [profile["source"]["source_member_id"]]
        return token, step, call_id, False, []
    if step == "neutral":
        if any(
            phrase in str(item.get("content"))
            for item in messages
            if item.get("role") != "system"
            for phrase in ("合成单餐偏咸", "我以后不吃香菜")
        ):
            raise ValueError("mixed_invalid_history_leaked")
        return token, step, call_id, True, []
    if step == "mixed_feedback":
        if results:
            feedback = json.loads(results[-1]["content"]).get("feedback", [])
            memories = [
                item
                for item in messages
                if item.get("role") == "tool" and item.get("tool_call_id") == call_id + "-memory"
            ]
            if len(feedback) != 1 or feedback[0].get("details", {}).get("comment") != "合成单餐偏咸":
                raise ValueError("mixed_feedback_required")
            if (
                not memories
                or json.loads(memories[-1]["content"]).get("memories", [{}])[0].get("content") != "我以后不吃香菜"
            ):
                raise ValueError("mixed_memory_required")
            return token, step, call_id, True, [feedback[0]["feedback_id"]]
        return token, step, call_id, False, []
    if step in {"feedback", "derived_feedback", "edited_feedback", "empty_feedback", "feedback_gate"}:
        if step in {"edited_feedback", "empty_feedback"} and any(
            phrase in str(item.get("content"))
            for item in messages
            if item.get("role") != "system"
            for phrase in (("合成单餐偏咸",) if step == "edited_feedback" else ("合成单餐偏咸", "合成餐后补充"))
        ):
            raise ValueError("invalid_feedback_history_leaked")
        if step == "derived_feedback":
            if not any(
                item.get("role") == "assistant" and "合成单餐偏咸" in str(item.get("content")) for item in messages
            ):
                raise ValueError("prior_feedback_answer_required")
            return token, step, call_id, True, []
        if results:
            result = json.loads(results[-1]["content"])
            rows = result.get("feedback", [])
            if step == "empty_feedback":
                if result != {"feedback": [], "truncated": False, "nutrition_recalculated": False}:
                    raise ValueError("revoked_feedback_recalled")
                return token, step, call_id, True, []
            expected = "合成餐后补充" if step == "edited_feedback" else "合成单餐偏咸"
            version = 2 if step == "edited_feedback" else 1
            if (
                len(rows) != 1
                or rows[0].get("details", {}).get("comment") != expected
                or rows[0].get("version") != version
            ):
                raise ValueError("active_meal_feedback_required")
            if (
                rows[0].get("scope") != "single_meal"
                or rows[0].get("source_type") != "user_self_report"
                or rows[0].get("formal_profile") is not False
            ):
                raise ValueError("feedback_self_report_scope_required")
            if not rows[0].get("diet_log_id") or rows[0].get("meal", {}).get("meal_type") != "lunch":
                raise ValueError("feedback_meal_reference_required")
            return token, step, call_id, True, [rows[0]["feedback_id"]]
        return token, step, call_id, False, []
    if step == "update_memory":
        if str(users[-1]["content"]) != f"HEALTH_CONSULTATION_E2E:{token}:update_memory\n我以后会吃香菜":
            raise ValueError("synthetic_memory_update_required")
        written = [
            item for item in messages if item.get("role") == "tool" and item.get("tool_call_id") == call_id + "-write"
        ]
        if written:
            result = json.loads(written[-1]["content"])
            if (
                result.get("content") != "我以后会吃香菜"
                or result.get("version") != 2
                or result.get("status") != "active"
            ):
                raise ValueError("updated_memory_required")
            return token, step, call_id + "-write", True, [result["memory_id"]]
        if results:
            result = json.loads(results[-1]["content"])
            if result.get("memories", [{}])[0].get("version") != 1:
                raise ValueError("original_memory_read_required")
            return token, step, call_id + "-write", False, []
        return token, step, call_id, False, []
    if step == "memory" and str(users[-1]["content"]) != f"HEALTH_CONSULTATION_E2E:{token}:memory\n我以后不吃香菜":
        raise ValueError("synthetic_memory_source_required")
    if step == "empty_memory":
        if any(
            any(phrase in str(item.get("content")) for phrase in ("我以后不吃香菜", "我以后会吃香菜"))
            for item in messages
            if item.get("role") != "system"
        ):
            raise ValueError("revoked_memory_history_leaked")
    if step == "derived_memory":
        if not any(
            item.get("role") == "assistant" and "合成读取：我以后不吃香菜" in str(item.get("content"))
            for item in messages
        ):
            raise ValueError("prior_memory_answer_required")
        return token, step, call_id, True, []
    if results and step == "read_memory":
        result = json.loads(results[-1]["content"])
        memories = result.get("memories", [])
        if len(memories) != 1 or memories[0].get("content") != "我以后不吃香菜" or memories[0].get("version") != 1:
            raise ValueError("active_memory_required")
        return token, step, call_id, True, [memories[0]["memory_id"]]
    if results and step == "memory":
        result = json.loads(results[-1]["content"])
        if (
            result.get("content") != "我以后不吃香菜"
            or result.get("source_type") != "user_self_report"
            or result.get("professional_review") != "not_reviewed"
            or result.get("status") != "active"
            or result.get("version") != 1
            or not re.fullmatch(r"[0-9a-f-]{36}", result.get("memory_id", ""))
        ):
            raise ValueError("unexpected_memory_receipt")
        return token, step, call_id, True, [result["memory_id"]]
    if results and step == "empty_memory":
        result = json.loads(results[-1]["content"])
        if result != {"memories": [], "truncated": False}:
            raise ValueError("revoked_memory_recalled")
        return token, step, call_id, True, []
    if results and step in {"lexical", "lexical_rebuilt"}:
        result = json.loads(results[-1]["content"])
        citations = result.get("citations", [])
        keys, version = ({"first", "second"}, "v1") if step == "lexical" else ({"first"}, "v2")
        if (
            result.get("status") != "ok"
            or len(citations) != len(keys)
            or result.get("query") != f"lexical{token} 膳食纤维 饮水"
        ):
            raise ValueError("independent_lexical_gold_required")
        seen = set()
        for citation in citations:
            key = str(citation.get("source_ref", "")).rsplit("/", 1)[-1]
            if (
                key not in keys
                or key in seen
                or citation.get("source_ref") != f"synthetic://lexical/{token}/{key}"
                or citation.get("title") != f"合成词法{key}"
                or citation.get("content") != f"lexical{token} 膳食纤维示例。另一段另提饮水，{key}。"
                or citation.get("source_version") != version
                or citation.get("scope") != "general_education"
                or not re.fullmatch(r"[0-9a-f-]{36}", str(citation.get("citation_id", "")))
                or not re.fullmatch(r"[0-9a-f-]{36}", str(citation.get("evidence_id", "")))
            ):
                raise ValueError("unexpected_lexical_source")
            seen.add(key)
        return token, step, call_id, True, [citation["citation_id"] for citation in citations]
    if results and step in {"evidence", "invalid_evidence"}:
        result = json.loads(results[-1]["content"])
        citations = result.get("citations", [])
        if result.get("status") != "ok" or len(citations) != 1:
            raise ValueError("reviewed_evidence_required")
        citation = citations[0]
        if (
            citation.get("title") != "合成营养证据"
            or citation.get("content") != "合成营养证据：此文本只用于协议验收。"
            or citation.get("source_version") != "synthetic-v1"
            or citation.get("scope") != "general_education"
            or not re.fullmatch(r"[0-9a-f-]{36}", citation.get("citation_id", ""))
        ):
            raise ValueError("unexpected_synthetic_evidence")
        return token, step, call_id, True, [citation["citation_id"]]
    if results:
        result = json.loads(results[-1]["content"])
        if (
            result.get("full_health_profile_available") is not False
            or result.get("personal_meal_plan_available") is not False
        ):
            raise ValueError("unverified_profile_capability")
        records = result.get("records", [])
        if len(records) != 1:
            raise ValueError("confirmed_record_required")
        record = records[0]
        if (
            record.get("name") != "测试指标"
            or record.get("value_numeric") != "6.8"
            or record.get("unit_raw") != "mmol/L"
        ):
            raise ValueError("unexpected_synthetic_record")
        if {"evidence", "value_raw", "object_key", "member_id", "actor_uid", "display_name"} & record.keys():
            raise ValueError("private_evidence_exported")
        record_ids = [record["record_id"]]
    return token, step, call_id, bool(results), record_ids


class HealthReplayHandler(BaseHTTPRequestHandler):
    """重放只开放健康检查、显式 gate 和 OpenAI 兼容响应。"""

    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        """测试直接观察重放入口并释放首轮；不访问业务数据库。"""
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.write_json(200, {"isolated": True})
            return
        if parsed.path not in {"/release", "/observations"}:
            self.write_json(404, {"error": "not_found"})
            return
        token = parse_qs(parsed.query).get("token", [""])[0]
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            self.write_json(422, {"error": "synthetic_token_required"})
            return
        with LOCK:
            state = STATES.setdefault(token, {"calls": [], "release": Event()})
            if parsed.path == "/release":
                state["release"].set()
            calls = list(state["calls"])
        self.write_json(200, {"calls": calls})

    def do_POST(self):  # noqa: N802
        """固定响应由真实业务工具结果驱动，首轮等待显式释放。"""
        if self.path != "/v1/chat/completions":
            self.write_json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            if not 0 < length <= 1000000:
                raise ValueError("invalid_length")
            body = json.loads(self.rfile.read(length))
            safe_planner = body.get("model") == SAFE_PLANNER_MODEL
            if not safe_planner and length > 200000:
                raise ValueError("invalid_length")
            if safe_planner:
                token, step, safe_delta, answered = safe_planner_replay_delta(self.headers.get("authorization"), body)
                call_id, record_ids = "", []
            else:
                token, step, call_id, answered, record_ids = validate_request(self.headers.get("authorization"), body)
        except (ValueError, KeyError, TypeError, IndexError) as error:
            if isinstance(error, ValueError) and re.fullmatch(r"[a-z_]+", str(error)):
                print(f"合成协议拒绝：{error}", flush=True)
            self.write_json(422, {"error": "outside_synthetic_contract"})
            return
        with LOCK:
            state = STATES.setdefault(token, {"calls": [], "release": Event()})
            state["calls"].append({"step": step, "phase": "answer" if answered else "read", "record_ids": record_ids})
        if step == "one" and not answered and not state["release"].wait(40):
            self.write_json(504, {"error": "synthetic_gate_timeout"})
            return
        if (
            step
            in {
                "feedback_gate",
                "profile_gate",
                "derived_profile_gate",
                "weight_gate",
                "weight_derived_gate",
                "bp_gate",
                "bp_derived_gate",
                "glucose_gate",
                "glucose_derived_gate",
                "lipids_gate",
                "lipids_derived_gate",
                "safe_gate",
            }
            and answered
            and not state["release"].wait(40)
        ):
            self.write_json(504, {"error": "synthetic_gate_timeout"})
            return
        delta = (
            {
                "role": "assistant",
                "content": (
                    "合成科普说明 [证据:00000000-0000-0000-0000-000000000000]"
                    if step == "invalid_evidence"
                    else "合成词法科普 " + " ".join(f"[证据:{identity}]" for identity in record_ids)
                    if step in {"lexical", "lexical_rebuilt"}
                    else f"合成科普说明 [证据:{record_ids[0]}]"
                    if step == "evidence"
                    else "合成读取：合成单餐偏咸"
                    if step in {"feedback", "derived_feedback", "feedback_gate"}
                    else "合成读取：合成餐后补充"
                    if step == "edited_feedback"
                    else "合成本人身高171；营养安全字段尚未就绪"
                    if step in {"profile", "derived_profile", "profile_gate", "derived_profile_gate"}
                    else "合成本人身高172；营养安全字段尚未就绪"
                    if step == "profile_updated"
                    else "合成本人体重60 kg；实测记录，不是确认档案或专业配餐依据"
                    if step in {"weight_read", "weight_gate", "weight_derived_gate"}
                    else "合成本人体重61 kg；实测记录，不是确认档案或专业配餐依据"
                    if step == "weight_updated"
                    else "当前没有体重实测记录；请补充测量记录"
                    if step == "weight_missing"
                    else "合成本人血压120/80 mmHg；实测记录，不作为临床诊断或专业配餐依据"
                    if step in {"bp_read", "bp_gate", "bp_derived_gate"}
                    else "合成本人血压122/82 mmHg；实测记录，不作为临床诊断或专业配餐依据"
                    if step == "bp_updated"
                    else "当前没有血压实测记录；请补充成对测量记录"
                    if step == "bp_missing"
                    else "当前未关联本人血压来源；请明确关联本人档案"
                    if step == "bp_not_linked"
                    else "合成本人血糖5.5 mmol/L，测量条件fasting；实测记录，不作为临床诊断或专业配餐依据"
                    if step in {"glucose_read", "glucose_gate", "glucose_derived_gate"}
                    else "合成本人血糖5.5 mmol/L，测量条件after_meal_2h；实测记录，不作为临床诊断或专业配餐依据"
                    if step == "glucose_updated"
                    else "当前没有血糖实测记录；请补充数值和测量条件"
                    if step == "glucose_missing"
                    else "当前未关联本人血糖来源；请明确关联本人档案"
                    if step == "glucose_not_linked"
                    else "合成本人血脂四项tc4.8、tg1.2、hdl1.3、ldl2.6 mmol/L；实测记录，不作为临床诊断或专业配餐依据"
                    if step in {"lipids_read", "lipids_gate", "lipids_derived_gate"}
                    else "合成本人血脂四项tc4.8、tg1.2、hdl1.3、ldl2.7 mmol/L；实测记录，不作为临床诊断或专业配餐依据"
                    if step == "lipids_updated"
                    else "当前没有血脂四项实测记录；请补充完整四项原值"
                    if step == "lipids_missing"
                    else "当前未关联本人血脂来源；请明确关联本人档案"
                    if step == "lipids_not_linked"
                    else "合成读取：我以后不吃香菜"
                    if step in {"read_memory", "derived_memory"}
                    else f"HEALTH_CONSULTATION_E2E_OK:{token}:{step}"
                ),
            }
            if answered
            else {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": call_id,
                        "type": "function",
                        "function": (
                            {
                                "name": "query_reviewed_nutrition_knowledge",
                                "arguments": json.dumps({"query": f"lexical{token} 膳食纤维 饮水"}),
                            }
                            if step in {"lexical", "lexical_rebuilt"}
                            else {
                                "name": "query_reviewed_nutrition_knowledge",
                                "arguments": json.dumps({"query": "合成营养证据"}),
                            }
                            if step in {"evidence", "invalid_evidence"}
                            else {
                                "name": "remember_member_fact",
                                "arguments": json.dumps(
                                    {
                                        "fact_key": "avoid_coriander",
                                        "kind": "preference",
                                        "subject": "我",
                                        "quote": "我以后不吃香菜",
                                        "persistence": "ongoing",
                                    }
                                ),
                            }
                            if step == "memory"
                            else {
                                "name": "remember_member_fact",
                                "arguments": json.dumps(
                                    {
                                        "fact_key": "avoid_coriander",
                                        "kind": "preference",
                                        "subject": "我",
                                        "quote": "我以后会吃香菜",
                                        "persistence": "ongoing",
                                    }
                                ),
                            }
                            if step == "update_memory" and call_id.endswith("-write")
                            else {"name": "get_member_memories", "arguments": "{}"}
                            if step in {"empty_memory", "read_memory", "update_memory"}
                            else {"name": "get_meal_feedback", "arguments": "{}"}
                            if step in {"feedback", "edited_feedback", "empty_feedback", "feedback_gate"}
                            else {"name": "get_complete_health_profile", "arguments": "{}"}
                            if step in {"profile", "profile_updated", "profile_gate"}
                            else {"name": "get_member_weight_records", "arguments": "{}"}
                            if step in {"weight_read", "weight_updated", "weight_missing", "weight_gate"}
                            else {"name": "get_member_blood_pressure_records", "arguments": "{}"}
                            if step in {"bp_read", "bp_updated", "bp_missing", "bp_not_linked", "bp_gate"}
                            else {"name": "get_member_blood_glucose_records", "arguments": "{}"}
                            if step
                            in {
                                "glucose_read",
                                "glucose_updated",
                                "glucose_missing",
                                "glucose_not_linked",
                                "glucose_gate",
                            }
                            else {"name": "get_member_blood_lipids_records", "arguments": "{}"}
                            if step
                            in {"lipids_read", "lipids_updated", "lipids_missing", "lipids_not_linked", "lipids_gate"}
                            else {"name": "get_confirmed_profile", "arguments": "{}"}
                        ),
                    }
                ],
            }
        )
        if step == "mixed_feedback" and not answered:
            delta = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": call_id,
                        "type": "function",
                        "function": {"name": "get_meal_feedback", "arguments": "{}"},
                    },
                    {
                        "index": 1,
                        "id": call_id + "-memory",
                        "type": "function",
                        "function": {"name": "get_member_memories", "arguments": "{}"},
                    },
                ],
            }
        if safe_planner:
            delta = safe_delta
        common = {
            "id": f"chatcmpl-{token}-{step}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": SAFE_PLANNER_MODEL if safe_planner else MODEL,
        }
        chunks = [
            {**common, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {
                **common,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop" if answered else "tool_calls"}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            },
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            for chunk in chunks:
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True

    def write_json(self, status, payload):
        """控制接口不返回请求正文或凭据。"""
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        """合成重放也不把 Authorization 或业务请求写入日志。"""


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8766), HealthReplayHandler).serve_forever()
