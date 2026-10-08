"""合成协议 oracle 的负向约束，不调用模型或业务数据库。"""

import json

import pytest

from test.support.health_consultation_replay_server import MODEL, STATES, HealthReplayHandler, validate_request

AUTH = "Bearer synthetic-health-replay-key"
TOKEN = "a" * 32


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/not-found?token=" + "b" * 32, 404),
        ("/observations?token=invalid", 422),
        ("/release?token=invalid", 422),
    ],
)
def test_control_routes_reject_unknown_paths_and_invalid_tokens(path, expected):
    """控制入口拒绝未知路径及非法标记，且不创建新的重放状态。"""
    handler = object.__new__(HealthReplayHandler)
    handler.path = path
    responses = []
    handler.write_json = lambda status, payload: responses.append((status, payload))
    before = set(STATES)
    handler.do_GET()
    assert len(responses) == 1 and responses[0][0] == expected
    assert set(STATES) == before


def replay_body():
    """固定输入来自显式常量，不能读取生产配置生成期望值。"""
    return {
        "model": MODEL,
        "stream": True,
        "tools": [
            {"type": "function", "function": {"name": name}}
            for name in (
                "get_confirmed_profile",
                "get_confirmed_diet",
                "get_complete_health_profile",
                "get_member_weight_records",
                "get_member_blood_pressure_records",
                "query_reviewed_nutrition_knowledge",
                "get_member_memories",
                "remember_member_fact",
                "get_meal_feedback",
            )
        ],
        "messages": [
            {"role": "system", "content": "slug: family-nutritionist\n## 咨询流程\n## 日常反馈与记忆边界"},
            {"role": "user", "content": f"HEALTH_CONSULTATION_E2E:{TOKEN}:one"},
        ],
    }


def record_result():
    """人工定义一条允许投影的合成已确认记录。"""
    return {
        "full_health_profile_available": False,
        "personal_meal_plan_available": False,
        "records": [
            {"record_id": "synthetic-record", "name": "测试指标", "value_numeric": "6.8", "unit_raw": "mmol/L"}
        ],
    }


def attach_result(body, result):
    """将本轮业务工具结果放在准确的 tool_call_id 下。"""
    body["messages"].append(
        {
            "role": "tool",
            "tool_call_id": f"health-read-{TOKEN}-one",
            "content": json.dumps(result),
        }
    )


def test_replay_accepts_only_explicit_minimal_synthetic_projection():
    """未答与已答对应不同协议阶段，并保留相同请求归属。"""
    body = replay_body()
    assert validate_request(AUTH, body) == (TOKEN, "one", f"health-read-{TOKEN}-one", False, [])
    attach_result(body, record_result())
    assert validate_request(AUTH, body) == (TOKEN, "one", f"health-read-{TOKEN}-one", True, ["synthetic-record"])


@pytest.mark.parametrize(
    "case,reason",
    [
        ("auth", "invalid_authorization_or_model"),
        ("model", "invalid_authorization_or_model"),
        ("stream", "stream_required"),
        ("extra_tool", "unexpected_tool_set"),
        ("missing_tool", "unexpected_tool_set"),
        ("real_query", "synthetic_input_required"),
        ("no_user", "synthetic_input_required"),
        ("missing_skill", "fixed_nutritionist_skill_required"),
    ],
)
def test_replay_rejects_non_synthetic_requests(case, reason):
    """每个入口约束都以具体错误拒绝，而不是返回合成成功。"""
    body, authorization = replay_body(), AUTH
    if case == "auth":
        authorization = "Bearer wrong-synthetic-key"
    elif case == "model":
        body["model"] = "unapproved-model"
    elif case == "stream":
        body["stream"] = False
    elif case == "extra_tool":
        body["tools"].append({"function": {"name": "read_file"}})
    elif case == "missing_tool":
        body["tools"].pop()
    elif case == "real_query":
        body["messages"][-1]["content"] = "不是合成协议标记"
    elif case == "missing_skill":
        body["messages"] = body["messages"][1:]
    else:
        body["messages"] = body["messages"][:1]
    with pytest.raises(ValueError, match=reason):
        validate_request(authorization, body)


