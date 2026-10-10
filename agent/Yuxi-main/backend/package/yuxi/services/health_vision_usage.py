"""识图成功尝试的有界模型用量；缺失报告不作为零计费。"""

TOKEN_KEYS = ("input_tokens", "output_tokens", "total_tokens")
USAGE_SCOPE = "successful_attempt_model_calls"


def vision_usage_receipt(usages: list) -> dict:
    """只保存用量数值，不复制供应商响应中的正文或扩展字段。"""
    return {
        "schema_version": 1,
        "scope": USAGE_SCOPE,
        "calls": [normalize_token_usage(usage) for usage in usages],
    }


def summarize_vision_usage(tasks: list) -> dict:
    """汇总当前有效任务的已报告值，历史和失败尝试仍保持未知。"""
    receipt_tasks = unknown_tasks = reported = missing = 0
    totals = dict.fromkeys(TOKEN_KEYS, 0)
    for task in tasks:
        result = task.get("result")
        receipt = result.get("provider_usage") if isinstance(result, dict) else None
        if (
            task["status"] != "success"
            or not isinstance(receipt, dict)
            or type(receipt.get("schema_version")) is not int
            or receipt.get("schema_version") != 1
            or receipt.get("scope") != USAGE_SCOPE
            or not isinstance(receipt.get("calls"), list)
            or not 1 <= len(receipt["calls"]) <= 100
        ):
            unknown_tasks += 1
            continue
        receipt_tasks += 1
        for call in receipt["calls"]:
            usage = normalize_token_usage(call)
            if usage is None:
                missing += 1
            else:
                reported += 1
                for key in TOKEN_KEYS:
                    totals[key] += usage[key]
    return {
        "scope": USAGE_SCOPE,
        "receipt_task_count": receipt_tasks,
        "unknown_task_count": unknown_tasks,
        "reported_call_count": reported,
        "missing_call_count": missing,
        "reported_tokens": totals if reported else dict.fromkeys(TOKEN_KEYS),
        "complete": bool(tasks) and not unknown_tasks and not missing,
        "billing_complete": False,
    }


def normalize_token_usage(usage) -> dict | None:
    """供应商边界接受一致的非负整数，缺失和非法值整体未知。"""
    if not isinstance(usage, dict):
        return None
    values = {key: usage.get(key) for key in TOKEN_KEYS}
    if any(type(value) is not int or not 0 <= value <= 10**12 for value in values.values()):
        return None
    if values["total_tokens"] != values["input_tokens"] + values["output_tokens"]:
        return None
    return values