@pytest.mark.parametrize(
    "private_field", ["evidence", "value_raw", "object_key", "member_id", "actor_uid", "display_name"]
)
def test_replay_rejects_private_evidence(private_field):
    """恢复任意一项禁止外发字段都必须让独立 oracle 失败。"""
    body, result = replay_body(), record_result()
    result["records"][0][private_field] = "synthetic-private-value"
    attach_result(body, result)
    with pytest.raises(ValueError, match="private_evidence_exported"):
        validate_request(AUTH, body)


@pytest.mark.parametrize(
    "case,reason",
    [
        ("profile", "unverified_profile_capability"),
        ("plan", "unverified_profile_capability"),
        ("missing", "confirmed_record_required"),
        ("extra", "confirmed_record_required"),
        ("value", "unexpected_synthetic_record"),
    ],
)
def test_replay_rejects_unverified_or_wrong_record(case, reason):
    """空记录、额外记录、错误值和伪装完整档案均不能通过。"""
    body, result = replay_body(), record_result()
    if case == "profile":
        result["full_health_profile_available"] = True
    elif case == "plan":
        result["personal_meal_plan_available"] = True
    elif case == "missing":
        result["records"] = []
    elif case == "extra":
        result["records"] *= 2
    else:
        result["records"][0]["value_numeric"] = "99"
    attach_result(body, result)
    with pytest.raises(ValueError, match=reason):
        validate_request(AUTH, body)


@pytest.mark.parametrize(
    "case,reason",
    [
        ("old_history", "invalid_feedback_history_leaked"),
        ("wrong_version", "active_meal_feedback_required"),
        ("formal", "feedback_self_report_scope_required"),
        ("missing_meal", "feedback_meal_reference_required"),
    ],
)
def test_feedback_replay_rejects_stale_or_unscoped_projection(case, reason):
    """反馈 oracle 独立拒绝旧内容、错误版本及伪装正式档案。"""
    body = replay_body()
    body["messages"][-1]["content"] = f"HEALTH_CONSULTATION_E2E:{TOKEN}:edited_feedback"
    result = {
        "feedback": [
            {
                "feedback_id": "synthetic-feedback",
                "diet_log_id": "synthetic-meal",
                "details": {"comment": "合成餐后补充"},
                "version": 2,
                "scope": "single_meal",
                "source_type": "user_self_report",
                "formal_profile": False,
                "meal": {"meal_type": "lunch"},
            }
        ]
    }
    body["messages"].append(
        {"role": "tool", "tool_call_id": f"health-read-{TOKEN}-edited_feedback", "content": json.dumps(result)}
    )
    if case == "old_history":
        body["messages"].insert(1, {"role": "assistant", "content": "合成单餐偏咸"})
    elif case == "wrong_version":
        result["feedback"][0]["version"] = 1
    elif case == "formal":
        result["feedback"][0]["formal_profile"] = True
    else:
        result["feedback"][0]["diet_log_id"] = None
    body["messages"][-1]["content"] = json.dumps(result)
    with pytest.raises(ValueError, match=reason):
        validate_request(AUTH, body)


def weight_replay_body(step="weight_read"):
    """人工固定体重投影，期望值不从业务实现或数据库生成。"""
    body = replay_body()
    body["messages"][-1]["content"] = f"HEALTH_CONSULTATION_E2E:{TOKEN}:{step}"
    payload = {
        "status": "ready",
        "code": "self_weight_records",
        "owner": "健康档案服务",
        "member_id": "11111111-1111-1111-1111-111111111111",
        "source_member_id": "22222222-2222-2222-2222-222222222222",
        "period": {"start_date": "2026-09-09", "end_date": "2026-10-08", "timezone": "Asia/Shanghai"},
        "limit": 20,
        "records": [
            {
                "record_id": "33333333-3333-3333-3333-333333333333",
                "value": 60,
                "unit": "kg",
                "measured_at": "2026-10-08T01:00:00Z",
                "source": "synthetic-weight-scale",
                "version": 1,
            }
        ],
        "truncated": False,
        "full_health_profile_available": False,
        "nutrition_safety_ready": False,
        "source_hash": "b" * 64,
    }
    if step == "weight_updated":
        payload["records"][0].update(value=61, version=2)
    if step == "weight_missing":
        payload.update(status="not_ready", code="weight_missing", records=[])
    return body, payload


def append_weight_result(body, payload, step):
    """工具回执严格绑定本轮固定调用ID。"""
    body["messages"].append(
        {"role": "tool", "tool_call_id": f"health-read-{TOKEN}-{step}", "content": json.dumps(payload)}
    )


@pytest.mark.parametrize("step", ["weight_read", "weight_updated", "weight_missing", "weight_gate"])
def test_weight_replay_accepts_exact_synthetic_value_or_explicit_missing(step):
    """60/v1、61/v2与明确缺口均通过独立投影oracle。"""
    body, payload = weight_replay_body(step)
    assert validate_request(AUTH, body) == (TOKEN, step, f"health-read-{TOKEN}-{step}", False, [])
    append_weight_result(body, payload, step)
    refs = [] if step == "weight_missing" else ["33333333-3333-3333-3333-333333333333"]
    assert validate_request(AUTH, body) == (TOKEN, step, f"health-read-{TOKEN}-{step}", True, refs)


@pytest.mark.parametrize(
    "case,reason",
    [
        ("body", "minimal_weight_projection_required"),
        ("note", "minimal_weight_record_required"),
        ("value", "synthetic_weight_value_required"),
        ("version", "synthetic_weight_value_required"),
        ("unit", "synthetic_weight_value_required"),
        ("source", "synthetic_weight_value_required"),
        ("time", "weight_utc_measurement_required"),
        ("period", "weight_period_required"),
        ("formal", "independent_weight_source_required"),
        ("profile", "minimal_weight_projection_required"),
        ("missing", "synthetic_weight_record_required"),
    ],
)
def test_weight_replay_rejects_wrong_value_version_source_and_formal_profile(case, reason):
    """恢复旧值、旧版本、错误单位时间或私有正文使oracle因准确原因失败。"""
    body, payload = weight_replay_body("weight_updated")
    record = payload["records"][0]
    if case == "body":
        payload["note"] = "不得外发的合成备注"
    elif case == "note":
        record["note"] = "不得外发的合成备注"
    elif case == "value":
        record["value"] = 60
    elif case == "version":
        record["version"] = 1
    elif case == "unit":
        record["unit"] = "lb"
    elif case == "source":
        record["source"] = "inferred-from-chat"
    elif case == "time":
        record["measured_at"] = "2026-10-08T09:00:00+08:00"
    elif case == "period":
        payload["period"]["start_date"] = "2026-09-08"
    elif case == "formal":
        payload["full_health_profile_available"] = True
    elif case == "profile":
        payload["confirmed_version"] = 2
    else:
        payload["records"] = []
    append_weight_result(body, payload, "weight_updated")
    with pytest.raises(ValueError, match=reason):
        validate_request(AUTH, body)


def test_weight_missing_does_not_accept_fabricated_record():
    """缺口模式不得返回模型补造的体重。"""
    body, payload = weight_replay_body("weight_missing")
    payload["records"] = weight_replay_body()[1]["records"]
    append_weight_result(body, payload, "weight_missing")
    with pytest.raises(ValueError, match="missing_weight_required"):
        validate_request(AUTH, body)


def test_weight_replay_accepts_device_source_selected_by_real_form():
    """浏览器设备来源须由实际工具投影给出，仍严格核对单条60kg/v1。"""
    body, payload = weight_replay_body()
    payload["records"][0]["source"] = "device"
    append_weight_result(body, payload, "weight_read")
    assert validate_request(AUTH, body)[3] is True


def test_weight_derived_gate_requires_prior_weight_answer_without_another_tool():
    """派生轮次必须沿用真实先前体重回答，并保留无新工具的发布测试。"""
    body, _ = weight_replay_body("weight_derived_gate")
    with pytest.raises(ValueError, match="prior_weight_answer_required"):
        validate_request(AUTH, body)
    body["messages"].insert(
        1, {"role": "assistant", "content": "合成本人体重60 kg；实测记录，不是确认档案或专业配餐依据"}
    )
    assert validate_request(AUTH, body) == (
        TOKEN,
        "weight_derived_gate",
        f"health-read-{TOKEN}-weight_derived_gate",
        True,
        [],
    )


@pytest.mark.parametrize("step", ["bp_read", "bp_updated", "bp_missing", "bp_not_linked", "bp_gate"])
def test_blood_pressure_replay_reads_only_exact_pair_or_explicit_gap(step):
    """固定九工具下核对成对原值、独立单位及空来源，不输出专业判断。"""
    body, payload = blood_pressure_replay_body(step)
    assert validate_request(AUTH, body)[3] is False
    append_blood_pressure_result(body, payload, step)
    expected_refs = [] if step in {"bp_missing", "bp_not_linked"} else ["33333333-3333-3333-3333-333333333333"]
    assert validate_request(AUTH, body) == (TOKEN, step, f"health-read-{TOKEN}-{step}", True, expected_refs)


@pytest.mark.parametrize("source", ["manual", "device", "report", "synthetic-blood-pressure-device"])
def test_blood_pressure_replay_retains_different_original_source_strings(source):
    """来源按实测原文保留，不把所有记录改写成单一来源。"""
    body, payload = blood_pressure_replay_body()
    payload["records"][0]["source"] = source
    append_blood_pressure_result(body, payload, "bp_read")
    assert validate_request(AUTH, body)[3] is True


@pytest.mark.parametrize(
    "case,reason",
    [
        ("extra_profile", "minimal_blood_pressure_projection_required"),
        ("private_note", "minimal_blood_pressure_record_required"),
        ("previous", "minimal_blood_pressure_record_required"),
        ("clinical", "minimal_blood_pressure_record_required"),
        ("missing_diastolic", "minimal_blood_pressure_record_required"),
        ("swapped_pair", "synthetic_blood_pressure_pair_required"),
        ("stale_systolic", "synthetic_blood_pressure_pair_required"),
        ("stale_diastolic", "synthetic_blood_pressure_pair_required"),
        ("bool_version", "synthetic_blood_pressure_pair_required"),
        ("string_value", "synthetic_blood_pressure_pair_required"),
        ("invalid_source", "synthetic_blood_pressure_pair_required"),
        ("weight_unit", "synthetic_blood_pressure_pair_required"),
        ("local_time", "blood_pressure_utc_measurement_required"),
        ("wide_period", "blood_pressure_period_required"),
        ("nutrition_ready", "independent_blood_pressure_source_required"),
    ],
)
def test_blood_pressure_replay_rejects_body_leaks_wrong_pair_and_unsafe_flags(case, reason):
    """负控覆盖成对字段、旧值、JSON类型及模型外呼最小范围。"""
    body, payload = blood_pressure_replay_body("bp_updated")
    row = payload["records"][0]
    if case == "extra_profile":
        payload["confirmed_version"] = 1
    elif case in {"private_note", "previous", "clinical"}:
        row[{"private_note": "note", "previous": "previous", "clinical": "diagnosis"}[case]] = "不能外发的合成正文"
    elif case == "missing_diastolic":
        row.pop("diastolic")
    elif case == "swapped_pair":
        row.update(systolic=82, diastolic=122)
    elif case == "stale_systolic":
        row["systolic"] = 120
    elif case == "stale_diastolic":
        row["diastolic"] = 80
    elif case == "bool_version":
        row["version"] = True
    elif case == "string_value":
        row["systolic"] = "122"
    elif case == "invalid_source":
        row["source"] = {"inferred": "model"}
    elif case == "weight_unit":
        row["unit"] = "kg"
    elif case == "local_time":
        row["measured_at"] = "2026-10-08T09:00:00+08:00"
    elif case == "wide_period":
        payload["period"]["start_date"] = "2026-09-08"
    else:
        payload["nutrition_safety_ready"] = True
    append_blood_pressure_result(body, payload, "bp_updated")
    with pytest.raises(ValueError, match=reason):
        validate_request(AUTH, body)


@pytest.mark.parametrize("step", ["bp_missing", "bp_not_linked"])
def test_blood_pressure_gap_rejects_a_fabricated_record(step):
    """缺口与未关联不得填零或补造一对测量。"""
    body, payload = blood_pressure_replay_body(step)
    payload["records"] = blood_pressure_replay_body()[1]["records"]
    append_blood_pressure_result(body, payload, step)
    with pytest.raises(ValueError, match="missing_blood_pressure_required|unlinked_blood_pressure_required"):
        validate_request(AUTH, body)


def test_blood_pressure_derived_gate_requires_actual_prior_pair_without_new_tool():
    """派生发布负控保持无新工具路径，必须存在先前真实成对回答。"""
    body, _ = blood_pressure_replay_body("bp_derived_gate")
    with pytest.raises(ValueError, match="prior_blood_pressure_answer_required"):
        validate_request(AUTH, body)
    body["messages"].insert(
        1, {"role": "assistant", "content": "合成本人血压120/80 mmHg；实测记录，不作为临床诊断或专业配餐依据"}
    )
    assert validate_request(AUTH, body)[3:] == (True, [])


def blood_pressure_replay_body(step="bp_read"):
    """显式血压夹具不从生产工具清单、投影或配置生成oracle。"""
    body = replay_body()
    body["messages"][-1]["content"] = f"HEALTH_CONSULTATION_E2E:{TOKEN}:{step}"
    payload = {
        "status": "ready",
        "code": "self_blood_pressure_records",
        "owner": "健康档案服务",
        "member_id": "11111111-1111-1111-1111-111111111111",
        "source_member_id": "22222222-2222-2222-2222-222222222222",
        "period": {"start_date": "2026-09-09", "end_date": "2026-10-08", "timezone": "Asia/Shanghai"},
        "limit": 20,
        "records": [
            {
                "record_id": "33333333-3333-3333-3333-333333333333",
                "systolic": 120.0,
                "diastolic": 80.0,
                "unit": "mmHg",
                "measured_at": "2026-10-08T01:00:00Z",
                "source": "synthetic-blood-pressure-device",
                "version": 1,
            }
        ],
        "truncated": False,
        "full_health_profile_available": False,
        "nutrition_safety_ready": False,
        "source_hash": "b" * 64,
    }
    if step == "bp_updated":
        payload["records"][0].update(systolic=122.0, diastolic=82.0, version=2)
    if step in {"bp_missing", "bp_not_linked"}:
        payload.update(status="not_ready", code="blood_pressure_missing", records=[])
    if step == "bp_not_linked":
        payload.update(code="blood_pressure_not_linked", source_member_id=None)
    return body, payload


def append_blood_pressure_result(body, payload, step):
    """只包装显式测试投影，不调用任何生产生成器。"""
    body["messages"].append(
        {
            "role": "tool",
            "tool_call_id": f"health-read-{TOKEN}-{step}",
            "content": json.dumps(payload, ensure_ascii=False),
        }
    )
